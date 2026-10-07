"""Revisión de propuestas: listarlas resueltas a su dueño y aplicar las decisiones del usuario."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from . import knowledge as K
from . import knowledge_store as KS
from .models import KnowledgeItem, Person, Profile, ProfilePersonLink, Speaker, Video
from .models import now as _now
from .pipeline.voice import match_name
from .services import speaker_names


class Resolver:
    """Resuelve a qué persona pertenece la propuesta de un hablante y pone nombres a la evidencia."""

    def __init__(self, session: Session, auto: float):
        self.s, self.auto = session, auto
        self._speakers: dict[int, dict[str, dict]] = {}
        self._names: dict[int, dict[str, str]] = {}

    def speakers(self, video_id: int) -> dict[str, dict]:
        if video_id not in self._speakers:
            self._speakers[video_id] = KS.speaker_rows(self.s, video_id)
        return self._speakers[video_id]

    def names(self, video_id: int) -> dict[str, str]:
        if video_id not in self._names:
            self._names[video_id] = speaker_names(self.s, video_id)
        return self._names[video_id]

    def person_of(self, it: KnowledgeItem) -> int | None:
        if it.person_id:
            return it.person_id
        if it.speaker_label and it.video_id:
            return K.speaker_person(self.speakers(it.video_id).get(it.speaker_label), self.auto)
        return None


def _pending(session: Session) -> list[KnowledgeItem]:
    return list(session.exec(select(KnowledgeItem).where(KnowledgeItem.status == "propuesto")
                             .order_by(KnowledgeItem.video_id, KnowledgeItem.id)))


def proposal_out(session: Session, r: Resolver, it: KnowledgeItem, person_id: int | None) -> dict[str, Any]:
    if it.kind in K.PROFILE_KINDS:
        p = session.get(Profile, it.profile_id)
        owner = {"type": "profile", "id": it.profile_id, "name": p.name if p else "?"}
    elif it.kind == "nueva_persona":
        owner = {"type": "new", "id": None, "name": it.data.get("name", "")}
    elif person_id:
        p = session.get(Person, person_id)
        owner = {"type": "person", "id": person_id, "name": p.name if p else "?"}
    else:
        owner = {"type": "speaker", "id": None,
                 "name": r.names(it.video_id).get(it.speaker_label, it.speaker_label) if it.video_id else "?"}
    evidence = []
    for e in it.evidence or []:
        names = r.names(e["video_id"]) if e.get("video_id") else {}
        v = session.get(Video, e["video_id"]) if e.get("video_id") else None
        evidence.append({**e, "video_title": v.title if v else "(vídeo eliminado)",
                         "lines": [{**ln, "name": names.get(ln["label"], ln["label"])} for ln in e.get("lines", [])]})
    replaces = session.get(KnowledgeItem, it.replaces_id) if it.replaces_id else None
    video = session.get(Video, it.video_id) if it.video_id else None
    return {
        **it.model_dump(exclude={"evidence"}), "owner": owner, "evidence": evidence,
        "text": K.item_text(it.kind, it.data), "category_label": K.CATEGORY_LABELS.get(it.category, ""),
        "video_title": video.title if video else "",
        "replaces": {"id": replaces.id, "text": K.item_text(replaces.kind, replaces.data)} if replaces else None,
    }


def list_proposals(session: Session, auto: float, video_id: int | None = None, profile_id: int | None = None,
                   person_id: int | None = None) -> dict[str, list[dict[str, Any]]]:
    """Propuestas pendientes; las de hablantes aún sin identificar con seguridad van en «waiting»."""
    r = Resolver(session, auto)
    ready, waiting = [], []
    for it in _pending(session):
        if video_id is not None and it.video_id != video_id:
            continue
        pid = r.person_of(it) if it.kind in K.PERSON_KINDS else None
        if profile_id is not None and not (it.kind in K.PROFILE_KINDS and it.profile_id == profile_id):
            continue
        if person_id is not None and pid != person_id:
            continue
        out = proposal_out(session, r, it, pid)
        (waiting if it.kind in K.PERSON_KINDS and pid is None else ready).append(out)
    return {"items": ready, "waiting": waiting}


def pending_count(session: Session, auto: float) -> int:
    r = Resolver(session, auto)
    return sum(1 for it in _pending(session) if it.kind not in K.PERSON_KINDS or r.person_of(it))


# --------------------------------------------------------------------------- decisiones

class _Owners:
    """Dueños tocados por una operación: foto antes del primer cambio y versión al final."""

    def __init__(self, session: Session):
        self.s = session
        self.touched: dict[tuple[str, int], int] = {}

    def touch(self, profile_id: int | None = None, person_id: int | None = None) -> None:
        key = ("profile", profile_id) if profile_id else ("person", person_id)
        if key not in self.touched:
            KS.ensure_baseline(self.s, profile_id=profile_id, person_id=person_id)
            self.touched[key] = 0
        self.touched[key] += 1

    def record(self, reason: str) -> None:
        for (kind, oid), n in self.touched.items():
            text = reason.format(n=n, s="" if n == 1 else "s")
            KS.record_version(self.s, text, **({"profile_id": oid} if kind == "profile" else {"person_id": oid}))


def _retire(session: Session, item_id: int | None, owners: _Owners, profile_id=None, person_id=None) -> None:
    it = session.get(KnowledgeItem, item_id) if item_id else None
    if it and it.status == "aceptado" and it.profile_id == profile_id and it.person_id == person_id:
        it.status, it.decided_at = "retirado", _now()
        session.add(it)


def _accept_person_item(session: Session, it: KnowledgeItem, pid: int, owners: _Owners) -> None:
    owners.touch(person_id=pid)
    existing = [KS.item_dict(i) for i in KS.owner_items(session, person_id=pid, statuses=("aceptado",))]
    match = K.find_match(it.kind, it.key, existing)
    if match:  # ya lo sabíamos: se suma la evidencia y se descarta el duplicado
        known = session.get(KnowledgeItem, match["id"])
        for ev in it.evidence or []:
            known.evidence, is_new = K.add_evidence(list(known.evidence or []), ev)
            known.seen_count += int(is_new)
        session.add(known)
        session.delete(it)
        return
    it.person_id, it.status, it.decided_at = pid, "aceptado", _now()
    session.add(it)
    for old in K.single_value_conflicts(KS.item_dict(it), existing):
        _retire(session, old, owners, person_id=pid)
    _retire(session, it.replaces_id, owners, person_id=pid)


def _accept_new_person(session: Session, it: KnowledgeItem, owners: _Owners) -> int:
    name = it.data.get("name", "").strip()
    people = [{"id": p.id, "name": p.name, "aliases": p.aliases or []} for p in session.exec(select(Person))]
    pid = match_name(name, people)
    if pid is None:
        person = Person(name=name)
        session.add(person)
        session.commit()
        pid = person.id
        KS.record_version(session, "Creada desde un vídeo", person_id=pid)
    if it.profile_id and not session.get(ProfilePersonLink, (it.profile_id, pid)):
        owners.touch(profile_id=it.profile_id)
        session.add(ProfilePersonLink(profile_id=it.profile_id, person_id=pid))
    for d in it.data.get("datos", []):
        data = {"text": d["text"]}
        fact = KnowledgeItem(person_id=pid, kind="dato", category=d.get("category", "otro"), data=data,
                             key=K.item_key("dato", data), video_id=it.video_id, last_seen_at=it.last_seen_at,
                             evidence=[{"video_id": it.video_id, "t": d.get("t"), "lines": d.get("lines", [])}])
        session.add(fact)
        session.flush()
        _accept_person_item(session, fact, pid, owners)
    it.status, it.decided_at, it.data = "aceptado", _now(), {**it.data, "person_id": pid}
    session.add(it)
    return pid


def apply_edit(it: KnowledgeItem, edit: dict[str, Any]) -> None:
    data = dict(it.data)
    for k in ("text", "term", "definition", "title", "name"):
        if k in edit and isinstance(edit[k], str):
            data[k] = edit[k].strip()
    it.data = data
    if edit.get("category") in (*K.PROFILE_CATEGORIES, *K.PERSON_CATEGORIES):
        it.category = edit["category"]
    it.key = K.item_key(it.kind, data)


def decide(session: Session, auto: float, accept: list[int], reject: list[int],
           edits: dict[int, dict[str, Any]]) -> dict[str, Any]:
    owners = _Owners(session)
    r = Resolver(session, auto)
    done = {"aceptadas": 0, "rechazadas": 0, "en_espera": 0}
    for iid in reject:
        it = session.get(KnowledgeItem, iid)
        if it and it.status == "propuesto":
            it.status, it.decided_at = "rechazado", _now()
            session.add(it)
            done["rechazadas"] += 1
    for iid in accept:
        it = session.get(KnowledgeItem, iid)
        if not it or it.status != "propuesto":
            continue
        if iid in edits:
            apply_edit(it, edits[iid])
        if it.kind in K.PROFILE_KINDS:
            owners.touch(profile_id=it.profile_id)
            it.status, it.decided_at = "aceptado", _now()
            session.add(it)
            _retire(session, it.replaces_id, owners, profile_id=it.profile_id)
        elif it.kind == "nueva_persona":
            _accept_new_person(session, it, owners)
        else:
            pid = r.person_of(it)
            if pid is None:
                done["en_espera"] += 1
                continue
            _accept_person_item(session, it, pid, owners)
        done["aceptadas"] += 1
    session.commit()
    owners.record("Aceptada{s} {n} propuesta{s}")
    return done


def update_item(session: Session, it: KnowledgeItem, edit: dict[str, Any]) -> None:
    owners = _Owners(session)
    owners.touch(profile_id=it.profile_id if it.kind in K.PROFILE_KINDS else None, person_id=it.person_id)
    apply_edit(it, edit)
    session.add(it)
    session.commit()
    owners.record("Editado un dato aprendido")


def retire_item(session: Session, it: KnowledgeItem) -> None:
    owners = _Owners(session)
    owners.touch(profile_id=it.profile_id if it.kind in K.PROFILE_KINDS else None, person_id=it.person_id)
    it.status, it.decided_at = "retirado", _now()
    session.add(it)
    session.commit()
    owners.record("Retirado un dato aprendido")


def forget_video(session: Session, video_id: int) -> dict[str, int]:
    """Deshace lo aprendido de un vídeo: retira lo que solo venía de él y quita su evidencia del resto."""
    owners = _Owners(session)
    stats = {"retirados": 0, "rechazados": 0, "actualizados": 0}
    q = select(KnowledgeItem).where(KnowledgeItem.status.in_(("propuesto", "aceptado")),
                                    KnowledgeItem.kind.in_((*K.PROFILE_KINDS, *K.PERSON_KINDS, "nueva_persona")))
    for it in session.exec(q):
        if it.kind == "nueva_persona" and it.status == "aceptado":
            continue  # la persona ya se creó; sus datos se tratan como los de cualquier persona
        ev = it.evidence or []
        from_video = [e for e in ev if e.get("video_id") == video_id]
        if not from_video and it.video_id != video_id:
            continue
        rest = [e for e in ev if e.get("video_id") != video_id]
        is_profile = it.kind in K.PROFILE_KINDS
        if it.status == "aceptado":
            owners.touch(profile_id=it.profile_id if is_profile else None, person_id=None if is_profile else it.person_id)
        if rest:
            it.evidence, it.seen_count = rest, max(1, it.seen_count - len(from_video))
            stats["actualizados"] += 1
        elif it.status == "aceptado":
            it.status, it.decided_at = "retirado", _now()
            stats["retirados"] += 1
        else:
            it.status, it.decided_at = "rechazado", _now()
            stats["rechazados"] += 1
        session.add(it)
    session.commit()
    owners.record("Olvidado lo aprendido de un vídeo")
    return stats


def reassign_speaker_items(session: Session, video_id: int, label: str, old_pid: int, new_pid: int | None) -> None:
    """Si un hablante se reasigna, lo aprendido de él pasa a la nueva persona."""
    items = list(session.exec(select(KnowledgeItem).where(
        KnowledgeItem.video_id == video_id, KnowledgeItem.speaker_label == label, KnowledgeItem.person_id == old_pid)))
    if not items:
        return
    owners = _Owners(session)
    owners.touch(person_id=old_pid)
    for it in items:
        if new_pid is None:
            it.person_id = None
            if it.status == "aceptado":
                it.status = "propuesto"
            session.add(it)
            continue
        if it.status == "aceptado":
            it.person_id = None
            it.status = "propuesto"
            session.add(it)
            session.flush()
            _accept_person_item(session, it, new_pid, owners)
        else:
            it.person_id = None
            session.add(it)
    session.commit()
    owners.record("Reasignado un hablante")


def link_to_profile(session: Session, video: Video, person_id: int) -> None:
    if video.profile_id and not session.get(ProfilePersonLink, (video.profile_id, person_id)):
        KS.ensure_baseline(session, profile_id=video.profile_id)
        session.add(ProfilePersonLink(profile_id=video.profile_id, person_id=person_id))
        session.commit()
        KS.record_version(session, "Persona confirmada en un vídeo", profile_id=video.profile_id)


def speaker_persons(session: Session, video_id: int) -> list[int]:
    return [sp.person_id for sp in session.exec(select(Speaker).where(Speaker.video_id == video_id)) if sp.person_id]
