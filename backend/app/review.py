"""Revisión de un vídeo: lo que el usuario debe comprobar antes de que el vídeo cuente para lo demás.

Un vídeo recién analizado queda `pendiente`. El usuario revisa hablantes, transcripción y análisis, y pulsa
«Aplicar y continuar»: un trabajo (`aplicando`) aplica sus cambios, actualiza los seguimientos y propone
conocimiento. Después decide lo dudoso (`propuestas`) y el vídeo queda `revisado`.

Hasta entonces, los vídeos relacionados encolados después (mismo perfil o algún seguimiento en común) hacen
lo pesado y esperan antes de identificar a los hablantes y resumir: así usan las voces, el glosario y el
seguimiento ya revisados.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlmodel import Session, select

from . import followups as F
from . import followups_store as FS
from . import services, speaker_fix
from .config import WORK_DIR
from .models import FollowupItem, FollowupVideo, Job, KnowledgeItem, Person, Speaker, Video, VoiceEmbedding, VoiceSample

log = logging.getLogger(__name__)

PENDING, APPLYING, PROPOSALS, DONE = "pendiente", "aplicando", "propuestas", "revisado"
# Fases que esperan a que se revisen los vídeos relacionados anteriores
GATED_STAGES = ("names", "identify", "correct", "analyze")


def _last_job(session: Session, video_id: int) -> Job | None:
    return session.exec(select(Job).where(Job.video_id == video_id).order_by(Job.id.desc())).first()


def related(session: Session, v: Video) -> list[Video]:
    """Vídeos del mismo perfil o con algún seguimiento en común."""
    ids: set[int] = set()
    if v.profile_id:
        ids |= set(session.exec(select(Video.id).where(Video.profile_id == v.profile_id)))
    fids = list(session.exec(select(FollowupVideo.followup_id).where(FollowupVideo.video_id == v.id)))
    if fids:
        ids |= set(session.exec(select(FollowupVideo.video_id).where(FollowupVideo.followup_id.in_(fids))))
    ids.discard(v.id)
    return [x for x in (session.get(Video, i) for i in sorted(ids)) if x]


def blocker(session: Session, v: Video) -> Video | None:
    """El vídeo relacionado, encolado antes, que falta por revisar (o None si no hay ninguno).

    No bloquean los que fallaron o se cancelaron antes de analizarse: no hay nada que revisar."""
    for other in related(session, v):
        if other.id > v.id or other.review == DONE:
            continue
        job = _last_job(session, other.id)
        if other.status == "error" or (job and job.status in ("error", "cancelled") and not other.folder):
            continue
        return other
    return None


def speakers_map(session: Session, video_id: int) -> dict[str, int]:
    return {sp.label: sp.person_id for sp in session.exec(select(Speaker).where(Speaker.video_id == video_id))
            if sp.confirmed and sp.person_id}


def changes(session: Session, v: Video) -> list[dict[str, Any]]:
    """Cambios del usuario que el análisis aún no tiene en cuenta: [{kind, n, label}]."""
    out = []
    if not v.analysis:
        return out
    corrections = services.video_corrections(session, v.id)
    if services.corrections_pending(v.analysis, corrections):
        n = sum(1 for c in services.with_applied(v.analysis, corrections) if not c["applied"]) or 1
        out.append({"kind": "correcciones", "n": n, "label": f"{n} corrección" if n == 1 else f"{n} correcciones"})
    items = speaker_fix.overrides(session, v.id)
    if speaker_fix.pending(v.analysis, items):
        used = set((v.analysis or {}).get("hablantes_aplicados") or [])
        n = sum(1 for o in items if o["id"] not in used) or 1
        out.append({"kind": "tramos", "n": n, "label": f"{n} cambio" + ("s" if n != 1 else "") + " de quién habla"})
    now = speakers_map(session, v.id)
    # Sin valor (vídeos de antes de la revisión), las huellas se dan por calculadas con lo que hay
    before = now if v.voices_applied is None else {k: int(p) for k, p in v.voices_applied.items()}
    n = len({k for k in set(now) | set(before) if now.get(k) != before.get(k)})
    if n:
        out.append({"kind": "hablantes", "n": n, "label": f"{n} hablante" + ("s" if n != 1 else "") + " confirmado"
                    + ("s" if n != 1 else "") + " o cambiado" + ("s" if n != 1 else "")})
    return out


def apply_stages(session: Session, v: Video) -> list[str]:
    """Fases del trabajo «aplicar»: rehacer el análisis si hay correcciones o cambios de quién habla, y después
    las huellas de voz, los seguimientos y el aprendizaje."""
    kinds = {c["kind"] for c in changes(session, v)}
    redo = ["correct", "analyze"] if kinds & {"correcciones", "tramos"} else []
    return [*redo, "voiceprints", "follow", "learn", "publish"]


def pending(session: Session, v: Video) -> dict[str, int]:
    """Lo que falta por decidir de un vídeo tras aplicarlo: propuestas y dudas de sus seguimientos."""
    proposals = len(session.exec(select(KnowledgeItem.id).where(KnowledgeItem.video_id == v.id,
                                                                 KnowledgeItem.status == "propuesto")).all())
    follow = 0
    for f in FS.for_video(session, v.id):
        rows = session.exec(select(FollowupItem).where(FollowupItem.followup_id == f.id)).all()
        follow += sum(1 for it in rows if F.needs_review(FS.item_dict(it), v.id))
    voices = len(session.exec(select(VoiceEmbedding.id).where(VoiceEmbedding.video_id == v.id,
                                                               VoiceEmbedding.doubtful.is_(True))).all())
    return {"propuestas": proposals, "seguimiento": follow, "voces": voices}


def mark_changed(session: Session, v: Video) -> None:
    """El usuario ha cambiado algo que requiere aplicar de nuevo: el vídeo vuelve a estar pendiente."""
    if v.review in (DONE, PROPOSALS) and v.analysis:
        v.review = PENDING
        session.add(v)
        session.commit()


def check_done(session: Session, v: Video) -> bool:
    """Si ya no queda nada por decidir, el vídeo queda revisado (y se libera lo que esperaba por él)."""
    if v.review != PROPOSALS or any(pending(session, v).values()):
        return False
    v.review = DONE
    session.add(v)
    session.commit()
    drop_audio(session, v)
    return True


def check_videos(session: Session, video_ids: set[int | None]) -> None:
    for vid in video_ids:
        v = session.get(Video, vid) if vid else None
        if v:
            check_done(session, v)


def drop_audio(session: Session, v: Video) -> None:
    """El audio de trabajo se guarda hasta la revisión (lo necesitan las huellas de voz); después sobra."""
    job = _last_job(session, v.id)
    if job and job.status not in ("queued", "running", "waiting"):
        for name in ("audio.wav", "owner.wav"):
            (WORK_DIR / f"job_{job.id}" / name).unlink(missing_ok=True)


def release_waiting(session: Session) -> int:
    """Vuelve a poner en cola los trabajos que esperaban si ya no tienen nada que los bloquee."""
    n = 0
    for job in session.exec(select(Job).where(Job.status == "waiting")).all():
        v = session.get(Video, job.video_id)
        if v and blocker(session, v) is None:
            job.status, job.message = "queued", "Continúa tras la revisión"
            job.options = {k: val for k, val in (job.options or {}).items() if k != "waiting_for"}
            session.add(job)
            n += 1
    if n:
        session.commit()
    return n


def out(session: Session, v: Video) -> dict[str, Any]:
    """Estado de la revisión para la web."""
    data: dict[str, Any] = {"state": v.review, "changes": changes(session, v) if v.review != DONE else [],
                            "pending": {"propuestas": 0, "seguimiento": 0, "voces": 0}, "waiting": [],
                            "doubtful_voices": []}
    if v.review == PROPOSALS:
        data["pending"] = pending(session, v)
        for e in session.exec(select(VoiceEmbedding).where(VoiceEmbedding.video_id == v.id,
                                                          VoiceEmbedding.doubtful.is_(True))):
            p = session.get(Person, e.person_id)
            smp = session.exec(select(VoiceSample).where(VoiceSample.video_id == v.id,
                                                         VoiceSample.person_id == e.person_id)).first()
            data["doubtful_voices"].append({"id": e.id, "person_id": e.person_id, "person_name": p.name if p else "?",
                                            "similarity": e.similarity, "seconds": e.seconds,
                                            "sample_id": smp.id if smp else None})
    # Vídeos que esperan a que se revise este
    for job in session.exec(select(Job).where(Job.status == "waiting")).all():
        if (job.options or {}).get("waiting_for") == v.id:
            other = session.get(Video, job.video_id)
            data["waiting"].append({"id": other.id, "title": other.title})
    return data
