"""API web local (FastAPI). Sirve también el frontend compilado."""

from __future__ import annotations

from . import env  # noqa: F401  (debe ir antes que cualquier librería de IA)

import asyncio
import json
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, func, select
from sse_starlette.sse import EventSourceResponse

from . import __version__, knowledge_store as KS, proposals as PR, services
from . import people as people_mod
from . import regenerate as regen
from . import followups as FL
from . import followups_store as FS
from . import help_values, removal, speaker_fix
from .config import FRONTEND_DIST, MODELS_DIR, WORK_DIR, Settings, ensure_dirs, load_settings, save_settings
from .db import engine, get_session, init_db
from .media import probe
from .models import (
    Followup, FollowupItem, FollowupVersion, FollowupVideo, Job, Keyframe, KnowledgeItem, KnowledgeVersion, Person,
    Profile, ProfilePersonLink, Segment, Speaker, Video, SpeakerOverride, VideoCorrection, VoiceEmbedding,
)
from .models import now as models_now
from .pipeline.glossary import normalize
from .worker import STAGE_LABELS, worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
mimetypes.add_type("video/x-matroska", ".mkv")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    init_db()
    worker.start()
    yield


app = FastAPI(title="video-transcript", version=__version__, lifespan=lifespan)
SessionDep = Depends(get_session)


def _404(obj: Any, what: str = "Elemento") -> Any:
    if obj is None:
        raise HTTPException(404, f"{what} no encontrado")
    return obj


# --------------------------------------------------------------------------- estado y ajustes

@app.get("/api/status")
def status(session: Session = SessionDep) -> dict[str, Any]:
    s = load_settings()
    checks = {
        "ffmpeg": bool(__import__("shutil").which("ffmpeg")),
        "llama_server": Path(s.llama_server_path).exists(),
        "llm_model": Path(s.llm_model_path).exists(),
        "llm_mmproj": Path(s.llm_mmproj_path).exists(),
        "whisper": any((MODELS_DIR / "hf" / "hub").glob("models--Systran--faster-whisper-large-v3")),
        "align": any((MODELS_DIR / "hf" / "hub").glob("models--jonatasgrosman--wav2vec2-large-xlsr-53-spanish")),
        "diarization": (Path(s.diarization_model_dir) / "config.yaml").exists(),
    }
    pending = PR.pending_count(session, s.voice_auto_threshold)
    return {"version": __version__, "checks": checks, "ready": all(checks.values()), "current_job": worker.current,
            "pending_proposals": pending}


@app.get("/api/help/values")
def help_values_endpoint() -> dict[str, Any]:
    """Ajustes y umbrales que cita la ayuda, con su valor actual."""
    return help_values.values()


@app.get("/api/help/changelog")
def help_changelog() -> dict[str, str]:
    """Historial de cambios para la página «Novedades» de la ayuda."""
    path = Path(__file__).resolve().parents[2] / "CHANGELOG.md"
    return {"text": path.read_text(encoding="utf-8") if path.exists() else ""}


@app.get("/api/settings")
def get_settings() -> Settings:
    return load_settings()


@app.put("/api/settings")
def put_settings(body: Settings) -> Settings:
    save_settings(body)
    return body


@app.get("/api/probe")
def probe_file(path: str) -> dict[str, Any]:
    p = Path(path.strip().strip('"'))
    if not p.is_file():
        raise HTTPException(400, f"No existe el archivo: {p}")
    try:
        return {"path": str(p), **probe(p)}
    except RuntimeError as e:
        raise HTTPException(400, str(e))


# --------------------------------------------------------------------------- trabajos

class JobCreate(BaseModel):
    path: str
    profile_id: Optional[int] = None
    followup_ids: list[int] = []
    options: dict[str, Any] = {}


def job_out(job: Job, video: Video | None = None) -> dict[str, Any]:
    return {
        **job.model_dump(),
        "stage_label": STAGE_LABELS.get(job.stage, job.stage),
        "video_title": video.title if video else "",
        "video_source": video.source_path if video else "",
    }


@app.post("/api/jobs")
def create_job(body: JobCreate, session: Session = SessionDep) -> dict[str, Any]:
    p = Path(body.path.strip().strip('"'))
    if not p.is_file():
        raise HTTPException(400, f"No existe el archivo: {p}")
    active = session.exec(
        select(Video).where(Video.source_path == str(p), Video.status.in_(["pending", "processing"]))
    ).first()
    if active:
        raise HTTPException(409, "Ese vídeo ya está en la cola")
    followups = [_404(session.get(Followup, fid), "Seguimiento") for fid in dict.fromkeys(body.followup_ids)]
    if any(f.status != "abierto" for f in followups):
        raise HTTPException(400, "Un seguimiento archivado no admite vídeos nuevos")
    video = Video(source_path=str(p), title=p.stem, profile_id=body.profile_id)
    session.add(video)
    session.commit()
    for f in followups:
        session.add(FollowupVideo(followup_id=f.id, video_id=video.id))
    job = Job(video_id=video.id, options=body.options)
    session.add(job)
    session.commit()
    session.refresh(job)
    session.refresh(video)
    worker.notify()
    return job_out(job, video)


@app.get("/api/jobs")
def list_jobs(session: Session = SessionDep, limit: int = 30) -> list[dict[str, Any]]:
    jobs = session.exec(select(Job).order_by(Job.id.desc()).limit(limit)).all()
    return [job_out(j, session.get(Video, j.video_id)) for j in jobs]


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int, session: Session = SessionDep) -> dict[str, Any]:
    job = _404(session.get(Job, job_id), "Trabajo")
    if job.status == "queued":
        job.status, job.message = "cancelled", "Cancelado"
        session.add(job)
        session.commit()
    else:
        worker.cancel(job_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int, session: Session = SessionDep) -> dict[str, Any]:
    job = _404(session.get(Job, job_id), "Trabajo")
    if job.status not in ("error", "cancelled"):
        raise HTTPException(400, "Solo se pueden reintentar trabajos con error o cancelados")
    job.status, job.message, job.error = "queued", "Reintentando", ""
    session.add(job)
    session.commit()
    worker.notify()
    return {"ok": True}


@app.get("/api/events")
async def events():
    """Estado de los trabajos en tiempo real (Server-Sent Events)."""

    async def gen():
        last = None
        while True:
            with Session(engine) as s:
                jobs = s.exec(select(Job).order_by(Job.id.desc()).limit(30)).all()
                data = json.dumps([job_out(j, s.get(Video, j.video_id)) for j in jobs], default=str)
            if data != last:
                last = data
                yield {"event": "jobs", "data": data}
            await asyncio.sleep(1)

    return EventSourceResponse(gen())


# --------------------------------------------------------------------------- vídeos

