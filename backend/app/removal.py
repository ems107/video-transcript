"""Quitar un vídeo de la app y, si se pide, borrar sus ficheros. Copia de recuperación en `datos/`.

Al quitar sin borrar nada, la carpeta publicada conserva todo lo necesario para recuperar el análisis
en el futuro: los documentos, el vídeo y `datos/` (estado de los hablantes y los JSON de trabajo).
Solo se borran ficheros que escribe la app, o el vídeo cuando el usuario lo marca expresamente.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from . import __version__
from . import proposals as PR
from . import services
from .config import WORK_DIR
from .models import Job, Keyframe, KnowledgeItem, Person, Profile, Segment, Speaker, Video, VoiceEmbedding

APP_FILES = ("transcripcion.md", "transcripcion.txt", "resumen.md", "analisis.json", "miniatura.jpg")
APP_DIRS = ("fotogramas", "datos")
DATA_DIR = "datos"
# Ficheros de trabajo que bastan para reconstruir el análisis sin repetir las fases con GPU
WORK_FILES = ("probe.json", "frames.json", "vision.raw.json", "vision.json", "names.json", "screen_terms.json",
              "whisper_prompt.json", "asr.json", "aligned.json", "utterances.json", "diarization.json",
              "identities.json", "corrected.json", "context_identities.json", "analysis.json", "proposals.json",
              "screen_judgment.json")


def work_dirs(session: Session, video_id: int) -> list[Path]:
    return [WORK_DIR / f"job_{j.id}" for j in session.exec(select(Job).where(Job.video_id == video_id))]


def save_recovery(session: Session, video: Video, work_dir: Path | None = None) -> None:
    """Escribe `datos/` en la carpeta publicada: estado del vídeo y de sus hablantes, y los JSON de trabajo."""
    if not video.folder or not Path(video.folder).is_dir():
        return
    out = Path(video.folder) / DATA_DIR
    out.mkdir(exist_ok=True)
    profile = session.get(Profile, video.profile_id) if video.profile_id else None
    speakers = []
    for sp in session.exec(select(Speaker).where(Speaker.video_id == video.id).order_by(Speaker.order_idx)):
        person = session.get(Person, sp.person_id) if sp.person_id else None
        speakers.append({
            "label": sp.label, "order": sp.order_idx, "person": person.name if person else "",
            "person_aliases": list(person.aliases or []) if person else [], "confirmed": sp.confirmed,
            "suggested_name": sp.suggested_name, "source": sp.source, "confidence": sp.confidence,
            "is_owner": sp.is_owner, "speaking_time": sp.speaking_time, "visual_hints": sp.visual_hints,
            "embedding": sp.embedding,
        })
    meta = {
        "app_version": __version__, "title": video.title, "source_path": video.source_path,
        "video_path": video.video_path, "duration": video.duration,
        "recorded_at": video.recorded_at.isoformat() if video.recorded_at else None,
        "created_at": video.created_at.isoformat(), "profile": profile.name if profile else "",
        "speakers": speakers,
        "corrections": services.video_corrections(session, video.id),
    }
    (out / "video.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    if work_dir and work_dir.is_dir():
        for name in WORK_FILES:
            if (work_dir / name).exists():
                shutil.copy2(work_dir / name, out / name)


@dataclass
class Options:
    delete_files: bool = False  # documentos publicados y datos de trabajo
    delete_video: bool = False  # el vídeo que usa la app (la copia publicada o el original movido)
    delete_original: bool = False  # el original, si la app hizo una copia
    forget: bool = False  # lo aceptado que solo venía de este vídeo y las huellas de voz


def _same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def plan(folder: Path | None, video_path: Path | None, source_path: Path | None, work: list[Path],
         opts: Options) -> list[tuple[str, Path, Path | None]]:
    """Acciones sobre el disco: («delete», ruta, None), («move», origen, destino) o («rmdir», carpeta, None)."""
    acts: list[tuple[str, Path, Path | None]] = []
    has_video = bool(video_path and video_path.is_file())
    in_folder = has_video and folder is not None and _same(video_path.parent, folder)
    copied = bool(source_path and source_path.is_file() and (not has_video or not _same(source_path, video_path)))

    if opts.delete_files:
        if folder and folder.is_dir():
            acts += [("delete", folder / n, None) for n in (*APP_FILES, *APP_DIRS) if (folder / n).exists()]
        acts += [("delete", w, None) for w in work if w.exists()]
    if has_video and opts.delete_video:
        acts.append(("delete", video_path, None))
    elif in_folder and opts.delete_files:
        if copied:
            acts.append(("delete", video_path, None))  # solo es una copia: el original sigue en su sitio
        elif source_path and not source_path.exists() and source_path.parent.is_dir():
            acts.append(("move", video_path, source_path))  # se había movido: vuelve a su sitio
    if copied and opts.delete_original:
        acts.append(("delete", source_path, None))
    if opts.delete_files and folder and folder.is_dir():
        acts.append(("rmdir", folder, None))
    return acts


def execute(acts: list[tuple[str, Path, Path | None]]) -> list[str]:
    """Aplica el plan. Devuelve los errores (un fichero bloqueado no impide el resto)."""
    errors = []
    for kind, path, dst in acts:
        try:
            if kind == "delete":
                shutil.rmtree(path) if path.is_dir() else path.unlink(missing_ok=True)
            elif kind == "move":
                shutil.move(str(path), str(dst))
            elif kind == "rmdir" and path.is_dir() and not any(path.iterdir()):
                path.rmdir()  # solo si ha quedado vacía: nunca se borra nada que no sea de la app
        except OSError as e:
            errors.append(f"{path}: {e}")
    return errors


def info(session: Session, v: Video) -> dict[str, Any]:
    """Lo que afectaría quitar el vídeo, para mostrarlo antes de decidir."""
    folder = Path(v.folder) if v.folder and Path(v.folder).is_dir() else None
    video_path = Path(v.video_path) if v.video_path and Path(v.video_path).is_file() else None
    source = Path(v.source_path) if v.source_path and Path(v.source_path).is_file() else None
    copied = bool(source and (not video_path or not _same(source, video_path)))
    voices = len(session.exec(select(VoiceEmbedding).where(VoiceEmbedding.video_id == v.id)).all())
    pending = len(session.exec(select(KnowledgeItem).where(
        KnowledgeItem.video_id == v.id, KnowledgeItem.status == "propuesto")).all())
    return {
        "folder": str(folder) if folder else None,
        "video_path": str(video_path) if video_path else None,
        "source_path": str(source) if copied else None,
        "video_in_folder": bool(video_path and folder and _same(video_path.parent, folder)),
        "work_dirs": [str(w) for w in work_dirs(session, v.id) if w.exists()],
        "voices": voices, "pending_proposals": pending,
    }


def remove(session: Session, v: Video, opts: Options) -> dict[str, Any]:
    """Quita el vídeo de la app y aplica las opciones elegidas."""
    folder = Path(v.folder) if v.folder else None
    video_path = Path(v.video_path) if v.video_path else None
    source = Path(v.source_path) if v.source_path else None
    work = work_dirs(session, v.id)
    if not opts.delete_files:
        save_recovery(session, v, next((w for w in reversed(work) if w.is_dir()), None))

    stats = PR.forget_video(session, v.id) if opts.forget else {}
    if opts.forget:
        for e in session.exec(select(VoiceEmbedding).where(VoiceEmbedding.video_id == v.id)):
            session.delete(e)
    # Lo pendiente de este vídeo ya no se podría revisar; lo aceptado se conserva salvo que se olvide
    for it in session.exec(select(KnowledgeItem).where(KnowledgeItem.video_id == v.id,
                                                       KnowledgeItem.status.in_(["propuesto", "descartado_ia"]))):
        session.delete(it)
    session.connection().execute(text("DELETE FROM search_fts WHERE video_id = :v"), {"v": v.id})
    for model in (Segment, Keyframe, Speaker, Job):
        for row in session.exec(select(model).where(model.video_id == v.id)):
            session.delete(row)
    session.delete(v)
    session.commit()

    errors = execute(plan(folder, video_path, source, work, opts))
    return {"ok": not errors, "errors": errors, "forgotten": stats}
