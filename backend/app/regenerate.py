"""Regenerar un vídeo ya analizado: qué fases repite cada nivel y si se puede.

Niveles, de menos a más profundo (cada uno incluye los anteriores):
- `analysis`: corrección de términos, resumen, aprendizaje y publicación;
- `speakers`: además, vuelve a comprobar las voces e identificar a los hablantes (las confirmaciones se
  conservan; necesita el vídeo para volver a extraer el audio);
- `screen`: además, vuelve a elegir y analizar los fotogramas y a unificar los nombres;
- `full`: todo desde el audio. Los hablantes se vuelven a separar y hay que volver a confirmarlos.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from . import estimates
from .models import Job, Speaker, Video

LEVELS = ("analysis", "speakers", "screen", "full")
_STAGES = {
    "analysis": ["correct", "analyze", "learn", "publish"],
    "speakers": ["ingest", "voices", "names", "identify", "correct", "analyze", "learn", "publish"],
    "screen": ["ingest", "frames", "vision", "voices", "names", "identify", "correct", "analyze", "learn", "publish"],
    "full": ["ingest", "frames", "vision", "asr", "align", "diarize", "voices", "names", "identify", "correct",
             "analyze", "learn", "publish"],
}
# Lo que necesita cada nivel en la carpeta de trabajo (además del vídeo en `screen` y `full`)
_NEEDS = {
    "analysis": ("corrected.json",),
    "speakers": ("corrected.json", "diarization.json", "aligned.json"),
    "screen": ("corrected.json", "diarization.json", "aligned.json"),
    "full": (),
}


def stages(level: str) -> list[str]:
    if level not in _STAGES:
        raise ValueError(f"Nivel desconocido: {level}")
    return list(_STAGES[level])


def video_file(v: Video) -> Path | None:
    for p in (v.video_path, v.source_path):
        if p and Path(p).is_file():
            return Path(p)
    return None


def availability(work: Path | None, video: Path | None) -> dict[str, str]:
    """Motivo por el que no se puede usar cada nivel («» si se puede)."""
    out = {}
    for level in LEVELS:
        missing = [n for n in _NEEDS[level] if not (work and (work / n).exists())]
        if level != "analysis" and not video:
            out[level] = "No se encuentra el archivo de vídeo"
        elif missing:
            out[level] = "Faltan los datos intermedios de este vídeo; solo se puede analizar desde cero"
        else:
            out[level] = ""
    return out


def info(session: Session, v: Video, work: Path | None, max_frames: int) -> dict[str, Any]:
    """Disponibilidad y estimación de cada nivel, para la ventana de regenerar."""
    video = video_file(v)
    frames_file = work / "frames.json" if work else None
    frames = len(json.loads(frames_file.read_text(encoding="utf-8"))) if frames_file and frames_file.exists() else None
    reasons = availability(work, video)
    levels = []
    for level in LEVELS:
        est = estimates.estimate(session, stages(level), v.duration, frames, max_frames)
        levels.append({"level": level, "available": not reasons[level], "reason": reasons[level],
                       "seconds": round(est["total"])})
    confirmed = len(session.exec(select(Speaker).where(Speaker.video_id == v.id, Speaker.confirmed.is_(True))).all())
    names_file = work / "names.json" if work else None
    on_screen = sum(1 for g in json.loads(names_file.read_text(encoding="utf-8")) if g.get("readings", 0) >= 2) \
        if names_file and names_file.exists() else None
    options = (session.exec(select(Job).where(Job.video_id == v.id).order_by(Job.id.desc())).first() or Job(video_id=0)).options or {}
    return {"levels": levels, "video_path": str(video) if video else None, "confirmed_speakers": confirmed,
            "on_screen": on_screen, "min_speakers": options.get("min_speakers"), "max_speakers": options.get("max_speakers")}


def unconfirm_speakers(session: Session, video_id: int) -> None:
    """Antes de volver a separar las voces: las etiquetas dejarán de significar lo mismo.

    Las huellas de voz ya guardadas de esas personas se conservan, así que se volverán a proponer por voz.
    """
    for sp in session.exec(select(Speaker).where(Speaker.video_id == video_id)):
        if sp.label.startswith("MANUAL_"):
            continue  # hablante creado por un arreglo manual: sigue valiendo, se aplica por tiempo
        sp.person_id, sp.confirmed = None, False
        sp.suggested_person_id, sp.suggested_name, sp.source, sp.confidence = None, "", "", 0.0
        sp.visual_hints = {}
        session.add(sp)
    session.commit()
