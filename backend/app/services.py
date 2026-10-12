"""Operaciones sobre la base de datos compartidas por la API y el worker."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from . import followups_store
from . import knowledge_store as KS
from .models import (
    Keyframe,
    KnowledgeItem,
    Person,
    Profile,
    ProfilePersonLink,
    Segment,
    Speaker,
    Video,
    VideoCorrection,
    VoiceEmbedding,
)
from .pipeline.export import write_outputs
from .pipeline.glossary import normalize
from .pipeline.transcript import fmt_ts
from .pipeline.voice import match_name


def profile_dict(session: Session, profile_id: int | None) -> dict[str, Any] | None:
    if not profile_id:
        return None
    p = session.get(Profile, profile_id)
    if not p:
        return None
    learned = [{"id": i.id, "kind": i.kind, "category": i.category, "data": i.data, "seen_count": i.seen_count}
               for i in KS.owner_items(session, profile_id=profile_id, statuses=("aceptado",))]
    return {**p.model_dump(), "learned": learned}


def people_for(session: Session, profile_id: int | None) -> list[dict[str, Any]]:
    """Personas del perfil primero; después el resto. Incluye lo aprendido (otros nombres y datos)."""
    linked = set()
    if profile_id:
        linked = set(session.exec(select(ProfilePersonLink.person_id).where(ProfilePersonLink.profile_id == profile_id)))
    learned: dict[int, list[KnowledgeItem]] = {}
    q = select(KnowledgeItem).where(KnowledgeItem.person_id.is_not(None), KnowledgeItem.status == "aceptado")
    for it in session.exec(q.order_by(KnowledgeItem.seen_count.desc(), KnowledgeItem.id.desc())):
        learned.setdefault(it.person_id, []).append(it)
    rows = []
    for p in session.exec(select(Person)):
        items = learned.get(p.id, [])
        aliases = list(p.aliases or []) + [i.data.get("name", "") for i in items if i.kind == "alias"]
        facts = [{"id": i.id, "category": i.category, "text": i.data.get("text", "")} for i in items if i.kind == "dato"]
        rows.append({"id": p.id, "name": p.name, "role": p.role, "notes": p.notes, "aliases": [a for a in aliases if a],
                     "facts": facts, "in_profile": p.id in linked})
    return sorted(rows, key=lambda r: (not r["in_profile"], r["name"]))


def video_person_ids(session: Session, video_id: int) -> set[int]:
    """Personas confirmadas o propuestas como hablantes de un vídeo."""
    return {sp.person_id or sp.suggested_person_id
            for sp in session.exec(select(Speaker).where(Speaker.video_id == video_id))
            if sp.person_id or sp.suggested_person_id}


def voice_db(session: Session) -> dict[int, list[list[float]]]:
    out: dict[int, list[list[float]]] = {}
    for e in session.exec(select(VoiceEmbedding)):
        out.setdefault(e.person_id, []).append(e.vector)
    return out


def speaker_names(session: Session, video_id: int) -> dict[str, str]:
    """Nombre a mostrar de cada hablante: persona confirmada > propuesta > nombre en pantalla > «Hablante N»."""
    names = {}
    for sp in session.exec(select(Speaker).where(Speaker.video_id == video_id)):
        pid = sp.person_id or sp.suggested_person_id
        person = session.get(Person, pid) if pid else None
        names[sp.label] = person.name if person else (sp.suggested_name or f"Hablante {sp.order_idx}")
    return names


def video_corrections(session: Session, video_id: int) -> list[dict[str, Any]]:
    rows = session.exec(select(VideoCorrection).where(VideoCorrection.video_id == video_id)
                        .order_by(VideoCorrection.id)).all()
    return [{"id": c.id, "text": c.text, "updated_at": c.updated_at.isoformat()} for c in rows]


def corrections_applied(corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lo que se guarda en el análisis para saber con qué correcciones se generó."""
    return [{"id": c["id"], "updated_at": c["updated_at"]} for c in corrections]