def video_card(session: Session, v: Video) -> dict[str, Any]:
    names = services.speaker_names(session, v.id)
    sps = session.exec(select(Speaker).where(Speaker.video_id == v.id).order_by(Speaker.order_idx)).all()
    profile = session.get(Profile, v.profile_id) if v.profile_id else None
    return {
        "id": v.id, "title": v.title, "status": v.status, "duration": v.duration,
        "recorded_at": v.recorded_at, "created_at": v.created_at, "folder": v.folder,
        "profile": profile.name if profile else None, "profile_id": v.profile_id,
        "summary": v.summary_md,
        "people": [names[s.label] for s in sps],
        "pending_speakers": sum(1 for s in sps if not s.confirmed),
        "has_thumbnail": bool(v.folder and (Path(v.folder) / "miniatura.jpg").exists()),
    }


@app.get("/api/videos")
def list_videos(
    session: Session = SessionDep,
    profile_id: Optional[int] = None,
    person_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    q = select(Video).where(Video.status.in_(["done", "processing", "error"])).order_by(
        func.coalesce(Video.recorded_at, Video.created_at).desc()
    )
    if profile_id:
        q = q.where(Video.profile_id == profile_id)
    if person_id:
        ids = select(Speaker.video_id).where((Speaker.person_id == person_id) | (Speaker.suggested_person_id == person_id))
        q = q.where(Video.id.in_(ids))
    return [video_card(session, v) for v in session.exec(q).all() if v.folder or v.status != "done"]


@app.get("/api/videos/{video_id}")
def get_video(video_id: int, session: Session = SessionDep) -> dict[str, Any]:
    v = _404(session.get(Video, video_id), "Vídeo")
    names = services.speaker_names(session, v.id)
    speakers = []
    for sp in session.exec(select(Speaker).where(Speaker.video_id == v.id).order_by(Speaker.order_idx)):
        sug = session.get(Person, sp.suggested_person_id) if sp.suggested_person_id else None
        hints = sp.visual_hints or {}
        speakers.append({
            "id": sp.id, "label": sp.label, "name": names.get(sp.label, sp.label), "order": sp.order_idx,
            "person_id": sp.person_id, "confirmed": sp.confirmed, "is_owner": sp.is_owner,
            "suggested_person_id": sp.suggested_person_id, "suggested_person_name": sug.name if sug else None,
            "suggested_name": sp.suggested_name, "source": sp.source, "confidence": sp.confidence,
            "speaking_time": sp.speaking_time, "has_embedding": bool(sp.embedding),
            "visual_hints": {k: c for k, c in hints.items() if not k.startswith("_")},
            "reason": hints.get("_motivo", ""), "aliases": hints.get("_apodos", []), "split": hints.get("_split"),
        })
    segs = session.exec(select(Segment).where(Segment.video_id == v.id).order_by(Segment.idx)).all()
    frames = session.exec(select(Keyframe).where(Keyframe.video_id == v.id).order_by(Keyframe.t)).all()
    job = session.exec(select(Job).where(Job.video_id == v.id).order_by(Job.id.desc())).first()
    return {
        **video_card(session, v),
        "source_path": v.source_path, "video_path": v.video_path,
        "analysis": v.analysis, "speakers": speakers,
        "video_corrections": services.with_applied(v.analysis, vc := services.video_corrections(session, v.id)),
        "corrections_pending": bool(v.analysis) and services.corrections_pending(v.analysis, vc),
        "overrides_pending": bool(v.analysis) and speaker_fix.pending(v.analysis, speaker_fix.overrides(session, v.id)),
        "followups": [{"id": f.id, "name": f.name, "status": f.status,
                       "applied": session.get(FollowupVideo, (f.id, v.id)).applied}
                      for f in FS.for_video(session, v.id)],
        "segments": [{"id": s.id, "start": s.start, "end": s.end, "speaker": s.speaker,
                      "name": names.get(s.speaker, s.speaker), "text": s.text,
                      "original_text": s.original_text, "corrections": s.corrections, "voice": s.voice} for s in segs],
        "keyframes": [{"id": k.id, "t": k.t, "scene_type": k.scene_type, "description": k.description,
                       "visible_text": k.visible_text, "participants": k.participants,
                       "active_speaker": k.active_speaker} for k in frames],
        "job": job_out(job) if job else None,
    }


class VideoUpdate(BaseModel):
    title: Optional[str] = None
    profile_id: Optional[int] = None


@app.put("/api/videos/{video_id}")
def update_video(video_id: int, body: VideoUpdate, session: Session = SessionDep) -> dict[str, Any]:
    v = _404(session.get(Video, video_id), "Vídeo")
    if body.title is not None and body.title.strip():
        v.title = body.title.strip()
        v.analysis = {**(v.analysis or {}), "titulo": v.title}
    if body.profile_id is not None:
        v.profile_id = body.profile_id or None
    session.add(v)
    session.commit()
    services.export_video(session, v)
    services.index_video(session, v)
    return video_card(session, v)


class CorrectionIn(BaseModel):
    text: str


@app.get("/api/videos/{video_id}/corrections")
def list_corrections(video_id: int, session: Session = SessionDep) -> list[dict[str, Any]]:
    _404(session.get(Video, video_id), "Vídeo")
    return services.video_corrections(session, video_id)


@app.post("/api/videos/{video_id}/corrections")
def add_correction(video_id: int, body: CorrectionIn, session: Session = SessionDep) -> dict[str, Any]:
    """Corrección del usuario. Se aplica al regenerar el análisis."""
    _404(session.get(Video, video_id), "Vídeo")
    if not body.text.strip():
        raise HTTPException(400, "La corrección está vacía")
    session.add(VideoCorrection(video_id=video_id, text=body.text.strip()))
    session.commit()
    return {"ok": True}


@app.put("/api/corrections/{correction_id}")
def update_correction(correction_id: int, body: CorrectionIn, session: Session = SessionDep) -> dict[str, Any]:
    c = _404(session.get(VideoCorrection, correction_id), "Corrección")
    if not body.text.strip():
        raise HTTPException(400, "La corrección está vacía")
    if body.text.strip() != c.text:
        c.text, c.updated_at = body.text.strip(), models_now()
        session.add(c)
        session.commit()
    return {"ok": True}


@app.delete("/api/corrections/{correction_id}")
def delete_correction(correction_id: int, session: Session = SessionDep) -> dict[str, Any]:
    session.delete(_404(session.get(VideoCorrection, correction_id), "Corrección"))
    session.commit()
    return {"ok": True}


class OverrideIn(BaseModel):
    ranges: list[tuple[float, float]]
    person_id: int | None = None
    new_person_name: str | None = None


def _after_speaker_change(session: Session, v: Video, removed: list[tuple[float, float]] = ()) -> None:
    speaker_fix.refresh_segments(session, v, removed)
    services.export_video(session, v)
    services.index_video(session, v)


@app.get("/api/videos/{video_id}/speaker-overrides")
def list_overrides(video_id: int, session: Session = SessionDep) -> list[dict[str, Any]]:
    _404(session.get(Video, video_id), "Vídeo")
    out = []
    for o in speaker_fix.overrides(session, video_id):
        p = session.get(Person, o["person_id"])
        out.append({**o, "person_name": p.name if p else ""})
    return out


@app.post("/api/videos/{video_id}/speaker-overrides")
def add_overrides(video_id: int, body: OverrideIn, session: Session = SessionDep) -> dict[str, Any]:
    """«De tal momento a tal momento habla esta persona». Se aplica al momento a la transcripción."""
    v = _404(session.get(Video, video_id), "Vídeo")
    ranges = [(min(a, b), max(a, b)) for a, b in body.ranges if abs(b - a) > 0.01]
    if not ranges:
        raise HTTPException(400, "Indica el tramo")
    pid = body.person_id
    if body.new_person_name and body.new_person_name.strip():
        person = Person(name=body.new_person_name.strip())
        session.add(person)
        session.commit()
        pid = person.id
        if v.profile_id:
            session.add(ProfilePersonLink(profile_id=v.profile_id, person_id=pid))
    _404(session.get(Person, pid) if pid else None, "Persona")
    for a, b in ranges:
        session.add(SpeakerOverride(video_id=v.id, start=a, end=b, person_id=pid))
    session.commit()
    _after_speaker_change(session, v)
    return {"ok": True, "person_id": pid}


@app.delete("/api/speaker-overrides/{override_id}")
def delete_override(override_id: int, session: Session = SessionDep) -> dict[str, Any]:
    o = _404(session.get(SpeakerOverride, override_id), "Arreglo")
    v = session.get(Video, o.video_id)
    removed, pid = (o.start, o.end), o.person_id
    session.delete(o)
    session.commit()
    if not session.exec(select(SpeakerOverride).where(SpeakerOverride.video_id == v.id,
                                                      SpeakerOverride.person_id == pid)).first():
        manual = session.exec(select(Speaker).where(Speaker.video_id == v.id,
                                                    Speaker.label == f"{speaker_fix.MANUAL_PREFIX}{pid}")).first()
        if manual:
            session.delete(manual)
            session.commit()
    _after_speaker_change(session, v, [removed])
    return {"ok": True}


@app.get("/api/videos/{video_id}/words")
def video_words(video_id: int, start: float, end: float, session: Session = SessionDep) -> list[dict[str, Any]]:
    """Palabras con su momento en un tramo, para elegir dónde empieza o acaba una voz."""
    _404(session.get(Video, video_id), "Vídeo")
    ws = speaker_fix.words(session, video_id) or []
    return [{"word": w["word"].strip(), "start": w["start"], "end": w["end"]}
            for w in ws if start - 0.05 <= (w["start"] + w["end"]) / 2 <= end + 0.05 and w["word"].strip()]


@app.get("/api/videos/{video_id}/removal")
def removal_info(video_id: int, session: Session = SessionDep) -> dict[str, Any]:
    """Rutas y datos a los que afectaría quitar el vídeo."""
    v = _404(session.get(Video, video_id), "Vídeo")
    return {**removal.info(session, v),
            "followups": [{"id": f.id, "name": f.name, "applied": session.get(FollowupVideo, (f.id, v.id)).applied}
                          for f in FS.for_video(session, v.id)]}


class RemoveIn(BaseModel):
    delete_files: bool = False
    delete_video: bool = False
    delete_original: bool = False
    forget: bool = False
    follow_rebuild: list[int] = []  # seguimientos cuyo estado se rehace sin este vídeo


@app.post("/api/videos/{video_id}/remove")
def remove_video(video_id: int, body: RemoveIn, session: Session = SessionDep) -> dict[str, Any]:
    """Quita el vídeo de la app. Sin opciones, los ficheros se conservan para poder recuperarlo."""
    v = _404(session.get(Video, video_id), "Vídeo")
    if v.status == "processing":
        raise HTTPException(400, "El vídeo se está procesando")
    for f in FS.for_video(session, v.id):
        _detach(session, f, v, f.id in body.follow_rebuild)
    return removal.remove(session, v, removal.Options(**body.model_dump(exclude={"follow_rebuild"})))


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: int, session: Session = SessionDep) -> dict[str, Any]:
    """Quita el vídeo de la biblioteca sin borrar ningún fichero."""
    return remove_video(video_id, RemoveIn(), session)


