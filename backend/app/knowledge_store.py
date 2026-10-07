"""Conocimiento aprendido en la base de datos: elementos, versiones y restauración.

La lógica sin base de datos está en knowledge.py; aquí solo se lee y escribe.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from . import knowledge as K
from .models import KnowledgeItem, KnowledgeVersion, Person, Profile, ProfilePersonLink
from .models import now as _now


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
