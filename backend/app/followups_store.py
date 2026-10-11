"""Seguimientos en la base de datos: estado, versiones, aplicar y rehacer vídeos, y su carpeta.

La lógica que no necesita la base de datos está en `followups.py`. Lo que usa la IA recibe la llamada
como función (`ask`), para que se pueda probar sin el modelo.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from . import estimates
from . import followups as F
from .config import load_settings
from .models import Followup, FollowupItem, FollowupVersion, FollowupVideo, Job, Segment, Video, now
from .pipeline.export import safe_name, unique_dir
from .pipeline.transcript import fmt_ts

log = logging.getLogger(__name__)

# (estado anterior con ids, descripción del vídeo, análisis del vídeo) -> respuesta de la IA
Ask = Callable[[str, str, str], dict[str, Any]]


def date_of(v: Video) -> datetime:
    return v.recorded_at or v.created_at


def item_dict(it: FollowupItem) -> dict[str, Any]:
    return {"id": it.id, "kind": it.kind, "text": it.text, "owner": it.owner, "due": it.due, "status": it.status,
            "manual": it.manual, "hidden": it.hidden, "events": list(it.events or [])}


def items(session: Session, fid: int) -> list[dict[str, Any]]:
    rows = session.exec(select(FollowupItem).where(FollowupItem.followup_id == fid).order_by(FollowupItem.id))
    return [item_dict(it) for it in rows]


def links(session: Session, fid: int) -> list[tuple[FollowupVideo, Video]]:
    """Vídeos del seguimiento en orden de fecha de grabación."""
    rows = session.exec(select(FollowupVideo, Video).join(Video, Video.id == FollowupVideo.video_id)
                        .where(FollowupVideo.followup_id == fid)).all()
    return sorted(rows, key=lambda r: (date_of(r[1]), r[1].id))


def for_video(session: Session, video_id: int, only_open: bool = False) -> list[Followup]:
    q = select(Followup).join(FollowupVideo, FollowupVideo.followup_id == Followup.id) \
        .where(FollowupVideo.video_id == video_id).order_by(Followup.id)
    if only_open:
        q = q.where(Followup.status == "abierto")
    return list(session.exec(q))


def summary_before(session: Session, f: Followup, before: datetime | None) -> str:
    """El resumen de la evolución tal como estaba antes de esa fecha."""
    applied = [(fv, v) for fv, v in links(session, f.id) if fv.applied]
    prev = [(fv, v) for fv, v in applied if before is None or date_of(v) < before]
    if not prev:
        return f.summary if f.summary_manual and not applied else ""
    if prev[-1] == applied[-1] and f.summary_manual:
        return f.summary  # lo último que hay es el del usuario
    return prev[-1][0].summary


def context_for_video(session: Session, video_id: int) -> list[str]:
    """Estado de cada seguimiento del vídeo antes de su fecha, para el contexto del análisis."""
    v = session.get(Video, video_id)
    out = []
    for f in for_video(session, video_id):
        dates = [date_of(x) for _, x in links(session, f.id) if x.id != video_id]
        block = F.context_block(f.name, f.description, summary_before(session, f, date_of(v)), items(session, f.id),
                                dates, date_of(v), with_ids=True)
        if block:
            out.append(block)
    return out


# --------------------------------------------------------------------------- versiones

def snapshot(session: Session, f: Followup) -> dict[str, Any]:
    return {
        "summary": f.summary, "summary_manual": f.summary_manual, "summary_ai": f.summary_ai,
        "items": items(session, f.id),
        "videos": [{"video_id": fv.video_id, "applied": fv.applied, "contribution": fv.contribution,
                    "summary": fv.summary} for fv, _ in links(session, f.id)],
    }


def record_version(session: Session, f: Followup, reason: str) -> FollowupVersion:
    v = FollowupVersion(followup_id=f.id, reason=reason, snapshot=snapshot(session, f))
    session.add(v)
    session.commit()
    return v


def restore(session: Session, f: Followup, version: FollowupVersion) -> None:
    """Vuelve al estado de esa versión. Los vídeos que se añadieron después quedan sin aplicar."""
    record_version(session, f, f"Antes de restaurar la versión del {version.created_at:%Y-%m-%d %H:%M}")
    snap = version.snapshot
    for it in session.exec(select(FollowupItem).where(FollowupItem.followup_id == f.id)):
        session.delete(it)
    session.flush()
    for it in snap.get("items", []):
        data = {k: it[k] for k in ("kind", "text", "owner", "due", "status", "manual", "hidden", "events")}
        keep_id = it.get("id") and session.get(FollowupItem, it["id"]) is None
        session.add(FollowupItem(followup_id=f.id, **data, **({"id": it["id"]} if keep_id else {})))
    by_video = {x["video_id"]: x for x in snap.get("videos", [])}
    unapplied = []
    for fv, v in links(session, f.id):
        old = by_video.get(fv.video_id)
        fv.applied, fv.contribution, fv.summary = (old["applied"], old["contribution"], old["summary"]) if old \
            else (False, "", "")
        if not fv.applied and v.analysis:
            unapplied.append(date_of(v))
        session.add(fv)
    f.summary, f.summary_manual, f.summary_ai = snap.get("summary", ""), snap.get("summary_manual", False), \
        snap.get("summary_ai", "")
    f.stale_from, f.stale_reason = (min(unapplied), "Hay vídeos que no estaban en esa versión") if unapplied \
        else (None, "")
    touch(session, f)


def touch(session: Session, f: Followup) -> None:
    f.updated_at = now()
    session.add(f)
    session.commit()


# --------------------------------------------------------------------------- aplicar y deshacer

def mark_stale(session: Session, f: Followup, since: datetime, reason: str) -> None:
    if f.stale_from is None or since <= f.stale_from:
        f.stale_from, f.stale_reason = since, reason
    touch(session, f)


def revert_videos(session: Session, f: Followup, video_ids: set[int]) -> None:
    """Quita del estado lo que la IA sacó de esos vídeos (lo manual se queda)."""
    plan = F.revert(items(session, f.id), video_ids)
    for iid in plan["delete"]:
        session.delete(session.get(FollowupItem, iid))
    for iid, evs in plan["update"].items():
        it = session.get(FollowupItem, iid)
        it.events, it.status = evs, F.derive_status(it.kind, evs)
        session.add(it)
    for fv, _ in links(session, f.id):
        if fv.video_id in video_ids:
            fv.applied, fv.contribution, fv.summary = False, "", ""
            session.add(fv)
    session.flush()
    last = [fv for fv, _ in links(session, f.id) if fv.applied]
    summary = last[-1].summary if last else ""
    if f.summary_manual:
        f.summary_ai = summary
    else:
        f.summary = summary
    touch(session, f)


def video_utts(session: Session, video_id: int) -> list[dict[str, Any]]:
    rows = session.exec(select(Segment).where(Segment.video_id == video_id).order_by(Segment.idx))
    return [{"start": s.start, "end": s.end, "speaker": s.speaker, "text": s.text} for s in rows]


def apply_video(session: Session, f: Followup, video: Video, analysis: dict[str, Any], ask: Ask,
                utts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Actualiza el estado con un vídeo. Los vídeos posteriores ya deben estar deshechos.

    `utts`: la transcripción, para comprobar las citas (si no se da, la publicada en la base de datos)."""
    when = date_of(video)
    utts = utts if utts is not None else video_utts(session, video.id)
    all_items = items(session, f.id)
    dates = [date_of(v) for _, v in links(session, f.id)]
    state = F.context_block(f.name, f.description, summary_before(session, f, when), all_items, dates, when,
                            with_ids=True)
    # Antes de publicar, el título del vídeo aún es el nombre del fichero
    desc = f"{when:%Y-%m-%d} «{analysis.get('titulo') or video.title}» (duración {fmt_ts(video.duration)})"
    visible = F.state_at(all_items, when) + [it for it in all_items if it.get("hidden")]
    ids = {F.short_id(it) for it in visible}
    signals = [x for x in analysis.get("seguimiento") or [] if x.get("id") in ids]
    points = F.analysis_points(analysis)
    r = ask(state, desc, F.analysis_text(analysis, points, signals))
    plan = F.apply_update(visible, r, video.id, when, video.duration, now(), points, utts)
    for iid, ev in plan["events"]:
        it = session.get(FollowupItem, iid)
        it.events = F.sort_events([*(it.events or []), ev])
        it.status = F.derive_status(it.kind, it.events)
        session.add(it)
    for n in plan["new"]:
        session.add(FollowupItem(followup_id=f.id, **n))
    fv = session.get(FollowupVideo, (f.id, video.id))
    summary = (r.get("resumen") or "").strip()
    fv.applied, fv.contribution, fv.summary = True, (r.get("aporte") or "").strip(), summary
    session.add(fv)
    if f.summary_manual:
        f.summary_ai = summary
    else:
        f.summary = summary
    touch(session, f)
    if plan["discarded"]:
        log.info("Seguimiento %s, vídeo %s: descartado %s", f.id, video.id, plan["discarded"])
    possible = [(iid, ev["posible"]) for iid, ev in plan["events"] if ev.get("posible")]
    if possible:
        log.info("Seguimiento %s, vídeo %s: posibles sin cita %s", f.id, video.id, possible)
    return {"eventos": len(plan["events"]), "nuevos": len(plan["new"]), "descartados": plan["discarded"]}