@app.get("/api/videos/{video_id}/file")
def video_file(video_id: int, session: Session = SessionDep):
    v = _404(session.get(Video, video_id), "Vídeo")
    p = Path(v.video_path or v.source_path)
    if not p.is_file():
        raise HTTPException(404, f"No se encuentra el archivo de vídeo: {p}")
    return FileResponse(p, media_type=mimetypes.guess_type(p.name)[0] or "video/mp4")


@app.get("/api/videos/{video_id}/thumbnail")
def video_thumbnail(video_id: int, session: Session = SessionDep):
    v = _404(session.get(Video, video_id), "Vídeo")
    p = Path(v.folder or "") / "miniatura.jpg"
    if not v.folder or not p.is_file():
        raise HTTPException(404, "Sin miniatura")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/keyframes/{frame_id}/image")
def keyframe_image(frame_id: int, session: Session = SessionDep):
    k = _404(session.get(Keyframe, frame_id), "Fotograma")
    if not Path(k.path).is_file():
        raise HTTPException(404, "Fotograma no encontrado en disco")
    return FileResponse(k.path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.post("/api/videos/{video_id}/open-folder")
def open_folder(video_id: int, session: Session = SessionDep) -> dict[str, Any]:
    v = _404(session.get(Video, video_id), "Vídeo")
    if not v.folder or not Path(v.folder).is_dir():
        raise HTTPException(404, "La carpeta no existe")
    os.startfile(v.folder)  # noqa: S606  (abre el Explorador de Windows)
    return {"ok": True}


def _last_job(session: Session, v: Video) -> Job | None:
    return session.exec(select(Job).where(Job.video_id == v.id).order_by(Job.id.desc())).first()


@app.get("/api/videos/{video_id}/regenerate")
def regenerate_info(video_id: int, session: Session = SessionDep) -> dict[str, Any]:
    """Qué niveles de regeneración se pueden usar y cuánto tardaría cada uno."""
    v = _404(session.get(Video, video_id), "Vídeo")
    last = _last_job(session, v)
    work = WORK_DIR / f"job_{last.id}" if last else None
    out = regen.info(session, v, work, load_settings().max_frames)
    out["followups"] = [{"id": f.id, "name": f.name, "status": f.status,
                         "seconds": round(FS.rebuild_seconds(session, f, FS.date_of(v)))}
                        for f in FS.for_video(session, v.id)]
    return out


class RegenerateIn(BaseModel):
    level: str = "analysis"
    min_speakers: int | None = None  # solo en «full»: ayudan a la separación de voces
    max_speakers: int | None = None
    follow_rebuild: list[int] = []  # seguimientos cuyo estado se rehace desde este vídeo


@app.post("/api/videos/{video_id}/regenerate")
def regenerate(video_id: int, body: RegenerateIn | None = None, session: Session = SessionDep) -> dict[str, Any]:
    """Repite el análisis desde el nivel indicado con el perfil, las personas y el glosario actuales."""
    v = _404(session.get(Video, video_id), "Vídeo")
    level = (body or RegenerateIn()).level
    if level not in regen.LEVELS:
        raise HTTPException(400, f"Nivel desconocido: {level}")
    last = _last_job(session, v)
    reason = regen.availability(WORK_DIR / f"job_{last.id}" if last else None, regen.video_file(v))[level]
    if reason:
        raise HTTPException(400, reason)
    if level == "full":
        regen.unconfirm_speakers(session, v.id)
    job = _requeue(session, v, regen.stages(level), "Regenerando análisis", check_work=False,
                   extra={"follow_rebuild": (body or RegenerateIn()).follow_rebuild})
    if level == "full":
        opts = {k: val for k, val in (job.options or {}).items() if k not in ("min_speakers", "max_speakers", "num_speakers")}
        b = body or RegenerateIn()
        opts.update({k: val for k, val in (("min_speakers", b.min_speakers), ("max_speakers", b.max_speakers)) if val})
        job.options = opts
        session.add(job)
        session.commit()
    return {"ok": True, "job_id": job.id}


# Opciones que valen solo para un encolado: no se arrastran al siguiente
ONE_SHOT_OPTIONS = ("only", "follow_rebuild")


def _requeue(session: Session, v: Video, redo: list[str], message: str, check_work: bool = True,
             extra: dict[str, Any] | None = None) -> Job:
    """Vuelve a encolar el último trabajo del vídeo repitiendo solo las fases indicadas."""
    last = _last_job(session, v)
    if not last or last.status in ("queued", "running"):
        raise HTTPException(400, "Hay un trabajo en curso para este vídeo")
    if check_work and not (WORK_DIR / f"job_{last.id}" / "corrected.json").exists():
        raise HTTPException(400, "Faltan los datos intermedios de este vídeo; hay que analizarlo de nuevo desde cero")
    last.status, last.message, last.error, last.progress = "queued", message, "", 0.0
    last.started_at, last.finished_at = None, None  # el tiempo de este trabajo empieza ahora
    kept = {k: val for k, val in (last.options or {}).items() if k not in ONE_SHOT_OPTIONS}
    last.options = {**kept, **(extra or {}), "redo": redo}
    v.status = "processing"
    session.add(last), session.add(v)
    session.commit()
    worker.notify()
    return last


@app.post("/api/videos/{video_id}/learn")
def learn_video(video_id: int, session: Session = SessionDep) -> dict[str, Any]:
    """Vuelve a proponer conocimiento a partir de un vídeo ya analizado."""
    v = _404(session.get(Video, video_id), "Vídeo")
    job = _requeue(session, v, ["learn"], "Aprendiendo del vídeo")
    return {"ok": True, "job_id": job.id}


# --------------------------------------------------------------------------- hablantes

class SpeakerUpdate(BaseModel):
    person_id: Optional[int] = None
    new_person_name: Optional[str] = None
    confirm: bool = True


@app.put("/api/speakers/{speaker_id}")
def update_speaker(speaker_id: int, body: SpeakerUpdate, session: Session = SessionDep) -> dict[str, Any]:
    """Asigna (y confirma) una persona a un hablante. Con la confirmación se guarda su huella de voz."""
    sp = _404(session.get(Speaker, speaker_id), "Hablante")
    video = session.get(Video, sp.video_id)
    old_name = services.speaker_names(session, video.id).get(sp.label, "")

    person_id = body.person_id
    if body.new_person_name and body.new_person_name.strip():
        # Al confirmar la persona propuesta, se guardan también los apodos con que la llaman en el vídeo
        same = normalize(body.new_person_name) == normalize(sp.suggested_name)
        person = Person(name=body.new_person_name.strip(),
                        aliases=list((sp.visual_hints or {}).get("_apodos", [])) if same else [])
        session.add(person)
        session.commit()
        person_id = person.id
        if video.profile_id:
            session.add(ProfilePersonLink(profile_id=video.profile_id, person_id=person.id))

    # Quitar la huella anterior de este vídeo si se cambia de persona
    for e in session.exec(select(VoiceEmbedding).where(VoiceEmbedding.video_id == video.id)):
        if sp.person_id and e.person_id == sp.person_id:
            session.delete(e)

    old_pid = sp.person_id
    sp.person_id = person_id
    sp.confirmed = bool(person_id) and body.confirm
    if sp.confirmed and sp.embedding:
        session.add(VoiceEmbedding(person_id=person_id, video_id=video.id, vector=sp.embedding))
    session.add(sp)
    session.commit()

    new_name = services.speaker_names(session, video.id).get(sp.label, "")
    if old_name and new_name and old_name != new_name:
        video.analysis = services.replace_speaker_name(video.analysis or {}, old_name, new_name)
        video.summary_md = (video.analysis or {}).get("resumen_breve", video.summary_md)
        session.add(video)
        session.commit()
    if old_pid and old_pid != person_id:
        PR.reassign_speaker_items(session, video.id, sp.label, old_pid, person_id)
    if sp.confirmed:
        PR.link_to_profile(session, video, person_id)
    services.export_video(session, video)
    services.index_video(session, video)
    return {"ok": True, "name": new_name}


@app.post("/api/videos/{video_id}/confirm-speakers")
def confirm_all(video_id: int, session: Session = SessionDep) -> dict[str, Any]:
    """Acepta todas las propuestas de identidad pendientes de un vídeo."""
    video = _404(session.get(Video, video_id), "Vídeo")
    n = 0
    pending = session.exec(select(Speaker).where(Speaker.video_id == video_id, Speaker.confirmed == False)).all()  # noqa: E712
    for sp in pending:
        if sp.suggested_person_id:
            update_speaker(sp.id, SpeakerUpdate(person_id=sp.suggested_person_id), session)
            n += 1
        elif sp.suggested_name:
            update_speaker(sp.id, SpeakerUpdate(new_person_name=sp.suggested_name), session)
            n += 1
    session.refresh(video)
    return {"ok": True, "confirmed": n}


# --------------------------------------------------------------------------- perfiles

class ProfileIn(BaseModel):
    name: str
    description: str = ""
    context: str = ""
    extra_prompt: str = ""
    summary_sections: list[str] = []
    glossary: list[dict[str, Any]] = []
    person_ids: list[int] = []


def profile_out(session: Session, p: Profile) -> dict[str, Any]:
    ids = list(session.exec(select(ProfilePersonLink.person_id).where(ProfilePersonLink.profile_id == p.id)))
    n_videos = session.exec(select(func.count()).select_from(Video).where(Video.profile_id == p.id)).one()
    items = KS.owner_items(session, profile_id=p.id, statuses=("aceptado", "propuesto"))
    return {**p.model_dump(), "person_ids": ids, "video_count": n_videos,
            "learned_count": sum(1 for i in items if i.status == "aceptado"),
            "pending_count": sum(1 for i in items if i.status == "propuesto")}


@app.get("/api/profiles")
def list_profiles(session: Session = SessionDep) -> list[dict[str, Any]]:
    return [profile_out(session, p) for p in session.exec(select(Profile).order_by(Profile.name))]


@app.get("/api/profiles/{profile_id}")
def get_profile(profile_id: int, session: Session = SessionDep) -> dict[str, Any]:
    return profile_out(session, _404(session.get(Profile, profile_id), "Perfil"))


def _save_profile(session: Session, p: Profile, body: ProfileIn, reason: str = "Cambios manuales") -> dict[str, Any]:
    if p.id:
        KS.ensure_baseline(session, profile_id=p.id)
    data = body.model_dump(exclude={"person_ids"})
    data["glossary"] = [
        {"term": g.get("term", "").strip(), "variants": [v.strip() for v in g.get("variants", []) if v.strip()],
         "definition": g.get("definition", "").strip()}
        for g in data["glossary"] if g.get("term", "").strip()
    ]
    data["summary_sections"] = [s.strip() for s in data["summary_sections"] if s.strip()]
    for k, val in data.items():
        setattr(p, k, val)
    p.updated_at = datetime.now()
    session.add(p)
    session.commit()
    for link in session.exec(select(ProfilePersonLink).where(ProfilePersonLink.profile_id == p.id)):
        session.delete(link)
    for pid in dict.fromkeys(body.person_ids):
        session.add(ProfilePersonLink(profile_id=p.id, person_id=pid))
    session.commit()
    KS.record_version(session, reason, profile_id=p.id)
    return profile_out(session, p)


@app.post("/api/profiles")
def create_profile(body: ProfileIn, session: Session = SessionDep) -> dict[str, Any]:
    return _save_profile(session, Profile(name=body.name), body, reason="Creado")


@app.put("/api/profiles/{profile_id}")
def update_profile(profile_id: int, body: ProfileIn, session: Session = SessionDep) -> dict[str, Any]:
    return _save_profile(session, _404(session.get(Profile, profile_id), "Perfil"), body)


@app.get("/api/profiles/{profile_id}/versions")
def profile_versions(profile_id: int, session: Session = SessionDep) -> list[dict[str, Any]]:
    _404(session.get(Profile, profile_id), "Perfil")
    return KS.list_versions(session, profile_id=profile_id)


@app.post("/api/profiles/{profile_id}/versions/{version_id}/restore")
def restore_profile_version(profile_id: int, version_id: int, session: Session = SessionDep) -> dict[str, Any]:
    v = session.get(KnowledgeVersion, version_id)
    if not v or v.profile_id != profile_id:
        raise HTTPException(404, "Versión no encontrada")
    KS.restore_version(session, v)
    return profile_out(session, session.get(Profile, profile_id))


@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: int, session: Session = SessionDep) -> dict[str, Any]:
    p = _404(session.get(Profile, profile_id), "Perfil")
    session.delete(p)
    session.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- personas

