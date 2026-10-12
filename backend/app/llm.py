"""Gestión de llama-server (llama.cpp) y cliente para respuestas JSON.

El servidor se arranca solo cuando una fase lo necesita y se para después, para que
la GPU quede libre para Whisper/pyannote (nunca hay dos modelos grandes a la vez).
"""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from .config import DATA_DIR, Settings
from .media import CREATE_NO_WINDOW

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMTruncated(LLMError):
    """La respuesta se cortó al llegar a `max_tokens`: repetir la misma petición daría lo mismo."""


class LLMServer:
    def __init__(self, settings: Settings):
        self.s = settings
        self.proc: subprocess.Popen | None = None
        self.base = f"http://127.0.0.1:{settings.llm_port}"
        self.log_path = DATA_DIR / "llama-server.log"

    # -- ciclo de vida -------------------------------------------------
    def start(self, timeout: float = 600) -> None:
        if self.proc and self.proc.poll() is None:
            return
        exe, model, mmproj = Path(self.s.llama_server_path), Path(self.s.llm_model_path), Path(self.s.llm_mmproj_path)
        for p in (exe, model):
            if not p.exists():
                raise LLMError(f"No existe {p}. Ejecuta scripts/download_models.py")
        args = [
            str(exe), "-m", str(model),
            "--host", "127.0.0.1", "--port", str(self.s.llm_port),
            "-c", str(self.s.llm_ctx), "-np", "1",
            "-ngl", "999", "--n-cpu-moe", str(self.s.llm_n_cpu_moe),
            "-fa", "on", "--jinja", "--no-webui",
            "--cache-type-k", "q8_0", "--cache-type-v", "q8_0",
        ]
        if mmproj.exists():
            args += ["--mmproj", str(mmproj)]
            if self.s.llm_image_min_tokens:
                args += ["--image-min-tokens", str(self.s.llm_image_min_tokens)]
            if self.s.llm_image_max_tokens:
                args += ["--image-max-tokens", str(self.s.llm_image_max_tokens)]
        log.info("Arrancando llama-server: %s", " ".join(args))
        self._logf = open(self.log_path, "ab")
        self.proc = subprocess.Popen(
            args, stdout=self._logf, stderr=subprocess.STDOUT, cwd=str(exe.parent), creationflags=CREATE_NO_WINDOW
        )
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise LLMError(f"llama-server terminó al arrancar (código {self.proc.returncode}). Ver {self.log_path}")
            try:
                r = httpx.get(self.base + "/health", timeout=2)
                if r.status_code == 200:
                    log.info("llama-server listo en %.0fs", time.time() - t0)
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
        self.stop()
        raise LLMError("llama-server no respondió a tiempo")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc = None
        if getattr(self, "_logf", None):
            self._logf.close()
            self._logf = None

    def __enter__(self) -> "LLMServer":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- llamadas ------------------------------------------------------
    def chat_json(
        self,
        system: str,
        user: str | list[dict[str, Any]],
        schema: dict[str, Any],
        max_tokens: int = 4096,
        temperature: float | None = None,
        retries: int = 2,
        thinking: bool = False,
    ) -> dict[str, Any]:
        """Petición de chat con salida restringida a un esquema JSON.

        `thinking`: con el «modo razonamiento» del modelo, que piensa antes de responder. Es mucho más lento y
        solo se usa donde se ha medido que hace falta (`max_tokens` incluye lo que piensa)."""
        body = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.s.llm_temperature if temperature is None else temperature,
            "top_p": self.s.llm_top_p,
            "top_k": self.s.llm_top_k,
            "min_p": self.s.llm_min_p,
            "presence_penalty": self.s.llm_presence_penalty,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": "respuesta", "schema": schema}},
            # Sin «modo razonamiento» salvo que se pida: salida directa
            "chat_template_kwargs": {"enable_thinking": thinking},
        }
        if thinking:
            body.update(THINKING_SAMPLING)
        last: Exception | None = None
        for _ in range(retries + 1):
            try:
                r = httpx.post(self.base + "/v1/chat/completions", json=body, timeout=1800)
                r.raise_for_status()
                choice = r.json()["choices"][0]
                content = choice["message"]["content"]
            except (httpx.HTTPError, KeyError) as e:
                last = e
                log.warning("Fallo en llamada al LLM: %s", e)
                time.sleep(2)
                continue
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                last = e
                saved = save_failure(body, content, choice.get("finish_reason"))
                if choice.get("finish_reason") == "length":
                    # Se ha cortado por el límite de tokens: repetir la misma petición daría lo mismo
                    raise LLMTruncated(f"La respuesta del modelo se cortó al llegar a {max_tokens} tokens "
                                   f"(guardada en {saved})") from e
                log.warning("Respuesta del LLM no válida (guardada en %s): %s", saved, e)
        raise LLMError(f"El modelo de lenguaje no devolvió una respuesta válida: {last}")


# Muestreo recomendado por Qwen para el modo razonamiento
THINKING_SAMPLING = {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0}


def save_failure(body: dict[str, Any], content: str, finish_reason: str | None) -> Path:
    """Guarda una respuesta no válida para poder diagnosticarla (sin las imágenes, que ocupan mucho)."""
    out = DATA_DIR / "llm_failures"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    messages = [{**m, "content": m["content"] if isinstance(m["content"], str) else
                 [p for p in m["content"] if p.get("type") == "text"]} for m in body["messages"]]
    path.write_text(json.dumps({"finish_reason": finish_reason, "max_tokens": body.get("max_tokens"),
                                "response": content, "messages": messages}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return path


def image_part(path: Path) -> dict[str, Any]:
    b64 = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