def rebuild_from(session: Session, f: Followup, since: datetime | None, ask: Ask,
                 current: dict[int, dict[str, Any]] | None = None,
                 report: Callable[[float, str], None] = lambda *_: None,
                 current_utts: dict[int, list[dict[str, Any]]] | None = None) -> float:
    """Rehace el estado desde esa fecha: deshace esos vídeos y los vuelve a aplicar en orden.

    `current` y `current_utts` dan el análisis y la transcripción de los vídeos que aún no los tienen en la
    base de datos (el que se está procesando). Devuelve los minutos de vídeo aplicados (para medir lo que
    tarda)."""
    current, current_utts = current or {}, current_utts or {}
    record_version(session, f, "Antes de actualizar con la IA")
    affected = [(fv, v) for fv, v in links(session, f.id) if since is None or date_of(v) >= since]
    linked = {fv.video_id for fv, _ in links(session, f.id)}
    # También lo que aportaron vídeos que ya no están en el seguimiento (se quitaron sin rehacer)
    orphans = {e["video_id"] for it in items(session, f.id) for e in it["events"]
               if e.get("source") == "ia" and e.get("video_id") not in linked
               and (since is None or ((d := F.event_date(e)) is not None and d >= since))}
    revert_videos(session, f, {fv.video_id for fv, _ in affected if fv.applied} | orphans)
    minutes = 0.0
    for i, (_, v) in enumerate(affected):
        analysis = current.get(v.id) or v.analysis
        if not analysis:
            continue  # aún sin analizar: se aplicará al terminar su análisis
        report(i / len(affected), f"«{f.name}»: vídeo {i + 1} de {len(affected)}")
        apply_video(session, f, v, analysis, ask, current_utts.get(v.id))
        minutes += v.duration / 60
    if f.stale_from is not None and (since is None or f.stale_from >= since):
        f.stale_from, f.stale_reason = None, ""
    touch(session, f)
    export(session, f)
    return minutes