class PersonIn(BaseModel):
    name: str
    role: str = ""
    aliases: list[str] = []
    notes: str = ""


def person_out(session: Session, p: Person) -> dict[str, Any]:
    voices = session.exec(select(func.count()).select_from(VoiceEmbedding).where(VoiceEmbedding.person_id == p.id)).one()
    videos = session.exec(
        select(func.count(func.distinct(Speaker.video_id))).where(Speaker.person_id == p.id)
    ).one()
    learned = len(KS.owner_items(session, person_id=p.id, statuses=("aceptado",)))
    return {**p.model_dump(), "voice_samples": voices, "video_count": videos, "learned_count": learned}


@app.get("/api/people")
def list_people(session: Session = SessionDep) -> list[dict[str, Any]]:
    return [person_out(session, p) for p in session.exec(select(Person).order_by(Person.name))]


@app.get("/api/people/duplicates")
def people_duplicates(session: Session = SessionDep) -> list[dict[str, Any]]:
    """Parejas de personas que podrían ser la misma (nombre parecido o voz parecida)."""
    return people_mod.duplicates(session)


class PairIn(BaseModel):
    a: int
    b: int


@app.post("/api/people/duplicates/dismiss")
def dismiss_duplicate(body: PairIn, session: Session = SessionDep) -> dict[str, Any]:
    people_mod.dismiss(session, body.a, body.b)
    return {"ok": True}


