"""Fase 9: análisis con el modelo de lenguaje (resumen por bloques + informe final y título)."""

from __future__ import annotations

from typing import Any

from ..llm import LLMServer
from ..prompts import CHUNK_SCHEMA, CHUNK_SYSTEM, FINAL_SCHEMA, FINAL_SYSTEM, chunk_user, final_user, profile_block
from .base import JobContext
from .transcript import fmt_ts

MAX_CHUNK_CHARS = 90_000  # ≈ 25-30k tokens, deja margen en el contexto de 64k


def timeline(utts: list[dict[str, Any]], vision: list[dict[str, Any]], names: dict[str, str]) -> list[tuple[float, str]]:
    """Líneas cronológicas: habla y descripción de pantalla intercaladas."""
    lines = [(u["start"], f"[{fmt_ts(u['start'])}] {names.get(u['speaker'], u['speaker'] or '?')}: {u['text']}") for u in utts]
    prev = ""
    for v in vision:
        desc = (v.get("descripcion") or "").strip()
        if not desc or desc == prev:
            continue
        prev = desc
        app = f" · {v['aplicacion']}" if v.get("aplicacion") else ""
        txt = (v.get("texto_relevante") or "").strip().replace("\n", " ")
        extra = f" | Texto visible: {txt[:300]}" if txt else ""
        lines.append((v["t"], f"[{fmt_ts(v['t'])}] (pantalla · {v.get('tipo_escena', '')}{app}) {desc}{extra}"))
    lines.sort(key=lambda x: x[0])
    return lines


def chunk_lines(lines: list[tuple[float, str]], minutes: float, max_chars: int = MAX_CHUNK_CHARS) -> list[list[tuple[float, str]]]:
    chunks: list[list[tuple[float, str]]] = []
    cur: list[tuple[float, str]] = []
    size, start = 0, None
    for t, line in lines:
        if cur and (t - start >= minutes * 60 or size + len(line) > max_chars):
            chunks.append(cur)
            cur, size = [], 0
        if not cur:
            start = t
        cur.append((t, line))
        size += len(line) + 1
    if cur:
        chunks.append(cur)
    return chunks


def _fmt_items(r: dict[str, Any]) -> str:
    out = []
    if r.get("tareas"):
        out.append("Tareas: " + "; ".join(f"{x['tarea']} ({x['responsable'] or '?'}, {x['t']})" for x in r["tareas"]))
    if r.get("decisiones"):
        out.append("Decisiones: " + "; ".join(f"{x['decision']} ({x['t']})" for x in r["decisiones"]))
    if r.get("pendientes"):
        out.append("Pendientes: " + "; ".join(r["pendientes"]))
    return "\n".join(out)


def run(ctx: JobContext, llm: LLMServer) -> None:
    utts = ctx.load("corrected.json")
    vision = ctx.load("vision.json", [])
    duration = ctx.load("probe.json")["duration"]
    names = ctx.speaker_names
    context = profile_block(ctx.profile, ctx.people)

    chunks = chunk_lines(timeline(utts, vision, names), ctx.settings.chunk_minutes)
    if not chunks:
        raise RuntimeError("La transcripción está vacía: no se detectó habla en el vídeo")
    partial_state = ctx.load("analysis.partial.json", {})
    llm.start()
    partials = []
    for i, ch in enumerate(chunks):
        ctx.check_cancel()
        key = str(i)
        if key not in partial_state:
            ctx.report(0.05 + 0.75 * i / len(chunks), f"Resumiendo fragmento {i + 1}/{len(chunks)}")
            body = "\n".join(line for _, line in ch)
            end_t = ch[-1][0]
            r = llm.chat_json(CHUNK_SYSTEM, chunk_user(context, i + 1, len(chunks), fmt_ts(ch[0][0]), fmt_ts(end_t), body),
                              CHUNK_SCHEMA, max_tokens=6000)
            r.update(inicio=fmt_ts(ch[0][0]), fin=fmt_ts(end_t))
            partial_state[key] = r
            ctx.save("analysis.partial.json", partial_state)
        partials.append(partial_state[key])

    ctx.report(0.85, "Redactando resumen final y título")
    partial_text = "\n\n".join(
        f"### Fragmento {i + 1} ({p['inicio']} – {p['fin']})\n{p['resumen']}\n{_fmt_items(p)}" for i, p in enumerate(partials)
    )
    speakers = ", ".join(dict.fromkeys(names.get(u["speaker"], u["speaker"]) for u in utts if u["speaker"]))
    profile = ctx.profile or {}
    final = llm.chat_json(
        FINAL_SYSTEM,
        final_user(context, profile.get("extra_prompt", ""), profile.get("summary_sections") or [], fmt_ts(duration), speakers,
                   partial_text),
        FINAL_SCHEMA,
        max_tokens=10000,
    )
    final["titulo"] = final["titulo"].strip().strip('"«»').rstrip(".")
    final["fragmentos"] = partials
    ctx.save("analysis.json", final)
    ctx.report(1.0, f"Título: {final['titulo']}")
