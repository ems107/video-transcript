"""Generación de los documentos de resultados (Markdown, TXT, JSON)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .transcript import fmt_ts, group_turns

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str, max_len: int = 80) -> str:
    name = _BAD.sub("", name).strip()
    name = re.sub(r"\s+", " ", name)[:max_len].rstrip(" .")
    return name or "Sin título"


def unique_dir(parent: Path, name: str) -> Path:
    p = parent / name
    i = 2
    while p.exists():
        p = parent / f"{name} ({i})"
        i += 1
    return p


def _meta_lines(meta: dict[str, Any]) -> list[str]:
    lines = [f"- **Fecha:** {meta['date']}", f"- **Duración:** {meta['duration']}"]
    if meta.get("profile"):
        lines.append(f"- **Perfil:** {meta['profile']}")
    if meta.get("followups"):
        links = [f"[{name}]({link})" if link else name for name, link in meta["followups"]]
        lines.append(f"- **Seguimientos:** {', '.join(links)}")
    if meta.get("participants"):
        lines.append(f"- **Participantes:** {', '.join(meta['participants'])}")
    if meta.get("source"):
        lines.append(f"- **Archivo original:** {meta['source']}")
    return lines


def transcript_md(meta: dict[str, Any], utts: list[dict[str, Any]], names: dict[str, str]) -> str:
    out = [f"# {meta['title']}", "", *_meta_lines(meta), "", "## Transcripción", ""]
    for t in group_turns(utts):
        out.append(f"**[{fmt_ts(t['start'])}] {names.get(t['speaker'], t['speaker'] or '?')}:** {t['text']}")
        out.append("")
    return "\n".join(out)


def transcript_txt(utts: list[dict[str, Any]], names: dict[str, str]) -> str:
    return "\n".join(f"[{fmt_ts(u['start'])}] {names.get(u['speaker'], u['speaker'] or '?')}: {u['text']}" for u in utts) + "\n"


def summary_md(meta: dict[str, Any], a: dict[str, Any]) -> str:
    out = [f"# {meta['title']}", "", *_meta_lines(meta), ""]
    if a.get("resumen_breve"):
        out += ["## En resumen", "", a["resumen_breve"], ""]
    if a.get("resumen_detallado"):
        body = a["resumen_detallado"].strip()
        if not body.lstrip().startswith("#"):
            out += ["## Resumen detallado", ""]
        out += [body, ""]
    if a.get("tareas"):
        out += ["## Tareas", "", "| Responsable | Tarea | Plazo | Momento |", "|---|---|---|---|"]
        for x in a["tareas"]:
            cells = [x.get("responsable") or "—", x.get("tarea", ""), x.get("plazo") or "—", x.get("t", "")]
            out.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
        out.append("")
    if a.get("decisiones"):
        out += ["## Decisiones", ""] + [f"- {x['decision']} ({x.get('t', '')})" for x in a["decisiones"]] + [""]
    if a.get("pendientes"):
        pend = [x if isinstance(x, str) else f"{x.get('pendiente', '')} ({x.get('t', '')})" for x in a["pendientes"]]
        out += ["## Pendientes", ""] + [f"- {x}" for x in pend] + [""]
    if a.get("temas"):
        out += ["## Temas", ""] + [f"- {x}" for x in a["temas"]] + [""]
    return "\n".join(out)


def write_outputs(folder: Path, meta: dict[str, Any], utts: list[dict[str, Any]], names: dict[str, str],
                  analysis: dict[str, Any], extra: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "transcripcion.md").write_text(transcript_md(meta, utts, names), encoding="utf-8")
    (folder / "transcripcion.txt").write_text(transcript_txt(utts, names), encoding="utf-8")
    (folder / "resumen.md").write_text(summary_md(meta, analysis), encoding="utf-8")
    data = {"meta": meta, "analisis": analysis, "hablantes": names,
            "transcripcion": [{**u, "hablante": names.get(u["speaker"], u["speaker"])} for u in utts], **extra}
    (folder / "analisis.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