@app.get("/api/people/{person_id}")
def get_person(person_id: int, session: Session = SessionDep) -> dict[str, Any]:
    p = _404(session.get(Person, person_id), "Persona")
    return {**person_out(session, p), **people_mod.person_detail(session, p)}


class MergeIn(BaseModel):
    into_id: int


@app.post("/api/people/{person_id}/merge")
def merge_person(person_id: int, body: MergeIn, session: Session = SessionDep) -> dict[str, Any]:
    """Fusiona esta persona en otra (que se conserva)."""
    if person_id == body.into_id:
        raise HTTPException(400, "Elige otra persona")
    source = _404(session.get(Person, person_id), "Persona")
    target = _404(session.get(Person, body.into_id), "Persona")
    people_mod.merge(session, source, target)
    return person_out(session, session.get(Person, body.into_id))


@app.post("/api/people")
def create_person(body: PersonIn, session: Session = SessionDep) -> dict[str, Any]:
    p = Person(**body.model_dump())
    session.add(p)
    session.commit()
    KS.record_version(session, "Creada", person_id=p.id)
    return person_out(session, p)


@app.put("/api/people/{person_id}")
def update_person(person_id: int, body: PersonIn, session: Session = SessionDep) -> dict[str, Any]:
    p = _404(session.get(Person, person_id), "Persona")
    KS.ensure_baseline(session, person_id=p.id)
    renamed = body.name.strip() != p.name
    for k, val in body.model_dump().items():
        setattr(p, k, val)
    session.add(p)
    session.commit()
    KS.record_version(session, "Cambios manuales", person_id=p.id)
    if renamed:
        services.refresh_person_videos(session, p.id)
    return person_out(session, p)


@app.get("/api/people/{person_id}/versions")
def person_versions(person_id: int, session: Session = SessionDep) -> list[dict[str, Any]]:
    _404(session.get(Person, person_id), "Persona")
    return KS.list_versions(session, person_id=person_id)


