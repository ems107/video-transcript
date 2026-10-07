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
from .config import FRONTEND_DIST, MODELS_DIR, WORK_DIR, Settings, ensure_dirs, load_settings, save_settings
from .db import engine, get_session, init_db
from .media import probe
from .models import (
    Job, Keyframe, KnowledgeItem, KnowledgeVersion, Person, Profile, ProfilePersonLink, Segment, Speaker, Video, VoiceEmbedding,
)
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
    video = Video(source_path=str(p), title=p.stem, profile_id=body.profile_id)
    session.add(video)
    session.commit()
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
        speakers.append({
            "id": sp.id, "label": sp.label, "name": names.get(sp.label, sp.label), "order": sp.order_idx,
            "person_id": sp.person_id, "confirmed": sp.confirmed, "is_owner": sp.is_owner,
            "suggested_person_id": sp.suggested_person_id, "suggested_person_name": sug.name if sug else None,
            "suggested_name": sp.suggested_name, "source": sp.source, "confidence": sp.confidence,
            "speaking_time": sp.speaking_time, "visual_hints": sp.visual_hints, "has_embedding": bool(sp.embedding),
        })
    segs = session.exec(select(Segment).where(Segment.video_id == v.id).order_by(Segment.idx)).all()
    frames = session.exec(select(Keyframe).where(Keyframe.video_id == v.id).order_by(Keyframe.t)).all()
    job = session.exec(select(Job).where(Job.video_id == v.id).order_by(Job.id.desc())).first()
    return {
        **video_card(session, v),
        "source_path": v.source_path, "video_path": v.video_path,
        "analysis": v.analysis, "speakers": speakers,
        "segments": [{"id": s.id, "start": s.start, "end": s.end, "speaker": s.speaker,
                      "name": names.get(s.speaker, s.speaker), "text": s.text,
                      "original_text": s.original_text, "corrections": s.corrections} for s in segs],
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


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: int, session: Session = SessionDep) -> dict[str, Any]:
    """Quita el vídeo de la biblioteca. No borra ningún archivo del disco."""
    v = _404(session.get(Video, video_id), "Vídeo")
    if v.status == "processing":
        raise HTTPException(400, "El vídeo se está procesando")
    session.connection().execute(text("DELETE FROM search_fts WHERE video_id = :v"), {"v": v.id})
    for model in (Segment, Keyframe, Speaker, Job):
        for row in session.exec(select(model).where(model.video_id == v.id)):
            session.delete(row)
    session.delete(v)
    session.commit()
    return {"ok": True}


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


@app.post("/api/videos/{video_id}/regenerate")
def regenerate(video_id: int, session: Session = SessionDep) -> dict[str, Any]:
    """Repite la corrección de términos y el análisis con los nombres y el perfil actuales."""
    v = _404(session.get(Video, video_id), "Vídeo")
    job = _requeue(session, v, ["correct", "analyze", "learn", "publish"], "Regenerando análisis")
    return {"ok": True, "job_id": job.id}


def _requeue(session: Session, v: Video, redo: list[str], message: str) -> Job:
    """Vuelve a encolar el último trabajo del vídeo repitiendo solo las fases indicadas."""
    last = session.exec(select(Job).where(Job.video_id == v.id).order_by(Job.id.desc())).first()
    if not last or last.status in ("queued", "running"):
        raise HTTPException(400, "Hay un trabajo en curso para este vídeo")
    if not (WORK_DIR / f"job_{last.id}" / "corrected.json").exists():
        raise HTTPException(400, "Faltan los datos intermedios de este vídeo; hay que analizarlo de nuevo desde cero")
    last.status, last.message, last.error, last.progress = "queued", message, "", 0.0
    last.options = {**(last.options or {}), "redo": redo}
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
        person = Person(name=body.new_person_name.strip())
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
    return {**p.model_dump(), "person_ids": ids, "video_count": n_videos}


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
    return {**p.model_dump(), "voice_samples": voices, "video_count": videos}


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
        return FileResponse(FRONTEND_DIST / "index.html")
