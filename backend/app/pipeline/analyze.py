"""Fase 9: análisis con el modelo de lenguaje (resumen por bloques + informe final y título)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from rapidfuzz import fuzz

from ..followups import pending_parts, strip_ids, verify_signals
from ..knowledge import effective_sections
from ..llm import LLMServer
from ..prompts import (
    CHUNK_FOLLOW_SCHEMA,
    CHUNK_SCHEMA,
    CHUNK_SYSTEM,
    FINAL_SCHEMA,
    FINAL_SYSTEM,
    chunk_user,
    corrections_block,
    final_user,
    followup_block,
    profile_block,
    who_block,
)
from .base import JobContext
from .glossary import normalize
from .names import SIMILAR, similarity
from .transcript import fmt_ts

# Un apodo debe parecerse a una parte del nombre («Selu» en «JoSELUis»): 100; «Selu»/«Sandra»: 40
NICKNAME_SIMILAR = 75
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


def participants(groups: list[dict[str, Any]], min_readings: int = 2) -> list[str]:
    """Nombres unificados vistos en pantalla (una lectura suelta suele ser un error o un título)."""
    return [g["canonical"] for g in groups if g["readings"] >= min_readings]


def _resolve(name: str, known: list[str], heard: str) -> str:
    """Forma de la lista que corresponde a `name`; si no está en ella, solo vale si se oye tal cual."""
    n = normalize(name)
    if not n:
        return ""
    best, best_s = "", 0.0
    for k in known:
        s = similarity(name, k)
        if s > best_s:
            best, best_s = k, s
    if best_s >= SIMILAR:
        return best
    # Solo el nombre de pila de un único participante: «Iosu» → «Iosu Urcelay…»
    firsts = [k for k in known if normalize(k).split()[0] == n]
    if len(firsts) == 1:
        return firsts[0]
    return name.strip() if f" {n} " in heard else ""


def collect_identities(
    partials: list[dict[str, Any]],
    unnamed: dict[str, str],
    known: list[str],
    taken: list[str],
    heard_text: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Identidades y apodos que propone el LLM en los fragmentos, verificados.

    - `unnamed`: «Hablante N» → etiqueta, solo los hablantes sin identificar.
    - `known`: participantes en pantalla y nombres ya asignados a otros hablantes.
    - `taken`: nombres que ya tiene otro hablante (no se repiten).
    Un nombre vale si es de la lista o se oye en la transcripción; un apodo, si se oye.
    """
    heard = f" {normalize(heard_text)} "
    used = {normalize(n) for n in taken}
    votes: dict[str, Counter] = {}
    reasons: dict[tuple[str, str], dict[str, str]] = {}
    for p in partials:
        for x in p.get("identidades") or []:
            label = unnamed.get((x.get("hablante") or "").strip())
            name = _resolve(x.get("nombre") or "", known, heard)
            if not label or not name or normalize(name) in used or re.fullmatch(r"(?i)hablante \d+", name):
                continue
            votes.setdefault(label, Counter())[name] += 1
            reasons.setdefault((label, name), {"motivo": x.get("motivo", ""), "t": x.get("t", "")})

    identities: dict[str, dict[str, Any]] = {}
    ranked = sorted(((c.most_common(1)[0][1], label) for label, c in votes.items()), reverse=True)
    for _, label in ranked:
        top = votes[label].most_common(2)
        if len(top) > 1 and top[0][1] == top[1][1]:
            continue  # el LLM duda entre dos nombres
        name = top[0][0]
        if normalize(name) in used:
            continue
        used.add(normalize(name))
        identities[label] = {"nombre": name, "votos": top[0][1], **reasons[(label, name)]}

    names_now = known + [d["nombre"] for d in identities.values()]
    nicknames: dict[str, list[str]] = {}
    for p in partials:
        for x in p.get("apodos") or []:
            alias, target = (x.get("apodo") or "").strip(), _resolve(x.get("nombre") or "", names_now, heard)
            na = normalize(alias)
            if not na or not target or f" {na} " not in heard or na == normalize(target):
                continue
            if any(normalize(k).split()[0] == na for k in names_now):
                continue  # es el nombre de pila de alguien de la lista
            if fuzz.partial_ratio(na, normalize(target).replace(" ", "")) < NICKNAME_SIMILAR:
                continue  # no se parece a su nombre: el LLM lo ha deducido sin base («Selu» → «Sandra»)
            if alias not in nicknames.setdefault(target, []):
                nicknames[target].append(alias)
    return identities, nicknames


