"""Fichas de persona: datos calculados, posibles duplicados y fusión de dos personas."""

from __future__ import annotations

import re
from typing import Any

from sqlmodel import Session, select

from . import knowledge as K
from . import knowledge_store as KS
from . import services
from .models import (
    KnowledgeItem,
    KnowledgeVersion,
    Person,
    PersonPairDismissal,
    Profile,
    ProfilePersonLink,
    Speaker,
    Video,
    VoiceEmbedding,
)
from .pipeline.glossary import normalize
from .pipeline.voice import match_name, person_centroids


def person_detail(session: Session, p: Person) -> dict[str, Any]:
    """Vídeos, tiempo hablado, última aparición, tareas asignadas y perfiles de una persona."""
    who = [{"id": p.id, "name": p.name, "aliases": list(p.aliases or [])
            + [i.data.get("name", "") for i in KS.owner_items(session, person_id=p.id, statuses=("aceptado",))
               if i.kind == "alias"]}]
    videos, tasks, talk = [], [], 0.0
    q = select(Speaker).where((Speaker.person_id == p.id) | (Speaker.suggested_person_id == p.id))
    seen: set[int] = set()
    for sp in session.exec(q):
        v = session.get(Video, sp.video_id)
        if not v or v.id in seen:
            continue
        seen.add(v.id)
        confirmed = sp.person_id == p.id and sp.confirmed
        if confirmed:
            talk += sp.speaking_time
        videos.append({"id": v.id, "title": v.title, "date": v.recorded_at or v.created_at, "confirmed": confirmed,
                       "speaking_time": sp.speaking_time, "status": v.status})
        for task in (v.analysis or {}).get("tareas") or []:
            if task.get("responsable") and match_name(task["responsable"], who) is not None:
                tasks.append({**task, "video_id": v.id, "video_title": v.title, "date": v.recorded_at or v.created_at})
    videos.sort(key=lambda x: x["date"], reverse=True)
    tasks.sort(key=lambda x: x["date"], reverse=True)
    profile_ids = session.exec(select(ProfilePersonLink.profile_id).where(ProfilePersonLink.person_id == p.id))
    profiles = [{"id": pr.id, "name": pr.name} for pr in (session.get(Profile, i) for i in profile_ids) if pr]
    return {
        "videos": videos, "tasks": tasks, "profiles": profiles,
        "stats": {"videos": len(videos), "confirmed_videos": sum(1 for v in videos if v["confirmed"]),
                  "speaking_time": talk, "last_seen": videos[0]["date"] if videos else None},
    }


def duplicates(session: Session) -> list[dict[str, Any]]:
    people = list(session.exec(select(Person)))
    rows = [{"id": p.id, "name": p.name, "aliases": list(p.aliases or [])} for p in people]
    voices: dict[int, list[list[float]]] = {}
    for e in session.exec(select(VoiceEmbedding)):
        voices.setdefault(e.person_id, []).append(e.vector)
    dismissed = {(d.a, d.b) for d in session.exec(select(PersonPairDismissal))}
    names = {p.id: p.name for p in people}
    out = []
    for d in K.duplicate_candidates(rows, person_centroids(voices)):
        pair = (min(d["a"], d["b"]), max(d["a"], d["b"]))
        if pair not in dismissed:
            out.append({**d, "a_name": names[d["a"]], "b_name": names[d["b"]]})
    return out


def dismiss(session: Session, a: int, b: int) -> None:
    pair = (min(a, b), max(a, b))
    if not session.get(PersonPairDismissal, pair):
        session.add(PersonPairDismissal(a=pair[0], b=pair[1]))
        session.commit()


def replace_name(analysis: Any, old: str, new: str) -> Any:
    """Sustituye un nombre por otro en el análisis, salvo que el antiguo ya forme parte del nuevo."""
    if not old or set(normalize(old).split()) <= set(normalize(new).split()):
        return analysis
    pat = re.compile(rf"\b{re.escape(old)}\b")
    if isinstance(analysis, str):
        return pat.sub(new, analysis)
    if isinstance(analysis, list):
        return [replace_name(x, old, new) for x in analysis]
    if isinstance(analysis, dict):
        return {k: replace_name(v, old, new) for k, v in analysis.items()}
    return analysis


def merge(session: Session, source: Person, target: Person) -> None:
    """Fusiona `source` en `target`: voz, hablantes, perfiles, conocimiento y nombres. `source` se elimina.

    El historial de `source` no se conserva (sus versiones no tienen sentido aplicadas a `target`);
    la fusión queda registrada como una versión de `target`.
    """
    KS.ensure_baseline(session, person_id=target.id)
    video_ids = services.person_video_ids(session, source.id)
    for e in session.exec(select(VoiceEmbedding).where(VoiceEmbedding.person_id == source.id)):
        e.person_id = target.id
        session.add(e)
    for sp in session.exec(select(Speaker).where(
            (Speaker.person_id == source.id) | (Speaker.suggested_person_id == source.id))):
        if sp.person_id == source.id:
            sp.person_id = target.id
        if sp.suggested_person_id == source.id:
            sp.suggested_person_id = target.id
        session.add(sp)
    for link in session.exec(select(ProfilePersonLink).where(ProfilePersonLink.person_id == source.id)):
        if not session.get(ProfilePersonLink, (link.profile_id, target.id)):
            session.add(ProfilePersonLink(profile_id=link.profile_id, person_id=target.id))
        session.delete(link)
    target_items = [KS.item_dict(i) for i in KS.owner_items(session, person_id=target.id)]
    for it in KS.owner_items(session, person_id=source.id):
        match = K.find_match(it.kind, it.key, [t for t in target_items if t["status"] == it.status])
        if match and it.status == "aceptado":
            known = session.get(KnowledgeItem, match["id"])
            for ev in it.evidence or []:
                known.evidence, is_new = K.add_evidence(list(known.evidence or []), ev)
                known.seen_count += int(is_new)
            session.add(known)
            session.delete(it)
        else:
            it.person_id = target.id
            session.add(it)
    target.aliases = K.merged_aliases(KS.person_manual(target), KS.person_manual(source))
    target.role = target.role or source.role
    target.notes = "\n".join(n for n in (target.notes, source.notes) if n)
    session.add(target)
    session.commit()

    for v in (session.get(Video, i) for i in video_ids):
        if v and v.analysis:
            v.analysis = replace_name(v.analysis, source.name, target.name)
            v.summary_md = v.analysis.get("resumen_breve", v.summary_md)
            session.add(v)
    old_name = source.name
    for ver in session.exec(select(KnowledgeVersion).where(KnowledgeVersion.person_id == source.id)):
        session.delete(ver)
    session.delete(source)
    session.commit()
    KS.record_version(session, f"Fusionada con «{old_name}»", person_id=target.id)
    for vid in video_ids:
        v = session.get(Video, vid)
        if v and v.folder:
            services.export_video(session, v)
            services.index_video(session, v)