@app.post("/api/people/{person_id}/versions/{version_id}/restore")
def restore_person_version(person_id: int, version_id: int, session: Session = SessionDep) -> dict[str, Any]:
    v = session.get(KnowledgeVersion, version_id)
    if not v or v.person_id != person_id:
        raise HTTPException(404, "Versión no encontrada")
    old_name = session.get(Person, person_id).name
    KS.restore_version(session, v)
    p = session.get(Person, person_id)
    if p.name != old_name:
        services.refresh_person_videos(session, p.id)
    return person_out(session, p)


@app.delete("/api/people/{person_id}")
def delete_person(person_id: int, session: Session = SessionDep) -> dict[str, Any]:
    p = _404(session.get(Person, person_id), "Persona")
    session.delete(p)
    session.commit()
    return {"ok": True}


@app.delete("/api/people/{person_id}/voices")
def reset_voices(person_id: int, session: Session = SessionDep) -> dict[str, Any]:
    """Olvida las huellas de voz de una persona (por si se asignaron mal)."""
    for e in session.exec(select(VoiceEmbedding).where(VoiceEmbedding.person_id == person_id)):
        session.delete(e)
    session.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- conocimiento aprendido

class Decision(BaseModel):
    accept: list[int] = []
    reject: list[int] = []
    edits: dict[int, dict[str, Any]] = {}


class ItemEdit(BaseModel):
    text: str | None = None
    term: str | None = None
    definition: str | None = None
    title: str | None = None
    name: str | None = None
    category: str | None = None


@app.get("/api/proposals")
def get_proposals(
    session: Session = SessionDep,
    video_id: int | None = None,
    profile_id: int | None = None,
    person_id: int | None = None,
) -> dict[str, Any]:
    return PR.list_proposals(session, load_settings().voice_auto_threshold, video_id, profile_id, person_id)


@app.post("/api/proposals/decide")
def decide_proposals(body: Decision, session: Session = SessionDep) -> dict[str, Any]:
    return PR.decide(session, load_settings().voice_auto_threshold, body.accept, body.reject, body.edits)


@app.get("/api/profiles/{profile_id}/knowledge")
def profile_knowledge(profile_id: int, session: Session = SessionDep) -> list[dict[str, Any]]:
    _404(session.get(Profile, profile_id), "Perfil")
    return _knowledge_out(session, KS.owner_items(session, profile_id=profile_id, statuses=("aceptado",)))


@app.get("/api/people/{person_id}/knowledge")
def person_knowledge(person_id: int, session: Session = SessionDep) -> list[dict[str, Any]]:
    _404(session.get(Person, person_id), "Persona")
    return _knowledge_out(session, KS.owner_items(session, person_id=person_id, statuses=("aceptado",)))


def _knowledge_out(session: Session, items: list[KnowledgeItem]) -> list[dict[str, Any]]:
    r = PR.Resolver(session, load_settings().voice_auto_threshold)
    return [PR.proposal_out(session, r, it, it.person_id) for it in items]


@app.put("/api/knowledge/{item_id}")
def edit_knowledge(item_id: int, body: ItemEdit, session: Session = SessionDep) -> dict[str, Any]:
    it = _404(session.get(KnowledgeItem, item_id), "Dato")
    if it.status != "aceptado":
        raise HTTPException(400, "Solo se pueden editar datos aceptados; las propuestas se editan al aceptarlas")
    PR.update_item(session, it, body.model_dump(exclude_none=True))
    return {"ok": True}


@app.post("/api/knowledge/{item_id}/retire")
def retire_knowledge(item_id: int, session: Session = SessionDep) -> dict[str, Any]:
    it = _404(session.get(KnowledgeItem, item_id), "Dato")
    if it.status != "aceptado":
        raise HTTPException(400, "Solo se pueden retirar datos aceptados")
    PR.retire_item(session, it)
    return {"ok": True}


@app.post("/api/knowledge/forget-video/{video_id}")
def forget_video(video_id: int, session: Session = SessionDep) -> dict[str, Any]:
    _404(session.get(Video, video_id), "Vídeo")
    return PR.forget_video(session, video_id)


class FromVideo(BaseModel):
    video_id: int
    name: str


@app.post("/api/profiles/from-video")
def profile_from_video(body: FromVideo, session: Session = SessionDep) -> dict[str, Any]:
    """Crea un perfil vacío para el vídeo y le pide a la IA que proponga su contenido."""
    v = _404(session.get(Video, body.video_id), "Vídeo")
    if not body.name.strip():
        raise HTTPException(400, "Indica un nombre para el perfil")
    if v.status != "done":
        raise HTTPException(400, "El vídeo aún no está analizado")
    p = Profile(name=body.name.strip())
    session.add(p)
    session.commit()
    for pid in dict.fromkeys(PR.speaker_persons(session, v.id)):
        session.add(ProfilePersonLink(profile_id=p.id, person_id=pid))
    previous = v.profile_id
    v.profile_id = p.id
    session.add(v)
    session.commit()
    KS.record_version(session, f"Creado desde el vídeo «{v.title}»", profile_id=p.id)
    try:
        _requeue(session, v, ["learn"], "Creando el perfil a partir del vídeo")
    except HTTPException:
        v.profile_id = previous
        session.add(v)
        session.delete(p)
        session.commit()
        raise
    return profile_out(session, p)


@app.post("/api/profiles/{profile_id}/learn-all")
def learn_all(profile_id: int, session: Session = SessionDep) -> dict[str, Any]:
    """Encola el aprendizaje de todos los vídeos ya analizados del perfil."""
    _404(session.get(Profile, profile_id), "Perfil")
    queued, skipped = 0, 0
    for v in session.exec(select(Video).where(Video.profile_id == profile_id, Video.status == "done")):
        try:
            _requeue(session, v, ["learn"], "Aprendiendo del vídeo")
            queued += 1
        except HTTPException:
            skipped += 1
    return {"queued": queued, "skipped": skipped}


# --------------------------------------------------------------------------- seguimientos

class FollowupIn(BaseModel):
    name: str
    description: str = ""


class FollowupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None  # abierto | archivado
    summary: str | None = None  # resumen escrito por el usuario («» vuelve al de la IA)
    use_ai_summary: bool = False


def _followup(session: Session, fid: int) -> Followup:
    return _404(session.get(Followup, fid), "Seguimiento")


def _queue_follow(session: Session, f: Followup, v: Video, message: str) -> Job:
    """Encola un trabajo que solo rehace el estado del seguimiento desde ese vídeo."""
    try:
        return _requeue(session, v, ["follow"], message, check_work=False,
                        extra={"only": ["follow"], "follow_rebuild": [f.id]})
    except HTTPException as e:
        raise HTTPException(400, f"No se puede rehacer ahora: «{v.title}» tiene un trabajo en curso") from e


