"""Conocimiento aprendido en la base de datos: elementos, versiones y restauración.

La lógica sin base de datos está en knowledge.py; aquí solo se lee y escribe.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlmodel import Session, select

from . import knowledge as K
from .models import KnowledgeItem, KnowledgeVersion, Person, Profile, ProfilePersonLink, Speaker, Video
from .models import now as _now
from .pipeline.glossary import normalize


def item_dict(it: KnowledgeItem) -> dict[str, Any]:
    return it.model_dump()


def owner_items(session: Session, profile_id: int | None = None, person_id: int | None = None,
                statuses: tuple[str, ...] | None = None) -> list[KnowledgeItem]:
    """Elementos de un perfil (términos, contexto, secciones) o de una persona (datos, alias)."""
    if profile_id is not None:
        q = select(KnowledgeItem).where(KnowledgeItem.profile_id == profile_id,
                                        KnowledgeItem.kind.in_(K.PROFILE_KINDS))
    else:
        q = select(KnowledgeItem).where(KnowledgeItem.person_id == person_id, KnowledgeItem.kind.in_(K.PERSON_KINDS))
    if statuses:
        q = q.where(KnowledgeItem.status.in_(statuses))
    return list(session.exec(q.order_by(KnowledgeItem.seen_count.desc(), KnowledgeItem.id)))


def accepted(session: Session, profile_id: int | None = None, person_id: int | None = None) -> list[dict[str, Any]]:
    return [item_dict(i) for i in owner_items(session, profile_id, person_id, ("aceptado",))]


# --------------------------------------------------------------------------- versiones

def profile_manual(p: Profile) -> dict[str, Any]:
    return {"name": p.name, "description": p.description, "context": p.context, "extra_prompt": p.extra_prompt,
            "summary_sections": list(p.summary_sections or []), "glossary": list(p.glossary or [])}


def person_manual(p: Person) -> dict[str, Any]:
    return {"name": p.name, "role": p.role, "aliases": list(p.aliases or []), "notes": p.notes}


def profile_person_ids(session: Session, profile_id: int) -> list[int]:
    return list(session.exec(select(ProfilePersonLink.person_id).where(ProfilePersonLink.profile_id == profile_id)))


def snapshot(session: Session, profile_id: int | None = None, person_id: int | None = None) -> dict[str, Any]:
    if profile_id is not None:
        p = session.get(Profile, profile_id)
        return K.make_snapshot(profile_manual(p), accepted(session, profile_id=profile_id),
                               profile_person_ids(session, profile_id))
    p = session.get(Person, person_id)
    return K.make_snapshot(person_manual(p), accepted(session, person_id=person_id))


def _versions_q(profile_id: int | None, person_id: int | None):
    if profile_id is not None:
        return select(KnowledgeVersion).where(KnowledgeVersion.profile_id == profile_id)
    return select(KnowledgeVersion).where(KnowledgeVersion.person_id == person_id)


def ensure_baseline(session: Session, profile_id: int | None = None, person_id: int | None = None) -> None:
    """Antes del primer cambio, guarda el estado actual para poder volver a él."""
    if session.exec(_versions_q(profile_id, person_id)).first() is None:
        session.add(KnowledgeVersion(profile_id=profile_id, person_id=person_id, reason="Estado inicial",
                                     snapshot=snapshot(session, profile_id, person_id)))
        session.commit()


def record_version(session: Session, reason: str, profile_id: int | None = None,
                   person_id: int | None = None) -> KnowledgeVersion | None:
    """Guarda una versión si el estado cambió respecto a la última."""
    snap = snapshot(session, profile_id, person_id)
    last = session.exec(_versions_q(profile_id, person_id).order_by(KnowledgeVersion.id.desc())).first()
    if last and last.snapshot == snap:
        return None
    v = KnowledgeVersion(profile_id=profile_id, person_id=person_id, reason=reason, snapshot=snap)
    session.add(v)
    session.commit()
    return v


def list_versions(session: Session, profile_id: int | None = None, person_id: int | None = None) -> list[dict]:
    rows = list(session.exec(_versions_q(profile_id, person_id).order_by(KnowledgeVersion.id)))
    out = []
    prev = None
    for v in rows:
        out.append({"id": v.id, "created_at": v.created_at, "reason": v.reason,
                    "diff": K.version_diff(prev, v.snapshot) if prev is not None else None})
        prev = v.snapshot
    return out[::-1]


def restore_version(session: Session, version: KnowledgeVersion) -> None:
    profile_id, person_id = version.profile_id, version.person_id
    ensure_baseline(session, profile_id, person_id)
    snap = version.snapshot
    manual = snap.get("manual", {})
    if profile_id is not None:
        p = session.get(Profile, profile_id)
        for k, val in manual.items():
            setattr(p, k, val)
        p.updated_at = _now()
        session.add(p)
        if "person_ids" in snap:
            for link in session.exec(select(ProfilePersonLink).where(ProfilePersonLink.profile_id == profile_id)):
                session.delete(link)
            existing = set(session.exec(select(Person.id)))
            for pid in snap["person_ids"]:
                if pid in existing:
                    session.add(ProfilePersonLink(profile_id=profile_id, person_id=pid))
    else:
        p = session.get(Person, person_id)
        for k, val in manual.items():
            setattr(p, k, val)
        session.add(p)

    items = owner_items(session, profile_id, person_id)
    plan = K.restore_plan(snap, [item_dict(i) for i in items])
    by_id = {i.id: i for i in items}
    now = _now()
    for iid in plan["retire"]:
        by_id[iid].status, by_id[iid].decided_at = "retirado", now
    for iid in plan["accept"]:
        by_id[iid].status, by_id[iid].decided_at = "aceptado", now
    for iid, ch in plan["update"].items():
        by_id[iid].data, by_id[iid].category = ch["data"], ch["category"]
        by_id[iid].key = K.item_key(by_id[iid].kind, ch["data"])
    for it in by_id.values():
        session.add(it)
    for t in plan["create"]:
        session.add(KnowledgeItem(profile_id=profile_id, person_id=person_id, kind=t["kind"],
                                  category=t.get("category", ""), data=t["data"], key=K.item_key(t["kind"], t["data"]),
                                  status="aceptado", decided_at=now))
    session.commit()
    record_version(session, f"Restaurada la versión del {version.created_at:%d/%m/%Y %H:%M}", profile_id, person_id)


# --------------------------------------------------------------------------- propuestas

def speaker_rows(session: Session, video_id: int) -> dict[str, dict[str, Any]]:
    return {sp.label: sp.model_dump() for sp in session.exec(select(Speaker).where(Speaker.video_id == video_id))}


def rejected_texts(session: Session, profile_id: int | None, person_ids: set[int], limit: int = 60) -> list[str]:
    """Lo rechazado del perfil y de las personas del vídeo, para que el LLM no lo vuelva a proponer."""
    conds = [KnowledgeItem.person_id.in_(person_ids)] if person_ids else []
    if profile_id:
        conds.append(KnowledgeItem.profile_id == profile_id)
    if not conds:
        return []
    q = select(KnowledgeItem).where(KnowledgeItem.status == "rechazado", or_(*conds))
    return [K.item_text(r.kind, r.data) for r in session.exec(q.order_by(KnowledgeItem.id.desc()).limit(limit))]


def pending_texts(session: Session, video_id: int, profile_id: int | None, person_ids: set[int],
                  limit: int = 80) -> list[str]:
    """Propuestas pendientes de otros vídeos sobre el perfil y las personas de este.

    Las de este mismo vídeo no se incluyen: la nueva pasada las sustituye (`drop_pending_from`).
    """
    conds = [KnowledgeItem.person_id.in_(person_ids)] if person_ids else []
    if profile_id:
        conds.append(KnowledgeItem.profile_id == profile_id)
    if not conds:
        return []
    q = select(KnowledgeItem).where(KnowledgeItem.status == "propuesto", or_(*conds),
                                    or_(KnowledgeItem.video_id.is_(None), KnowledgeItem.video_id != video_id))
    return [K.item_text(r.kind, r.data) for r in session.exec(q.order_by(KnowledgeItem.id.desc()).limit(limit))]


def _owner_context(session: Session, video_id: int, owner: tuple, profile_id: int | None,
                   speakers: dict[str, dict], auto: float) -> tuple[dict[str, Any], list[KnowledgeItem]]:
    """Campos de dueño de una propuesta nueva y elementos existentes con los que deduplicarla."""
    kind, ref = owner[0], owner[1]
    if kind == "profile":
        return {"profile_id": profile_id}, owner_items(session, profile_id=profile_id) if profile_id else []
    if kind == "person":
        return {"person_id": ref}, owner_items(session, person_id=ref)
    if kind == "speaker":
        existing = list(session.exec(select(KnowledgeItem).where(
            KnowledgeItem.video_id == video_id, KnowledgeItem.speaker_label == ref, KnowledgeItem.person_id.is_(None))))
        pid = K.speaker_person(speakers.get(ref), auto)
        if pid:
            existing += owner_items(session, person_id=pid)
        return {"speaker_label": ref}, existing
    # Persona nueva: una sola propuesta por nombre, venga del vídeo que venga
    return {"profile_id": profile_id}, list(session.exec(select(KnowledgeItem).where(KnowledgeItem.kind == "nueva_persona")))


def _group_new_people(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Los datos de una persona nueva se agrupan en una única propuesta «nueva_persona»."""
    out: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    for p in proposals:
        owner = tuple(p["owner"])
        if owner[0] != "new":
            out.append({**p, "owner": owner})
            continue
        g = by_name.setdefault(normalize(owner[1]), {
            "kind": "nueva_persona", "category": "", "owner": owner, "data": {"name": owner[1], "datos": []},
            "t": p["t"], "lines": p["lines"], "replaces": 0})
        g["data"]["datos"].append({"category": p["category"], "text": p["data"]["text"], "t": p["t"], "lines": p["lines"]})
    return out + list(by_name.values())


