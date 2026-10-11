"""Genera las capturas de la ayuda (frontend/public/capturas/*.png) con los vídeos de muestra.

Uso (con la web compilada y la GPU libre; tarda unos 10 minutos):
    cd backend
    uv run python ../scripts/help_screenshots.py

Monta una instancia aislada (carpeta temporal, puerto 8771, llama-server en 8092), analiza
samples/videos-prueba/*.mp4, reproduce el uso normal (confirmar hablantes, crear un perfil, aceptar
propuestas, una corrección, un cambio de hablante, un seguimiento con los dos vídeos) y recorre las
pantallas con Chrome sin ventana por CDP. Nunca usa los vídeos ni los datos del usuario. Al terminar borra la instancia.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples" / "videos-prueba"
OUT = ROOT / "frontend" / "public" / "capturas"
PORT, LLM_PORT, CDP_PORT = 8771, 8092, 9334
BASE = f"http://127.0.0.1:{PORT}"
WIDTH, HEIGHT = 1280, 900
CHROME = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
          r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# --------------------------------------------------------------------------- instancia aislada

def start_instance(tmp: Path) -> subprocess.Popen:
    data = tmp / "data"
    data.mkdir()
    (tmp / "Analizados").mkdir()
    settings = {"llm_port": LLM_PORT, "analyzed_dir": str(tmp / "Analizados"), "file_mode": "copy",
                "owner_name": "Ana"}
    (data / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    env = {**os.environ, "VT_DATA_DIR": str(data)}
    log_file = (tmp / "server.log").open("wb")  # abierto mientras viva el servidor
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
                            cwd=ROOT / "backend", env=env, stdout=log_file, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            if httpx.get(f"{BASE}/api/status", timeout=2).status_code == 200:
                return proc
        except httpx.HTTPError:
            time.sleep(1)
    raise RuntimeError("La instancia de prueba no arrancó (ver server.log)")


def wait_jobs(c: httpx.Client, label: str) -> None:
    t0 = time.time()
    while True:
        jobs = c.get("/api/jobs").json()
        if jobs and all(j["status"] in ("done", "error", "cancelled") for j in jobs):
            bad = [j for j in jobs if j["status"] != "done"]
            log(f"{label}: {time.time() - t0:.0f}s" + (f" — fallos: {[j['error'][:200] for j in bad]}" if bad else ""))
            return
        time.sleep(4)


def prepare(c: httpx.Client) -> dict[str, int]:
    """Analiza los vídeos de muestra y reproduce el uso normal de la app."""
    for name in ("reunion_prueba.mp4", "incidencia_pedidos.mp4"):
        c.post("/api/jobs", json={"path": str(SAMPLES / name), "options": {"file_mode": "copy"}})
        wait_jobs(c, f"análisis de {name}")
    videos = {v["title"]: v["id"] for v in c.get("/api/videos").json()}
    v1 = min(videos.values())
    c.post(f"/api/videos/{v1}/confirm-speakers")
    for sp in c.get(f"/api/videos/{v1}").json()["speakers"]:
        if not sp["confirmed"]:
            c.put(f"/api/speakers/{sp['id']}", json={"new_person_name": "Juan Pérez", "confirm": True})
    c.post("/api/profiles/from-video", json={"video_id": v1, "name": "Reuniones de proyecto"})
    wait_jobs(c, "perfil a partir del vídeo")
    items = c.get("/api/proposals", params={"video_id": v1}).json()["items"]
    accept = [x["id"] for x in items][: max(1, len(items) * 2 // 3)]
    c.post("/api/proposals/decide", json={"accept": accept, "reject": [], "edits": {}})
    d = c.get(f"/api/videos/{v1}").json()
    seg = next((s for s in d["segments"] if len(s["text"].split()) > 6), d["segments"][0])
    words = c.get(f"/api/videos/{v1}/words", params={"start": seg["start"], "end": seg["end"]}).json()
    other = next((s for s in d["speakers"] if s["label"] != seg["speaker"] and s["person_id"]), None)
    if words and other:
        c.post(f"/api/videos/{v1}/speaker-overrides",
               json={"ranges": [[words[0]["start"], words[min(1, len(words) - 1)]["end"]]], "person_id": other["person_id"]})
    c.post(f"/api/videos/{v1}/corrections",
           json={"text": "El informe de costes lo prepara María López, no Juan Pérez."})
    f = c.post("/api/followups", json={"name": "Proyecto de pedidos"}).json()
    for vid in sorted(videos.values()):
        c.post(f"/api/followups/{f['id']}/videos/{vid}", json={"apply": True})
        wait_jobs(c, "aplicar el vídeo al seguimiento")
    return {"v1": v1, "v2": max(videos.values()), "followup": f["id"]}


# --------------------------------------------------------------------------- Chrome por CDP

class CDP:
    def __init__(self, ws):
        self.ws, self.n, self.pending = ws, 0, {}

    async def reader(self):
        async for msg in self.ws:
            m = json.loads(msg)
            if "id" in m and m["id"] in self.pending:
                self.pending.pop(m["id"]).set_result(m)

    async def send(self, method, **params):
        self.n += 1
        fut = asyncio.get_event_loop().create_future()
        self.pending[self.n] = fut
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        r = await asyncio.wait_for(fut, 30)
        if "error" in r:
            raise RuntimeError(r["error"])
        return r.get("result", {})

    async def js(self, expr):
        r = await self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        return r.get("result", {}).get("value")


def save_png(data: bytes, name: str) -> None:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(OUT / f"{name}.png", optimize=True)


# Rutas reales (con el usuario de Windows) que no deben salir en capturas publicadas: se sustituyen
MASKS: list[tuple[str, str]] = []


async def mask_paths(c: CDP) -> None:
    pairs = json.dumps(MASKS + [(a.replace("\\", "/"), b.replace("\\", "/")) for a, b in MASKS])
    await c.js(f"""(() => {{ const pairs = {pairs};
        const fix = (t) => pairs.reduce((acc, [a, b]) => acc.split(a).join(b), t);
        const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walk.nextNode()) walk.currentNode.nodeValue = fix(walk.currentNode.nodeValue);
        document.querySelectorAll('input').forEach(i => {{ i.value = fix(i.value); }});
        document.querySelectorAll('[title]').forEach(e => {{ e.title = fix(e.title); }}); }})()""")


async def shoot(c: CDP, name: str, selector: str | None = None, pad: int = 12) -> None:
    """Captura la pantalla entera o solo un elemento (selector CSS o expresión JS que devuelve un elemento)."""
    await mask_paths(c)
    params = {"format": "png"}
    if selector:
        expr = selector if selector.startswith("(") else f"document.querySelector({json.dumps(selector)})"
        rect = await c.js(f"""(() => {{ const e = {expr}; if (!e) return null; e.scrollIntoView({{block: 'center'}});
            const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }})()""")
        if not rect:
            log(f"  ⚠ {name}: no se encontró el elemento")
            return
        await asyncio.sleep(0.4)
        rect = await c.js(f"""(() => {{ const r = ({expr}).getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }})()""")
        x, y, w, h = rect
        params["clip"] = {"x": max(0, x - pad), "y": max(0, y - pad), "width": w + 2 * pad, "height": h + 2 * pad, "scale": 1}
    r = await c.send("Page.captureScreenshot", **params)
    save_png(base64.b64decode(r["data"]), name)
    log(f"  {name}.png")


async def go(c: CDP, path: str, wait: float = 2.5) -> None:
    await c.send("Page.navigate", url=BASE + path)
    await asyncio.sleep(wait)


async def click_text(c: CDP, text: str, wait: float = 1.5) -> None:
    await c.js(f"""(() => {{ const el = [...document.querySelectorAll('button, a, label')]
        .find(e => e.textContent.trim().startsWith({json.dumps(text)})); el && el.click(); }})()""")
    await asyncio.sleep(wait)


CARD = "[...document.querySelectorAll('.card')].find(e => e.querySelector('h3')?.textContent.startsWith({}))"


async def capture_all(ids: dict[str, int], ws_url: str) -> None:
    async with websockets.connect(ws_url, max_size=50_000_000) as ws:
        c = CDP(ws)
        task = asyncio.create_task(c.reader())
        for d in ("Page", "Runtime"):
            await c.send(f"{d}.enable")
        await c.send("Emulation.setDeviceMetricsOverride", width=WIDTH, height=HEIGHT, deviceScaleFactor=1, mobile=False)
        await c.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
        v1, v2 = ids["v1"], ids["v2"]

        await go(c, "/")
        await shoot(c, "biblioteca")
        await go(c, "/nuevo")
        await c.js(f"""(() => {{ const i = document.querySelector('input'); const set = Object.getOwnPropertyDescriptor(
            HTMLInputElement.prototype, 'value').set; set.call(i, {json.dumps(str(SAMPLES / 'reunion_prueba.mp4'))});
            i.dispatchEvent(new Event('input', {{bubbles: true}})); }})()""")
        await click_text(c, "Comprobar", 2.5)
        await shoot(c, "nuevo-analisis")
        await go(c, "/cola")
        await shoot(c, "cola")
        await go(c, f"/videos/{v1}")
        await shoot(c, "video")
        await shoot(c, "hablantes", "(" + CARD.format(json.dumps("Hablantes")) + ")")
        await shoot(c, "correcciones", "(" + CARD.format(json.dumps("Correcciones")) + ")")
        await shoot(c, "video-seguimientos", "(" + CARD.format(json.dumps("Seguimientos")) + ")")
        await go(c, f"/videos/{v1}?tab=transcripcion")
        await shoot(c, "video-transcripcion")
        await c.js("document.querySelector('.who-btn')?.click()")
        await asyncio.sleep(1.2)
        await click_text(c, "Parte de la línea", 1.5)
        await c.js("(() => { const w = [...document.querySelectorAll('dialog button.word')]; w[1]?.click(); w[2]?.click(); })()")
        await asyncio.sleep(0.5)
        await shoot(c, "cambiar-hablante", "dialog[open]")
        await click_text(c, "Cancelar", 0.8)
        await go(c, f"/videos/{v1}")
        await click_text(c, "Regenerar análisis", 2)
        await shoot(c, "regenerar", "dialog[open]")
        await click_text(c, "Cancelar", 0.8)
        await click_text(c, "Quitar", 2)
        await shoot(c, "quitar", "dialog[open]")
        await click_text(c, "Cancelar", 0.8)
        await go(c, "/propuestas")
        await shoot(c, "propuestas")
        await go(c, "/perfiles/1?tab=aprendido")
        await shoot(c, "perfil")
        await go(c, "/perfiles/1?tab=historial")
        await shoot(c, "perfil-historial")
        await go(c, "/personas/1")
        await shoot(c, "persona-ficha")
        await go(c, "/buscar?q=Kubernetes")
        await shoot(c, "buscar")
        await go(c, "/ajustes")
        await shoot(c, "ajustes")
        await go(c, f"/seguimientos/{ids['followup']}")
        await c.js("[...document.querySelectorAll('button')].filter(b => b.textContent === 'Ver todas').forEach(b => b.click())")
        await asyncio.sleep(0.8)
        await shoot(c, "seguimiento")
        task.cancel()
        _ = v2


def start_chrome(tmp: Path) -> subprocess.Popen:
    exe = next((p for p in CHROME if Path(p).exists()), None)
    if not exe:
        raise RuntimeError("No se encuentra Chrome")
    proc = subprocess.Popen([exe, "--headless=new", f"--remote-debugging-port={CDP_PORT}",
                             f"--user-data-dir={tmp / 'chrome'}", f"--window-size={WIDTH},{HEIGHT}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        try:
            httpx.get(f"http://127.0.0.1:{CDP_PORT}/json", timeout=2)
            return proc
        except httpx.HTTPError:
            time.sleep(1)
    raise RuntimeError("Chrome no arrancó")


def main() -> None:
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        sys.exit("Compila antes la web: cd frontend; npm run build")
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="vt-capturas-"))
    server = chrome = None
    try:
        log(f"Instancia aislada en {tmp}")
        neutral = Path("C:/Usuarios/Ana")
        MASKS.extend([(str(tmp / "Analizados"), str(neutral / "Vídeos" / "Analizados")),
                      (str(SAMPLES), str(neutral / "Vídeos")), (str(tmp), str(neutral))])
        server = start_instance(tmp)
        with httpx.Client(base_url=BASE, timeout=60) as c:
            ids = prepare(c)
        chrome = start_chrome(tmp)
        page = next(t for t in httpx.get(f"http://127.0.0.1:{CDP_PORT}/json").json() if t["type"] == "page")
        asyncio.run(capture_all(ids, page["webSocketDebuggerUrl"]))
    finally:
        for p in (chrome, server):
            if p and p.poll() is None:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, check=False)
        time.sleep(2)
        shutil.rmtree(tmp, ignore_errors=True)
    log(f"Capturas en {OUT}")


if __name__ == "__main__":
    main()