def _no_ask(*_: Any) -> dict[str, Any]:
    raise RuntimeError("No hay vídeos que aplicar")


def _detach(session: Session, f: Followup, v: Video, rebuild: bool) -> None:
    """Quita un vídeo del seguimiento: rehace el estado sin él o lo deja como está (desactualizado)."""
    fv = session.get(FollowupVideo, (f.id, v.id))
    applied = fv.applied
    session.delete(fv)
    session.commit()
    if applied and rebuild:
        FS.record_version(session, f, f"Antes de quitar «{v.title}»")
        FS.revert_videos(session, f, {v.id})
        nxt = FS.first_from(session, f, FS.date_of(v))
        if nxt:
            try:
                _queue_follow(session, f, nxt, f"Actualizando el seguimiento «{f.name}»")
            except HTTPException:
                FS.mark_stale(session, f, FS.date_of(v), f"Se quitó «{v.title}» y falta rehacer el estado")
    elif applied:
        FS.mark_stale(session, f, FS.date_of(v), f"Se quitó «{v.title}»; el estado aún incluye lo que aportó")
    FS.export(session, f)
    services.export_video(session, v)


@app.get("/api/followups")
def list_followups(session: Session = SessionDep) -> list[dict[str, Any]]:
    rows = session.exec(select(Followup).order_by(Followup.updated_at.desc())).all()
    return [FS.out(session, f) for f in rows]


@app.post("/api/followups")
def create_followup(body: FollowupIn, session: Session = SessionDep) -> dict[str, Any]:
    if not body.name.strip():
        raise HTTPException(400, "Indica un nombre para el seguimiento")
    f = Followup(name=body.name.strip(), description=body.description.strip())
    session.add(f)
    session.commit()
    FS.record_version(session, f, "Creado")
    FS.export(session, f)
    return FS.out(session, f, full=True)


@app.get("/api/followups/{followup_id}")
def get_followup(followup_id: int, session: Session = SessionDep) -> dict[str, Any]:
    return FS.out(session, _followup(session, followup_id), full=True)


@app.put("/api/followups/{followup_id}")
def update_followup(followup_id: int, body: FollowupUpdate, session: Session = SessionDep) -> dict[str, Any]:
    f = _followup(session, followup_id)
    if body.status is not None and body.status not in ("abierto", "archivado"):
        raise HTTPException(400, "Estado desconocido")
    reason = []
    if body.name is not None and body.name.strip() and body.name.strip() != f.name:
        f.name = body.name.strip()
    if body.description is not None:
        f.description = body.description.strip()
    if body.status is not None:
        f.status = body.status
    if body.use_ai_summary or (body.summary is not None and not body.summary.strip()):
        latest = [fv for fv, _ in FS.links(session, f.id) if fv.applied]
        f.summary, f.summary_manual, f.summary_ai = latest[-1].summary if latest else "", False, ""
        reason.append("Resumen de la IA")
    elif body.summary is not None and body.summary.strip() != f.summary:
        FS.record_version(session, f, "Antes de editar el resumen")
        if not f.summary_manual:
            f.summary_ai = f.summary
        f.summary, f.summary_manual = body.summary.strip(), True
        reason.append("Resumen editado")
    FS.touch(session, f)
    if reason:
        FS.record_version(session, f, ", ".join(reason))
    FS.export(session, f)
    return FS.out(session, f, full=True)


@app.post("/api/followups/{followup_id}/open-folder")
def open_followup_folder(followup_id: int, session: Session = SessionDep) -> dict[str, Any]:
    f = _followup(session, followup_id)
    FS.export(session, f)
    if not f.folder or not Path(f.folder).is_dir():
        raise HTTPException(404, "La carpeta no existe")
    os.startfile(f.folder)  # noqa: S606  (abre el Explorador de Windows)
    return {"ok": True}


@app.delete("/api/followups/{followup_id}")
def delete_followup(followup_id: int, delete_folder: bool = False, session: Session = SessionDep) -> dict[str, Any]:
    FS.delete(session, _followup(session, followup_id), delete_folder)
    return {"ok": True}


class FollowupVideoIn(BaseModel):
    apply: bool = True  # aplicar el vídeo al estado (rehace desde su fecha)
    regenerate: bool = False  # además, regenerar el resumen del vídeo con el contexto del seguimiento


@app.post("/api/followups/{followup_id}/videos/{video_id}")
def add_followup_video(followup_id: int, video_id: int, body: FollowupVideoIn | None = None,
                       session: Session = SessionDep) -> dict[str, Any]:
    f = _followup(session, followup_id)
    v = _404(session.get(Video, video_id), "Vídeo")
    body = body or FollowupVideoIn()
    if f.status != "abierto":
        raise HTTPException(400, "El seguimiento está archivado: reábrelo para añadir vídeos")
    if session.get(FollowupVideo, (f.id, v.id)):
        raise HTTPException(409, "El vídeo ya está en ese seguimiento")
    if v.status != "done":
        raise HTTPException(400, "Espera a que termine el análisis del vídeo")
    session.add(FollowupVideo(followup_id=f.id, video_id=v.id))
    session.commit()
    job = None
    if body.regenerate:
        job = regenerate(v.id, RegenerateIn(level="analysis", follow_rebuild=[f.id]), session)
    elif body.apply:
        job = {"job_id": _queue_follow(session, f, v, f"Añadiendo al seguimiento «{f.name}»").id}
    else:
        FS.mark_stale(session, f, FS.date_of(v), f"«{v.title}» se añadió sin aplicarlo al estado")
    FS.export(session, f)
    services.export_video(session, v)  # la línea «Seguimientos» de su documento
    return {**FS.out(session, f, full=True), "job_id": job["job_id"] if job else None}


@app.delete("/api/followups/{followup_id}/videos/{video_id}")
def remove_followup_video(followup_id: int, video_id: int, rebuild: bool = False,
                          session: Session = SessionDep) -> dict[str, Any]:
    f = _followup(session, followup_id)
    v = _404(session.get(Video, video_id), "Vídeo")
    _404(session.get(FollowupVideo, (f.id, v.id)), "Vídeo del seguimiento")
    _detach(session, f, v, rebuild)
    return FS.out(session, f, full=True)


@app.post("/api/followups/{followup_id}/rebuild")
def rebuild_followup(followup_id: int, all_videos: bool = False, session: Session = SessionDep) -> dict[str, Any]:
    """Rehace el estado desde que está desactualizado (o desde el principio)."""
    f = _followup(session, followup_id)
    since = None if all_videos else f.stale_from
    if not all_videos and since is None:
        raise HTTPException(400, "El estado ya está al día")
    first = FS.first_from(session, f, since)
    if first:
        job = _queue_follow(session, f, first, f"Rehaciendo el seguimiento «{f.name}»")
        return {**FS.out(session, f, full=True), "job_id": job.id}
    FS.rebuild_from(session, f, since, _no_ask)  # no queda ningún vídeo que aplicar: solo deshacer
    return {**FS.out(session, f, full=True), "job_id": None}


