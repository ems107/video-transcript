"""Fase 3: el modelo de visión describe cada fotograma (escena, texto, participantes)."""

from __future__ import annotations

from collections import Counter

from ..llm import LLMServer, image_part
from ..prompts import VISION_SCHEMA, VISION_SYSTEM, profile_block, vision_user
from .base import JobContext
from .transcript import fmt_ts


def run(ctx: JobContext, llm: LLMServer) -> None:
    frames = ctx.load("frames.json", [])
    ctx.path("vision.raw.json").unlink(missing_ok=True)  # la fase «names» la rehace con lo nuevo
    if not frames:
        ctx.save("vision.json", [])
        ctx.save("screen_terms.json", [])
        return
    # Reanudación: conservar fotogramas ya analizados
    done = {round(v["t"], 2): v for v in ctx.load("vision.partial.json", [])}
    context = profile_block(ctx.profile, ctx.people)
    ctx.report(0.0, "Cargando modelo de visión")
    llm.start()
    results = []
    for i, f in enumerate(frames):
        ctx.check_cancel()
        key = round(f["t"], 2)
        if key in done:
            results.append(done[key])
            continue
        ctx.report(i / len(frames), f"Analizando fotograma {i + 1}/{len(frames)} ({fmt_ts(f['t'])})")
        content = [image_part(ctx.path("frames") / f["file"]), {"type": "text", "text": vision_user(context, fmt_ts(f["t"]))}]
        try:
            r = llm.chat_json(VISION_SYSTEM, content, VISION_SCHEMA, max_tokens=1200)
        except Exception as e:  # un fotograma ilegible no debe parar el análisis
            r = {"tipo_escena": "otro", "aplicacion": "", "descripcion": f"(no analizado: {e})", "texto_relevante": "",
                 "participantes": [], "hablante_activo": "", "terminos": []}
        r = {"t": f["t"], "file": f["file"], **r}
        results.append(r)
        if i % 5 == 0:
            ctx.save("vision.partial.json", results)
    ctx.save("vision.json", results)

    # Términos vistos en pantalla, por frecuencia (para orientar a Whisper)
    terms = Counter()
    for r in results:
        for t in [*r.get("terminos", []), *r.get("participantes", [])]:
            t = t.strip()
            if 2 < len(t) < 40:
                terms[t] += 1
    ctx.save("screen_terms.json", [t for t, _ in terms.most_common(200)])
    ctx.report(1.0, f"{len(results)} fotogramas analizados")