def drop_pending_from(session: Session, video_id: int) -> None:
    """Una nueva pasada sobre un vídeo sustituye sus propuestas pendientes anteriores.

    Lo aceptado y lo rechazado se conserva; una propuesta que también viene de otros vídeos solo pierde
    la evidencia de este.
    """
    q = select(KnowledgeItem).where(KnowledgeItem.status == "propuesto")
    for it in session.exec(q):
        ev = it.evidence or []
        rest = [e for e in ev if e.get("video_id") != video_id]
        if len(rest) == len(ev):
            continue
        if rest:
            it.evidence, it.seen_count = rest, max(1, it.seen_count - 1)
            if it.video_id == video_id:
                it.video_id = rest[-1].get("video_id")
            session.add(it)
        else:
            session.delete(it)
    session.flush()


def merge_proposals(session: Session, video_id: int, proposals: list[dict[str, Any]], auto: float) -> dict[str, int]:
    """Guarda las propuestas de un vídeo: une las repetidas, descarta las rechazadas y crea las nuevas."""
    video = session.get(Video, video_id)
    when = video.recorded_at or video.created_at
    speakers = speaker_rows(session, video_id)
    stats = {"nuevas": 0, "repetidas": 0, "descartadas": 0}
    drop_pending_from(session, video_id)
    for p in _group_new_people(proposals):
        fields, existing = _owner_context(session, video_id, p["owner"], video.profile_id, speakers, auto)
        if p["kind"] in K.PROFILE_KINDS and not fields.get("profile_id"):
            continue
        key = K.item_key(p["kind"], p["data"])
        ev = {"video_id": video_id, "t": p["t"], "lines": p["lines"]}
        match = K.find_match(p["kind"], key, [item_dict(i) for i in existing])
        if match:
            it = session.get(KnowledgeItem, match["id"])
            if it.status in ("rechazado", "retirado"):
                stats["descartadas"] += 1
                continue
            it.evidence, is_new = K.add_evidence(list(it.evidence or []), ev)
            if is_new:
                it.seen_count += 1
                it.last_seen_at = max(d for d in (it.last_seen_at, when) if d)
            if p["kind"] == "nueva_persona" and it.status == "propuesto":
                known = {normalize(d["text"]) for d in it.data.get("datos", [])}
                extra = [d for d in p["data"]["datos"] if normalize(d["text"]) not in known]
                it.data = {**it.data, "datos": [*it.data.get("datos", []), *extra]}
            session.add(it)
            stats["repetidas"] += 1
            continue
        replaces = p.get("replaces") or None
        if replaces and not any(i.id == replaces and i.status == "aceptado" for i in existing):
            # Un hablante aún sin resolver puede reemplazar un dato de su futura persona: se valida al aceptar
            target = session.get(KnowledgeItem, replaces) if p["owner"][0] == "speaker" else None
            if not (target and target.status == "aceptado" and target.kind == p["kind"]):
                replaces = None
        session.add(KnowledgeItem(**fields, kind=p["kind"], category=p.get("category", ""), data=p["data"], key=key,
                                  video_id=video_id, replaces_id=replaces, evidence=[ev], last_seen_at=when))
        stats["nuevas"] += 1
    session.commit()
    return stats