class FollowupItemIn(BaseModel):
    kind: str | None = None
    text: str | None = None
    owner: str | None = None
    due: str | None = None
    status: str | None = None


def _item(session: Session, fid: int, item_id: int) -> FollowupItem:
    it = _404(session.get(FollowupItem, item_id), "Punto")
    if it.followup_id != fid:
        raise HTTPException(404, "Punto no encontrado")
    return it


def _manual_event(evento: str, nota: str = "") -> dict[str, Any]:
    return {"video_id": None, "date": None, "t": "", "evento": evento, "nota": nota, "source": "manual",
            "at": models_now().isoformat()}


@app.post("/api/followups/{followup_id}/items")
def add_followup_item(followup_id: int, body: FollowupItemIn, session: Session = SessionDep) -> dict[str, Any]:
    f = _followup(session, followup_id)
    if body.kind not in FL.KINDS or not (body.text or "").strip():
        raise HTTPException(400, "Indica el tipo y el texto")
    FS.record_version(session, f, "Antes de añadir un punto a mano")
    events = [_manual_event("creada")]
    status = body.status or FL.INITIAL[body.kind]
    if status != FL.INITIAL[body.kind]:
        ev = FL.status_for_event(body.kind, status)
        if not ev:
            raise HTTPException(400, "Estado no válido para ese tipo")
        events.append(_manual_event(ev))
    session.add(FollowupItem(followup_id=f.id, kind=body.kind, text=body.text.strip(), owner=(body.owner or "").strip(),
                             due=(body.due or "").strip(), status=FL.derive_status(body.kind, events), manual=True,
                             events=events))
    FS.touch(session, f)
    FS.export(session, f)
    return FS.out(session, f, full=True)


@app.put("/api/followups/{followup_id}/items/{item_id}")
def update_followup_item(followup_id: int, item_id: int, body: FollowupItemIn,
                         session: Session = SessionDep) -> dict[str, Any]:
    f = _followup(session, followup_id)
    it = _item(session, f.id, item_id)
    FS.record_version(session, f, "Antes de editar un punto")
    for field in ("text", "owner", "due"):
        val = getattr(body, field)
        if val is not None and (field != "text" or val.strip()):
            setattr(it, field, val.strip())
    if body.status is not None and body.status != it.status:
        ev = FL.status_for_event(it.kind, body.status)
        if not ev or body.status not in FL.STATUSES[it.kind]:
            raise HTTPException(400, "Estado no válido para ese tipo")
        it.events = FL.sort_events([*(it.events or []), _manual_event(ev)])
        it.status = FL.derive_status(it.kind, it.events)
    it.manual = True
    session.add(it)
    FS.touch(session, f)
    FS.export(session, f)
    return FS.out(session, f, full=True)


@app.delete("/api/followups/{followup_id}/items/{item_id}")
def delete_followup_item(followup_id: int, item_id: int, session: Session = SessionDep) -> dict[str, Any]:
    """Lo oculta en vez de borrarlo: así la IA no lo vuelve a crear al rehacer el estado."""
    f = _followup(session, followup_id)
    it = _item(session, f.id, item_id)
    FS.record_version(session, f, f"Antes de borrar «{it.text}»")
    it.hidden, it.manual = True, True
    session.add(it)
    FS.touch(session, f)
    FS.export(session, f)
    return FS.out(session, f, full=True)


@app.get("/api/followups/{followup_id}/versions")
def followup_versions(followup_id: int, session: Session = SessionDep) -> list[dict[str, Any]]:
    _followup(session, followup_id)
    rows = session.exec(select(FollowupVersion).where(FollowupVersion.followup_id == followup_id)
                        .order_by(FollowupVersion.id.desc())).all()
    return [{"id": r.id, "reason": r.reason, "created_at": r.created_at,
             "items": sum(1 for it in r.snapshot.get("items", []) if not it.get("hidden")),
             "videos": sum(1 for x in r.snapshot.get("videos", []) if x.get("applied"))} for r in rows]


@app.post("/api/followups/{followup_id}/versions/{version_id}/restore")
def restore_followup_version(followup_id: int, version_id: int, session: Session = SessionDep) -> dict[str, Any]:
    f = _followup(session, followup_id)
    ver = _404(session.get(FollowupVersion, version_id), "Versión")
    if ver.followup_id != f.id:
        raise HTTPException(404, "Versión no encontrada")
    FS.restore(session, f, ver)
    FS.export(session, f)
    return FS.out(session, f, full=True)


# --------------------------------------------------------------------------- búsqueda

def _fts_query(q: str) -> str:
    # Cada palabra como prefijo; las comillas del usuario se respetan como frase
    terms = []
    phrases = q.split('"')
    for i, chunk in enumerate(phrases):
        chunk = chunk.strip()
        if not chunk:
            continue
        if i % 2 == 1:
            terms.append('"' + chunk.replace('"', "") + '"')
        else:
            terms += ['"' + w.replace('"', "") + '"*' for w in chunk.split() if w]
    return " ".join(terms)


@app.get("/api/search")
def search(
    q: str = Query(min_length=2),
    profile_id: Optional[int] = None,
    person_id: Optional[int] = None,
    limit: int = 100,
    session: Session = SessionDep,
) -> list[dict[str, Any]]:
    fq = _fts_query(q)
    if not fq:
        return []
    rows = session.connection().execute(
        text(
            "SELECT kind, video_id, ref_id, t, speaker, snippet(search_fts, 0, '[[', ']]', '…', 24) AS snip "
            "FROM search_fts WHERE search_fts MATCH :q ORDER BY rank LIMIT :lim"
        ),
        {"q": fq, "lim": limit * 3},
    ).mappings().all()
    allowed: set[int] | None = None
    if profile_id or person_id:
        qv = select(Video.id)
        if profile_id:
            qv = qv.where(Video.profile_id == profile_id)
        if person_id:
            qv = qv.where(Video.id.in_(select(Speaker.video_id).where(Speaker.person_id == person_id)))
        allowed = set(session.exec(qv))
    out, titles = [], {}
    for r in rows:
        vid = int(r["video_id"])
        if allowed is not None and vid not in allowed:
            continue
        if vid not in titles:
            v = session.get(Video, vid)
            titles[vid] = v.title if v else "?"
        out.append({"kind": r["kind"], "video_id": vid, "video_title": titles[vid], "t": r["t"],
                    "speaker": r["speaker"], "snippet": r["snip"]})
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- frontend

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        f = FRONTEND_DIST / full_path
        if full_path and f.is_file():
            return FileResponse(f)
        # index.html nunca se cachea: tras recompilar apunta a ficheros nuevos (los de /assets llevan hash)
        return FileResponse(FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
