"""Estimación del tiempo de cada fase a partir de lo que han tardado en este equipo.

Cada fase ejecutada guarda un `StageRun` con sus segundos y sus «unidades»: los fotogramas en `vision`
y los minutos de audio en el resto. La estimación divide el total de segundos entre el total de unidades
de las últimas ejecuciones: así un vídeo corto, donde pesa más cargar el modelo, no distorsiona la de
uno largo. Sin historial se usan valores medidos en una RTX 5070 Ti con grabaciones reales.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from .models import StageRun

HISTORY = 10
# Segundos por unidad medidos con tres grabaciones de 17, 24 y 37 min (visión a 2560 px)
DEFAULT_RATES = {
    "ingest": 2.0, "frames": 8.0, "vision": 15.0, "asr": 1.5, "align": 0.6, "diarize": 0.8,
    "names": 0.05, "identify": 0.05, "correct": 0.5, "analyze": 6.0, "learn": 5.0, "publish": 0.1,
    "follow": 2.0,  # por minuto de cada vídeo que se aplica al seguimiento
}
FRAMES_PER_MINUTE = 3.0  # si aún no se han elegido los fotogramas


def units(stage: str, duration: float, frames: int) -> float:
    """Magnitud con la que escala la fase."""
    return float(max(frames, 1)) if stage == "vision" else max(duration / 60.0, 0.1)


def rates(session: Session, stages: list[str]) -> dict[str, float]:
    out = {}
    for stage in stages:
        rows = session.exec(select(StageRun).where(StageRun.stage == stage)
                            .order_by(StageRun.id.desc()).limit(HISTORY)).all()
        units_sum = sum(r.units for r in rows)
        out[stage] = sum(r.seconds for r in rows) / units_sum if units_sum > 0 else DEFAULT_RATES.get(stage, 1.0)
    return out


def estimate(session: Session, stages: list[str], duration: float, frames: int | None,
             max_frames: int = 240) -> dict[str, Any]:
    """Segundos estimados por fase y en total."""
    if frames is None:
        frames = min(max_frames, round(duration / 60 * FRAMES_PER_MINUTE))
    r = rates(session, stages)
    per = {s: r[s] * units(s, duration, frames) for s in stages}
    return {"stages": per, "total": sum(per.values())}


def record(session: Session, job_id: int, video_id: int, stage: str, seconds: float, duration: float,
           frames: int) -> None:
    session.add(StageRun(job_id=job_id, video_id=video_id, stage=stage, seconds=round(seconds, 2),
                         units=units(stage, duration, frames)))
    session.commit()