def update_for_video(session: Session, video: Video, analysis: dict[str, Any], rebuild: set[int], ask: Ask,
                     report: Callable[[float, str], None] = lambda *_: None, only_rebuild: bool = False,
                     utts: list[dict[str, Any]] | None = None) -> float:
    """Fase «follow»: lo que toca hacer en cada seguimiento de un vídeo recién analizado o regenerado.

    - Si se ha pedido rehacer (o el vídeo es nuevo y es el último por fecha), se rehace desde su fecha.
    - Si no, el estado queda desactualizado desde su fecha: no se puede preguntar desde la cola.

    `only_rebuild`: trabajo que solo rehace los seguimientos pedidos (el análisis no ha cambiado)."""
    minutes = 0.0
    when = date_of(video)
    for f in for_video(session, video.id):
        if only_rebuild and f.id not in rebuild:
            continue
        fv = session.get(FollowupVideo, (f.id, video.id))
        later = [v for x, v in links(session, f.id) if x.applied and v.id != video.id and date_of(v) > when]
        if f.id in rebuild or (f.status == "abierto" and not fv.applied and not later):
            minutes += rebuild_from(session, f, when, ask, {video.id: analysis}, report,
                                    {video.id: utts} if utts is not None else None)
        elif fv.applied:
            mark_stale(session, f, when, f"Se ha regenerado el análisis de «{video.title}» sin rehacer el estado")
        elif not later:
            mark_stale(session, f, when, f"«{video.title}» se analizó con el seguimiento archivado")
        else:
            mark_stale(session, f, when, f"«{video.title}» es anterior a otros vídeos del seguimiento: "
                                         "hay que rehacer el estado para incluirlo en orden")
    return minutes


# --------------------------------------------------------------------------- carpeta exportada

def _folder_name(f: Followup) -> str:
    return f"Seguimiento - {safe_name(f.name)}"