def _fmt_items(r: dict[str, Any]) -> str:
    out = []
    if r.get("tareas"):
        out.append("Tareas: " + "; ".join(f"{x['tarea']} ({x['responsable'] or '?'}, {x['t']})" for x in r["tareas"]))
    if r.get("decisiones"):
        out.append("Decisiones: " + "; ".join(f"{x['decision']} ({x['t']})" for x in r["decisiones"]))
    if r.get("pendientes"):
        out.append("Pendientes: " + "; ".join(pending_parts(x)[0] for x in r["pendientes"]))
    return "\n".join(out)


def run(ctx: JobContext, llm: LLMServer) -> None:
    utts = ctx.load("corrected.json")
    vision = ctx.load("vision.json", [])
    duration = ctx.load("probe.json")["duration"]
    names = ctx.speaker_names
    context = "\n\n".join(filter(None, [profile_block(ctx.profile, ctx.people), followup_block(ctx.followups),
                                         corrections_block([c["text"] for c in ctx.corrections])]))
    order = list(dict.fromkeys(u["speaker"] for u in utts if u["speaker"]))
    shown = {lb: names.get(lb, lb) for lb in order}
    unnamed = {name: lb for lb, name in shown.items() if re.fullmatch(r"Hablante \d+", name)}
    named = [name for lb, name in shown.items() if lb not in unnamed.values()]
    on_screen = participants(ctx.load("names.json", []))
    known = list(dict.fromkeys(on_screen + named + [p["name"] for p in ctx.people]))
    speakers_info = [(shown[lb], ctx.speaker_status.get(lb, "")) for lb in order]
    who = who_block(on_screen, speakers_info, {})

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
            follow = bool(ctx.followups)
            r = llm.chat_json(
                CHUNK_SYSTEM,
                chunk_user(context, i + 1, len(chunks), fmt_ts(ch[0][0]), fmt_ts(end_t), body, who, follow=follow),
                CHUNK_FOLLOW_SCHEMA if follow else CHUNK_SCHEMA, max_tokens=6000)
            r.update(inicio=fmt_ts(ch[0][0]), fin=fmt_ts(end_t))
            partial_state[key] = r
            ctx.save("analysis.partial.json", partial_state)
        partials.append(partial_state[key])

    # Identidades y apodos deducidos del contexto (verificados): solo propuestas, nunca se confirman
    identities, nicknames = collect_identities(partials, unnamed, known, named, " ".join(u["text"] for u in utts))
    ctx.save("context_identities.json",
             {"identidades": identities, "apodos": nicknames, "evaluados": sorted(unnamed.values())})
    speakers_info = [
        (shown[lb], f"probablemente {identities[lb]['nombre']} (por el contexto: {identities[lb]['motivo']})")
        if lb in identities else (shown[lb], ctx.speaker_status.get(lb, "")) for lb in order
    ]
    who = who_block(on_screen, speakers_info, nicknames)

    ctx.report(0.85, "Redactando resumen final y título")
    partial_text = "\n\n".join(
        f"### Fragmento {i + 1} ({p['inicio']} – {p['fin']})\n{p['resumen']}\n{_fmt_items(p)}" for i, p in enumerate(partials)
    )
    speakers = ", ".join(dict.fromkeys(names.get(u["speaker"], u["speaker"]) for u in utts if u["speaker"]))
    profile = ctx.profile or {}
    final = llm.chat_json(
        FINAL_SYSTEM,
        final_user(context, profile.get("extra_prompt", ""), effective_sections(profile), fmt_ts(duration), speakers,
                   partial_text, who),
        FINAL_SCHEMA,
        max_tokens=10000,
    )
    final = strip_ids(final)  # los [T3]… del contexto del seguimiento no deben llegar a los textos
    final["titulo"] = final["titulo"].strip().strip('"«»').rstrip(".")
    if ctx.followups:
        # Qué puntos del seguimiento se tratan, según quien leyó la transcripción; solo lo que se cita de verdad
        final["seguimiento"] = verify_signals([x for p in partials for x in p.get("seguimiento") or []], utts,
                                              duration)
    final["fragmentos"] = partials
    final["correcciones_aplicadas"] = [{"id": c["id"], "updated_at": c["updated_at"]} for c in ctx.corrections]
    final["hablantes_aplicados"] = sorted(o["id"] for o in ctx.overrides)
    ctx.save("analysis.json", final)
    ctx.report(1.0, f"Título: {final['titulo']}")
