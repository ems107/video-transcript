"""Lógica pura sobre la transcripción: asignar hablantes a palabras y construir intervenciones."""

from __future__ import annotations

import bisect
from typing import Any

Word = dict[str, Any]
Turn = dict[str, Any]


def fmt_ts(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def flatten_words(segments: list[dict[str, Any]]) -> list[Word]:
    """Extrae las palabras de los segmentos alineados rellenando tiempos que falten.

    WhisperX no alinea algunos tokens (números, símbolos): se les asigna el tiempo
    de la palabra vecina o, en su defecto, los límites del segmento.
    """
    out: list[Word] = []
    for seg in segments:
        words = seg.get("words") or []
        if not words:
            out.append({"word": seg["text"].strip(), "start": seg["start"], "end": seg["end"]})
            continue
        n = len(words)
        for i, w in enumerate(words):
            start = w.get("start")
            end = w.get("end")
            if start is None:
                prev_end = next((words[j]["end"] for j in range(i - 1, -1, -1) if words[j].get("end") is not None), None)
                start = prev_end if prev_end is not None else seg["start"]
            if end is None:
                next_start = next((words[j]["start"] for j in range(i + 1, n) if words[j].get("start") is not None), None)
                end = next_start if next_start is not None else seg["end"]
            end = max(end, start)
            out.append({"word": w["word"], "start": float(start), "end": float(end)})
    return out


def assign_speakers(words: list[Word], turns: list[Turn], max_distance: float = 2.0) -> list[Word]:
    """Asigna a cada palabra el hablante con mayor solape temporal.

    Si no solapa con ningún turno, se usa el turno más cercano (si está a menos de
    `max_distance` segundos) o el hablante de la palabra anterior.
    """
    turns = sorted(turns, key=lambda t: t["start"])
    starts = [t["start"] for t in turns]
    prev_speaker = ""
    for w in words:
        best, best_ov = None, 0.0
        # Turnos candidatos: los que empiezan antes del final de la palabra
        hi = bisect.bisect_right(starts, w["end"])
        for t in turns[max(0, hi - 50) : hi]:
            ov = min(w["end"], t["end"]) - max(w["start"], t["start"])
            if ov > best_ov:
                best, best_ov = t, ov
        if best is None and turns:
            mid = (w["start"] + w["end"]) / 2
            nearest = min(
                turns[max(0, hi - 2) : hi + 2] or turns,
                key=lambda t: 0 if t["start"] <= mid <= t["end"] else min(abs(mid - t["start"]), abs(mid - t["end"])),
            )
            dist = min(abs(mid - nearest["start"]), abs(mid - nearest["end"]))
            if dist <= max_distance or not prev_speaker:
                best = nearest
        w["speaker"] = best["speaker"] if best else prev_speaker
        prev_speaker = w["speaker"]
    return words


SENTENCE_END = (".", "?", "!", "…")
BORDER = 0.3  # segundos: un instante tan cerca del límite de un turno se considera en el borde


def build_utterances(words: list[Word], max_gap: float = 1.5, max_duration: float = 30.0) -> list[dict[str, Any]]:
    """Agrupa palabras consecutivas del mismo hablante en intervenciones.

    Se corta cuando cambia el hablante, cuando hay una pausa larga, o cuando la
    intervención supera `max_duration` y la palabra cierra una frase.
    """
    utts: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for w in words:
        text = w["word"].strip()
        if not text:
            continue
        new = (
            cur is None
            or w.get("speaker", "") != cur["speaker"]
            or w["start"] - cur["end"] > max_gap
            or (cur["end"] - cur["start"] > max_duration and cur["text"].endswith(SENTENCE_END))
        )
        if new:
            cur = {"start": w["start"], "end": w["end"], "speaker": w.get("speaker", ""), "text": text}
            utts.append(cur)
        else:
            cur["text"] += " " + text
            cur["end"] = max(cur["end"], w["end"])
    return utts


def speaking_time(turns: list[Turn]) -> dict[str, float]:
    total: dict[str, float] = {}
    for t in turns:
        total[t["speaker"]] = total.get(t["speaker"], 0.0) + (t["end"] - t["start"])
    return total


def speaker_at(turns: list[Turn], t: float, tolerance: float = BORDER) -> str | None:
    """Hablante en el instante `t`.

    Cuentan los turnos que lo contienen o que están a menos de `tolerance` segundos. Gana el que lo tiene
    más dentro; si está a menos de BORDER de un límite es el borde, y en el borde gana el que empieza
    (quien empieza a hablar es quien aparece resaltado).
    """
    cands = [x for x in turns if x["start"] - tolerance <= t <= x["end"] + tolerance]
    if not cands:
        return None

    def depth(x: Turn) -> tuple[float, float]:
        margin = min(t - x["start"], x["end"] - t)
        return (margin if margin >= BORDER else 0.0, x["start"])

    return max(cands, key=depth)["speaker"]


def group_turns(utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Une intervenciones consecutivas del mismo hablante (para documentos legibles)."""
    out: list[dict[str, Any]] = []
    for u in utterances:
        if out and out[-1]["speaker"] == u["speaker"] and u["start"] - out[-1]["end"] < 5:
            out[-1]["text"] += " " + u["text"]
            out[-1]["end"] = u["end"]
        else:
            out.append(dict(u))
    return out