def export(session: Session, f: Followup) -> None:
    """(Re)escribe `Seguimiento - Nombre/seguimiento.md` junto a las carpetas de los vídeos."""
    try:
        root = Path(load_settings().analyzed_dir)
        folder = Path(f.folder) if f.folder else None
        wanted = root / _folder_name(f)
        if folder is None or not folder.exists():
            folder = unique_dir(root, _folder_name(f))
        elif folder.name != wanted.name and not wanted.exists():
            folder = Path(shutil.move(str(folder), str(wanted)))  # renombrado
        folder.mkdir(parents=True, exist_ok=True)
        videos = []
        for fv, v in links(session, f.id):
            link = ""
            if v.folder:
                link = Path(os.path.relpath(v.folder, folder)).as_posix().replace(" ", "%20")
            videos.append({"id": v.id, "title": v.title, "date": date_of(v), "link": link,
                           "contribution": fv.contribution, "applied": fv.applied})
        data = {"name": f.name, "description": f.description, "summary": f.summary, "stale_from": f.stale_from,
                "stale_reason": f.stale_reason}
        (folder / "seguimiento.md").write_text(F.render_markdown(data, items(session, f.id), videos), encoding="utf-8")
        if f.folder != str(folder):
            f.folder = str(folder)
            session.add(f)
            session.commit()
    except OSError:
        log.exception("No se pudo escribir la carpeta del seguimiento %s", f.id)


def delete(session: Session, f: Followup, delete_folder: bool) -> None:
    if delete_folder and f.folder and Path(f.folder).is_dir():
        shutil.rmtree(f.folder, ignore_errors=True)
    session.delete(f)
    session.commit()


# --------------------------------------------------------------------------- para la API

def rebuild_seconds(session: Session, f: Followup, since: datetime | None) -> float:
    """Estimación de lo que tarda rehacer el estado desde esa fecha."""
    minutes = sum(v.duration / 60 for _, v in links(session, f.id)
                  if v.analysis and (since is None or date_of(v) >= since))
    return estimates.rates(session, ["follow"])["follow"] * minutes


def first_from(session: Session, f: Followup, since: datetime | None) -> Video | None:
    """Primer vídeo analizado del seguimiento desde esa fecha: el trabajo que rehace el estado va en él."""
    return next((v for _, v in links(session, f.id)
                 if v.analysis and v.status == "done" and (since is None or date_of(v) >= since)), None)

def busy_job(session: Session, fid: int) -> Job | None:
    """Trabajo en cola o en curso que va a actualizar este seguimiento."""
    for job in session.exec(select(Job).where(Job.status.in_(["queued", "running"]))):
        if fid in (job.options or {}).get("follow_rebuild", []):
            return job
        if session.get(FollowupVideo, (fid, job.video_id)):
            return job
    return None


def out(session: Session, f: Followup, full: bool = False) -> dict[str, Any]:
    ls = links(session, f.id)
    its = items(session, f.id)
    shown = [it for it in its if not it["hidden"]]
    profiles = [v.profile_id for _, v in ls if v.profile_id]
    job = busy_job(session, f.id)
    data = {
        "id": f.id, "name": f.name, "description": f.description, "status": f.status,
        "summary": f.summary, "summary_manual": f.summary_manual,
        "summary_ai": f.summary_ai if f.summary_manual and f.summary_ai != f.summary else "",
        "stale_from": f.stale_from, "stale_reason": f.stale_reason, "folder": f.folder,
        "created_at": f.created_at, "updated_at": f.updated_at,
        "n_videos": len(ls), "last_date": date_of(ls[-1][1]) if ls else None,
        "open_tasks": sum(1 for it in shown if it["kind"] == "tarea" and it["status"] == "abierta"),
        "profile_id": max(set(profiles), key=profiles.count) if profiles else None,
        "busy": bool(job), "job_id": job.id if job else None,
        "rebuild_seconds": round(rebuild_seconds(session, f, f.stale_from)) if f.stale_from else None,
    }
    if full:
        titles = {v.id: v.title for _, v in ls}
        data["videos"] = [{"video_id": v.id, "title": v.title, "date": date_of(v), "duration": v.duration,
                           "status": v.status, "applied": fv.applied, "contribution": fv.contribution}
                          for fv, v in ls]
        data["items"] = [{**it, "events": [{**e, "video_title": titles.get(e.get("video_id"), "")} for e in it["events"]]}
                         for it in shown]
    return data
