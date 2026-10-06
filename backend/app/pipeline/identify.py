"""Fase 7: propuesta de identidad para cada hablante.

Combina tres fuentes:
- micrófono: si hay pista separada, el hablante que coincide con ella es el dueño;
- voz: similitud con las huellas confirmadas en vídeos anteriores;
- pantalla: nombre del participante resaltado como hablante activo en la videollamada.
El usuario confirma o corrige en la web; cada confirmación añade una huella nueva.
"""

from __future__ import annotations

from typing import Any

from .base import JobContext
from .transcript import speaker_at
from .voice import dominant_visual_name, greedy_assign, match_name, person_centroids, similarity_matrix

VISUAL_CONFIDENCE = 0.7


def visual_hints(turns: list[dict], vision: list[dict]) -> dict[str, dict[str, int]]:
    hints: dict[str, dict[str, int]] = {}
    for v in vision:
        name = (v.get("hablante_activo") or "").strip()
        if not name:
            continue
        label = speaker_at(turns, v["t"])
        if label:
            hints.setdefault(label, {})
            hints[label][name] = hints[label].get(name, 0) + 1
    return hints


def identify(
    labels: list[str],
    embeddings: dict[str, list[float]],
    hints: dict[str, dict[str, int]],
    owner_label: str | None,
    people: list[dict[str, Any]],
    voice_db: dict[int, list[list[float]]],
    owner_name: str,
    match_threshold: float,
    auto_threshold: float,
) -> dict[str, dict[str, Any]]:
    sims = similarity_matrix(embeddings, person_centroids(voice_db)) if voice_db else {}
    by_voice = greedy_assign(sims, match_threshold) if sims else {}
    owner_pid = match_name(owner_name, people)

    out: dict[str, dict[str, Any]] = {}
    for label in labels:
        res: dict[str, Any] = {"person_id": None, "confidence": 0.0, "source": "", "suggested_name": "",
                               "is_owner": label == owner_label, "visual_hints": hints.get(label, {})}
        vname = dominant_visual_name(hints.get(label, {}))
        vpid = match_name(vname, people) if vname else None
        voice = by_voice.get(label)

        if label == owner_label:
            res.update(person_id=owner_pid, confidence=0.95, source="micrófono",
                       suggested_name="" if owner_pid else owner_name)
        elif voice and (voice[1] >= auto_threshold or not vpid or vpid == voice[0]):
            conf = voice[1] if vpid != voice[0] else max(voice[1], 0.9)
            res.update(person_id=voice[0], confidence=round(conf, 3), source="voz")
        elif vpid:
            res.update(person_id=vpid, confidence=VISUAL_CONFIDENCE, source="pantalla")
        elif vname:
            res.update(suggested_name=vname, confidence=VISUAL_CONFIDENCE, source="pantalla")
        out[label] = res
    return out


def run(ctx: JobContext, voice_db: dict[int, list[list[float]]]) -> None:
    diar = ctx.load("diarization.json")
    utts = ctx.load("utterances.json")
    # Orden de aparición (para «Hablante 1, 2...»)
    labels: list[str] = []
    for u in utts:
        if u["speaker"] and u["speaker"] not in labels:
            labels.append(u["speaker"])
    for label in diar["speaking_time"]:
        if label not in labels:
            labels.append(label)

    hints = visual_hints(diar["turns"], ctx.load("vision.json", []))
    ids = identify(
        labels, diar["embeddings"], hints, diar.get("owner"), ctx.people, voice_db,
        ctx.settings.owner_name, ctx.settings.voice_match_threshold, ctx.settings.voice_auto_threshold,
    )
    for i, label in enumerate(labels):
        ids[label]["order"] = i + 1
        ids[label]["speaking_time"] = diar["speaking_time"].get(label, 0.0)
        ids[label]["embedding"] = diar["embeddings"].get(label)
    ctx.save("identities.json", ids)
    known = sum(1 for v in ids.values() if v["person_id"] or v["suggested_name"])
    ctx.report(1.0, f"{known}/{len(labels)} hablantes con identidad propuesta")