def with_applied(analysis: dict[str, Any] | None, corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Marca cada corrección según si el análisis actual se generó con ella (con ese mismo texto)."""
    used = {(c["id"], c["updated_at"]) for c in (analysis or {}).get("correcciones_aplicadas") or []}
    return [{**c, "applied": (c["id"], c["updated_at"]) in used} for c in corrections]


def corrections_pending(analysis: dict[str, Any] | None, corrections: list[dict[str, Any]]) -> bool:
    """Si las correcciones actuales no son las que se usaron al generar el análisis."""
    used = (analysis or {}).get("correcciones_aplicadas") or []
    return {(c["id"], c["updated_at"]) for c in used} != {(c["id"], c["updated_at"]) for c in corrections}


CONTEXT_CONFIDENCE = 0.5


def speaker_status(session: Session, video_id: int) -> dict[str, str]:
    """Cómo se sabe quién es cada hablante, para el contexto del LLM."""
    out = {}
    for sp in session.exec(select(Speaker).where(Speaker.video_id == video_id)):
        if sp.person_id and sp.confirmed:
            out[sp.label] = "confirmado"
        elif sp.person_id or sp.suggested_person_id or sp.suggested_name:
            out[sp.label] = f"probable, por {sp.source or 'propuesta'}; sin confirmar"
        else:
            out[sp.label] = ""
    return out


def apply_context_identities(session: Session, video_id: int, found: dict[str, Any],
                             people: list[dict[str, Any]]) -> None:
    """Propone el nombre deducido del contexto a los hablantes que no tienen ninguno. Nunca confirma.

    Las pistas internas (motivo, apodos) se guardan en `visual_hints` con claves que empiezan por «_»,
    que el resto del código ignora.
    """
    identities, nicknames = found.get("identidades") or {}, found.get("apodos") or {}
    evaluated = set(found.get("evaluados") or [])
    names = speaker_names(session, video_id)
    for sp in session.exec(select(Speaker).where(Speaker.video_id == video_id)):
        hints = dict(sp.visual_hints or {})
        d = identities.get(sp.label)
        free = not sp.confirmed and not sp.person_id and (
            sp.source == "contexto" or not (sp.suggested_person_id or sp.suggested_name))
        if free and d:
            pid = match_name(d["nombre"], people) if people else None
            sp.suggested_person_id, sp.suggested_name = (pid, "") if pid else (None, d["nombre"])
            sp.source, sp.confidence = "contexto", CONTEXT_CONFIDENCE
            hints["_motivo"] = f"{d.get('motivo', '')} ({d['t']})" if d.get("t") else d.get("motivo", "")
        elif free and sp.source == "contexto" and sp.label in evaluated:
            # Solo se retira si se ha vuelto a evaluar y ya no se sostiene (al regenerar, los hablantes
            # con propuesta ya no figuran como «Hablante N» y no se evalúan de nuevo)
            sp.suggested_person_id, sp.suggested_name, sp.source, sp.confidence = None, "", "", 0.0
            hints.pop("_motivo", None)
        shown = d["nombre"] if free and d else names.get(sp.label, "")
        alias = next((a for name, a in nicknames.items() if normalize(name) == normalize(shown)), None)
        hints.pop("_apodos", None)  # los apodos se recalculan con todo el vídeo en cada pasada
        if alias:
            hints["_apodos"] = alias
        sp.visual_hints = hints
        session.add(sp)
    session.commit()


def persist_speakers(session: Session, video_id: int, identities: dict[str, dict[str, Any]]) -> None:
    """Guarda la identificación. Al repetirla, los hablantes confirmados conservan su persona.

    Solo cambian las propuestas de los que no están confirmados; las etiquetas que ya no existen se borran.
    """
    existing = {sp.label: sp for sp in session.exec(select(Speaker).where(Speaker.video_id == video_id))}
    for label, sp in existing.items():
        if label not in identities:
            session.delete(sp)
    for label, d in identities.items():
        sp = existing.get(label) or Speaker(video_id=video_id, label=label)
        sp.order_idx, sp.is_owner, sp.speaking_time, sp.embedding = (
            d["order"], d["is_owner"], d["speaking_time"], d["embedding"])
        sp.visual_hints = dict(d["visual_hints"])
        if not sp.confirmed:
            sp.suggested_person_id, sp.suggested_name = d["person_id"], d["suggested_name"]
            sp.source, sp.confidence = d["source"], d["confidence"]
        session.add(sp)
    session.commit()


def rename_speakers(analysis: Any, before: dict[str, str], after: dict[str, str]) -> Any:
    """Sustituye en el análisis los «Hablante N» que ahora tienen nombre (solo esos: ver replace_speaker_name)."""
    for label, old in before.items():
        new = after.get(label, old)
        if new != old:
            analysis = replace_speaker_name(analysis, old, new)
    return analysis


def replace_speaker_name(analysis: Any, old: str, new: str) -> Any:
    """Sustituye «Hablante N» por el nombre real en los textos del análisis."""
    if not re.fullmatch(r"Hablante \d+", old):
        return analysis
    pat = re.compile(rf"\b{re.escape(old)}\b")
    if isinstance(analysis, str):
        return pat.sub(new, analysis)
    if isinstance(analysis, list):
        return [replace_speaker_name(x, old, new) for x in analysis]
    if isinstance(analysis, dict):
        return {k: replace_speaker_name(v, old, new) for k, v in analysis.items()}
    return analysis


def video_meta(session: Session, video: Video) -> dict[str, Any]:
    names = speaker_names(session, video.id)
    sps = session.exec(select(Speaker).where(Speaker.video_id == video.id).order_by(Speaker.order_idx)).all()
    profile = session.get(Profile, video.profile_id) if video.profile_id else None
    return {
        "title": video.title,
        "date": (video.recorded_at or video.created_at).strftime("%Y-%m-%d %H:%M"),
        "duration": fmt_ts(video.duration),
        "profile": profile.name if profile else "",
        "participants": [names[s.label] for s in sps if s.label in names],
        "source": video.source_path,
        "followups": _followup_links(session, video),
    }


def _followup_links(session: Session, video: Video) -> list[tuple[str, str]]:
    """(nombre, ruta relativa a su `seguimiento.md`) de los seguimientos del vídeo, para sus documentos."""
    out = []
    for f in followups_store.for_video(session, video.id):
        link = ""
        if f.folder and video.folder:
            link = Path(os.path.relpath(Path(f.folder) / "seguimiento.md", video.folder)).as_posix().replace(" ", "%20")
        out.append((f.name, link))
    return out


def export_video(session: Session, video: Video) -> None:
    """(Re)escribe los documentos de la carpeta del vídeo con los nombres actuales."""
    if not video.folder or not Path(video.folder).is_dir():
        return  # sin publicar, o el usuario ha movido o borrado la carpeta: no se vuelve a crear
    names = speaker_names(session, video.id)
    segs = session.exec(select(Segment).where(Segment.video_id == video.id).order_by(Segment.idx)).all()
    utts = [{"start": s.start, "end": s.end, "speaker": s.speaker, "text": s.text} for s in segs]
    frames = session.exec(select(Keyframe).where(Keyframe.video_id == video.id).order_by(Keyframe.t)).all()
    extra = {"pantalla": [{"t": fmt_ts(k.t), "tipo": k.scene_type, "descripcion": k.description,
                           "texto": k.visible_text, "archivo": Path(k.path).name} for k in frames]}
    analysis = {k: v for k, v in (video.analysis or {}).items() if k != "fragmentos"}
    write_outputs(Path(video.folder), video_meta(session, video), utts, names, analysis, extra)


def index_video(session: Session, video: Video) -> None:
    """Reindexa en FTS5 el título, el resumen, la transcripción y la pantalla de un vídeo."""
    conn = session.connection()
    conn.execute(text("DELETE FROM search_fts WHERE video_id = :v"), {"v": video.id})
    names = speaker_names(session, video.id)
    rows = [{"text": video.title, "kind": "title", "ref": None, "t": 0.0, "sp": ""}]
    a = video.analysis or {}
    summary = "\n".join(filter(None, [a.get("resumen_breve", ""), a.get("resumen_detallado", "")]))
    if summary:
        rows.append({"text": summary, "kind": "summary", "ref": None, "t": 0.0, "sp": ""})
    for s in session.exec(select(Segment).where(Segment.video_id == video.id)):
        rows.append({"text": s.text, "kind": "segment", "ref": s.id, "t": s.start, "sp": names.get(s.speaker, s.speaker)})
    for k in session.exec(select(Keyframe).where(Keyframe.video_id == video.id)):
        t = " ".join(filter(None, [k.description, k.visible_text]))
        if t:
            rows.append({"text": t, "kind": "frame", "ref": k.id, "t": k.t, "sp": ""})
    conn.execute(
        text("INSERT INTO search_fts (text, kind, video_id, ref_id, t, speaker) VALUES (:text, :kind, :v, :ref, :t, :sp)"),
        [{**r, "v": video.id} for r in rows],
    )
    session.commit()


def person_video_ids(session: Session, person_id: int) -> list[int]:
    q = select(Speaker.video_id).where((Speaker.person_id == person_id) | (Speaker.suggested_person_id == person_id))
    return sorted(set(session.exec(q)))


def refresh_person_videos(session: Session, person_id: int) -> None:
    """Reescribe e indexa los vídeos en los que aparece una persona (tras renombrarla o fusionarla)."""
    for vid in person_video_ids(session, person_id):
        video = session.get(Video, vid)
        if video and video.folder:
            export_video(session, video)
            index_video(session, video)
