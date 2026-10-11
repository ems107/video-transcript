"""Arreglos manuales de hablantes: «de tal momento a tal momento habla esta persona».

Se guardan por tiempo y persona (`SpeakerOverride`), así que sobreviven a cualquier regeneración: el
worker los aplica a las palabras antes de identificar y de corregir (`pipeline/voices.rebuild`). Al
crearlos o borrarlos, la transcripción de la web se actualiza al momento; el resumen, al regenerar.
"""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from .config import WORK_DIR
from .models import Job, Segment, Speaker, SpeakerOverride, Video
from .pipeline.transcript import assign_speakers, flatten_words
from .pipeline.voices import apply_overrides

MANUAL_PREFIX = "MANUAL_"


def overrides(session: Session, video_id: int) -> list[dict[str, Any]]:
    rows = session.exec(select(SpeakerOverride).where(SpeakerOverride.video_id == video_id)
                        .order_by(SpeakerOverride.id)).all()
    return [{"id": o.id, "start": o.start, "end": o.end, "person_id": o.person_id} for o in rows]


def labels_for(session: Session, video_id: int, items: list[dict[str, Any]]) -> dict[int, str]:
    """Etiqueta de cada persona en el vídeo. Si no tiene, se crea un hablante manual ya confirmado."""
    speakers = list(session.exec(select(Speaker).where(Speaker.video_id == video_id)))
    out = {}
    for pid in dict.fromkeys(o["person_id"] for o in items):
        sp = next((s for s in speakers if s.person_id == pid and s.confirmed), None)
        if sp is None:
            label = f"{MANUAL_PREFIX}{pid}"
            sp = next((s for s in speakers if s.label == label), None)
            if sp is None:
                sp = Speaker(video_id=video_id, label=label, order_idx=max((s.order_idx for s in speakers), default=0) + 1)
                speakers.append(sp)
            sp.person_id, sp.confirmed, sp.source = pid, True, "manual"
            session.add(sp)
        out[pid] = sp.label
    session.commit()
    return out


def apply_splits(session: Session, video_id: int, splits: dict[str, Any]) -> None:
    """Guarda en cada hablante la propuesta de dividirlo (`_split` en `visual_hints`, clave interna)."""
    for sp in session.exec(select(Speaker).where(Speaker.video_id == video_id)):
        hints = {k: v for k, v in (sp.visual_hints or {}).items() if k != "_split"}
        if sp.label in splits:
            hints["_split"] = splits[sp.label]
        sp.visual_hints = hints
        session.add(sp)
    session.commit()


def pending(analysis: dict[str, Any] | None, items: list[dict[str, Any]]) -> bool:
    """Si el análisis actual se generó con otros arreglos de hablantes."""
    return set((analysis or {}).get("hablantes_aplicados") or []) != {o["id"] for o in items}


def words(session: Session, video_id: int) -> list[dict[str, Any]] | None:
    """Palabras con hablante del último trabajo (las de la fase «voices» o, si no, las de pyannote)."""
    job = session.exec(select(Job).where(Job.video_id == video_id).order_by(Job.id.desc())).first()
    wd = WORK_DIR / f"job_{job.id}" if job else None
    if not wd or not wd.is_dir():
        return None
    load = lambda n: json.loads((wd / n).read_text(encoding="utf-8")) if (wd / n).exists() else None
    words = load("words.json")
    if words is None:
        aligned, diar = load("aligned.json"), load("diarization.json")
        if not aligned or not diar:
            return None
        words = assign_speakers(flatten_words(aligned["segments"]), diar["turns"])
    return words


def _split_points(seg: Segment, words: list[dict[str, Any]]) -> list[tuple[float, float, str, str]]:
    """Trocea un segmento por palabras: [(inicio, fin, texto, hablante)], agrupando las consecutivas."""
    mine = [w for w in words if seg.start - 0.05 <= (w["start"] + w["end"]) / 2 <= seg.end + 0.05 and w["word"].strip()]
    tokens = seg.text.split()
    if not mine or not tokens:
        return [(seg.start, seg.end, seg.text, seg.speaker)]
    # El texto mostrado puede estar corregido: se reparte en proporción si no coincide el número de palabras
    idx = [min(len(tokens) - 1, round(i * len(tokens) / len(mine))) for i in range(len(mine))] + [len(tokens)]
    pieces: list[list[Any]] = []
    for i, w in enumerate(mine):
        text = " ".join(tokens[idx[i]: idx[i + 1]])
        if pieces and pieces[-1][3] == w["speaker"]:
            pieces[-1][1], pieces[-1][2] = w["end"], (pieces[-1][2] + " " + text).strip()
        else:
            pieces.append([w["start"], w["end"], text, w["speaker"]])
    pieces[0][0], pieces[-1][1] = seg.start, seg.end
    return [tuple(p) for p in pieces if p[2]]


def refresh_segments(session: Session, video: Video, removed: list[tuple[float, float]] = ()) -> None:
    """Aplica los arreglos actuales a la transcripción guardada, sin regenerar el análisis.

    Solo toca las líneas que solapan con un arreglo o con uno recién borrado (`removed`).
    """
    items = overrides(session, video.id)
    ranges = [(o["start"], o["end"]) for o in items] + list(removed)
    labels = labels_for(session, video.id, items)
    words = globals()["words"](session, video.id)
    segs = list(session.exec(select(Segment).where(Segment.video_id == video.id).order_by(Segment.start)))
    if words is None:  # sin datos de trabajo: solo líneas enteras, por su punto medio
        for seg in segs:
            mid = (seg.start + seg.end) / 2
            hit = next((o for o in reversed(items) if o["start"] <= mid <= o["end"]), None)
            if hit and any(a < seg.end and b > seg.start for a, b in ranges):
                seg.speaker, seg.voice = labels[hit["person_id"]], ""
                session.add(seg)
        session.commit()
        return
    words = apply_overrides(words, items, labels)
    new: list[Segment] = []
    for seg in segs:
        if not any(a < seg.end and b > seg.start for a, b in ranges):
            new.append(seg)
            continue
        pieces = _split_points(seg, words)
        manual = any(o["start"] <= (a + b) / 2 <= o["end"] for a, b, _, _ in pieces for o in items)
        if len(pieces) == 1:
            seg.speaker = pieces[0][3]
            seg.voice = "" if manual else seg.voice
            new.append(seg)
            continue
        session.delete(seg)
        for a, b, text, speaker in pieces:
            new.append(Segment(video_id=video.id, idx=0, start=a, end=b, speaker=speaker, text=text,
                               voice="" if manual else seg.voice))
    for i, seg in enumerate(sorted(new, key=lambda s: s.start)):
        seg.idx = i
        session.add(seg)
    session.commit()
