"""Fase «voiceprints»: huellas y muestras de voz de las personas confirmadas, al aplicar la revisión.

La huella de cada persona se calcula con sus intervenciones tal como quedan después de los arreglos del
usuario (no con el hablante que separó pyannote): así, si una persona estaba mezclada con otra, su voz no
contamina la huella de la otra y ella también gana la suya. Con lo que habla en el vídeo:
- la huella es la media de sus intervenciones largas, sin las que se parecen más a otra persona del vídeo
  (`voices.clean_centroids`);
- si suma menos de `MIN_SECONDS` limpios, no se guarda huella ni muestra: es poco fiable;
- si la huella no se parece a las de esa persona en otros vídeos, se guarda como dudosa y no se usa para
  reconocerla hasta que el usuario la acepte;
- la muestra son sus mejores tramos (los que más se parecen a su huella), entre `MIN_SECONDS` y
  `MAX_SECONDS`, con un objetivo de `TARGET_SECONDS`, extraídos del vídeo original a su calidad.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ..media import extract_clips, probe
from .base import JobContext, free_gpu
from .voices import CLEAN_MIN, TRIM, clean_centroids, unit

MIN_SECONDS = 5.0  # voz limpia mínima de una persona en un vídeo para guardar su huella y su muestra
TARGET_SECONDS = 18.0  # duración buscada de la muestra
MAX_SECONDS = 30.0
MAX_CLIP = 8.0  # cada tramo de la muestra, como mucho (varios tramos cortos suenan más variados)


def person_segments(utts: list[dict[str, Any]], label_person: dict[str, int]) -> list[tuple[int, float, float]]:
    """Intervenciones de al menos `CLEAN_MIN` s de cada persona confirmada: [(persona, inicio, fin)]."""
    out = []
    for u in utts:
        pid = label_person.get(u.get("speaker", ""))
        if pid is not None and u["end"] - u["start"] >= CLEAN_MIN:
            out.append((pid, float(u["start"]) + TRIM, float(u["end"]) - TRIM))
    return out


def pick_sample(items: list[tuple[float, float, float]], min_s: float = MIN_SECONDS, target: float = TARGET_SECONDS,
                max_s: float = MAX_SECONDS, clip: float = MAX_CLIP) -> list[tuple[float, float, float]]:
    """Mejores tramos para la muestra de voz: de más a menos parecidos a la huella, hasta el objetivo.

    `items`: [(inicio, fin, parecido)]. Devuelve los tramos elegidos (recortados a `clip`) en orden de tiempo,
    o [] si no llegan a `min_s`."""
    chosen, total = [], 0.0
    for a, b, s in sorted(items, key=lambda x: -x[2]):
        if total >= target:
            break
        b = min(b, a + clip, a + max_s - total)
        if b - a < 1.0:
            continue
        chosen.append((a, b, s))
        total += b - a
    return sorted(chosen) if total >= min_s else []


def _closest(v: np.ndarray, cents: dict[str, np.ndarray]) -> str:
    return max(cents, key=lambda o: float(v @ cents[o]))


def similarity_to(centroid: np.ndarray, others: list[list[float]]) -> float | None:
    """Parecido de una huella con la media de las huellas de esa persona en otros vídeos (None si no hay)."""
    if not others:
        return None
    ref = unit(np.mean([unit(np.asarray(v, dtype=np.float32)) for v in others], axis=0))
    return float(unit(centroid) @ ref)


def run(ctx: JobContext, label_person: dict[str, int], previous: dict[int, list[list[float]]],
        threshold: float, samples_dir: Path) -> dict[int, dict[str, Any]]:
    """Huella, parecido con lo anterior y muestra de cada persona confirmada del vídeo.

    `previous`: huellas de cada persona en otros vídeos (no dudosas). Devuelve
    `{persona: {vector, seconds, similarity, doubtful, sample: ruta | None, sample_seconds, score}}`."""
    import torch
    import whisperx
    from pyannote.audio import Inference, Model
    from pyannote.core import Segment

    utts = ctx.load("utterances.json") or []
    segs = person_segments(utts, label_person)
    if not segs:
        return {}
    ctx.report(0.05, "Cargando el modelo de voz")
    model = Model.from_pretrained(Path(ctx.settings.diarization_model_dir) / "embedding")
    inf = Inference(model, window="whole", device=torch.device("cuda"))
    audio = whisperx.load_audio(str(ctx.path("audio.wav")))
    file = {"waveform": torch.from_numpy(audio).unsqueeze(0), "sample_rate": 16000}
    total = len(audio) / 16000
    items = []
    for i, (pid, a, b) in enumerate(segs):
        ctx.check_cancel()
        a, b = max(0.0, a), min(total, b)
        if b - a < 0.5:
            continue
        v = np.asarray(inf.crop(file, Segment(a, b))).reshape(-1)
        if np.all(np.isfinite(v)) and np.linalg.norm(v) > 0:
            items.append((pid, a, b, unit(v)))
        if i % 10 == 0:
            ctx.report(0.1 + 0.6 * i / len(segs), "Calculando la voz de cada persona")
    model = inf = None  # libera la memoria de la GPU
    free_gpu()

    cents = clean_centroids([(str(pid), v, b - a) for pid, a, b, v in items])
    out: dict[int, dict[str, Any]] = {}
    info = probe(ctx.source_path) if ctx.source_path and Path(ctx.source_path).is_file() else None
    for key, c in cents.items():
        pid = int(key)
        # Solo cuentan los tramos que se parecen más a esta persona que a cualquier otra del vídeo
        clean = [(a, b, float(v @ c)) for p, a, b, v in items if p == pid and _closest(v, cents) == key]
        seconds = sum(b - a for a, b, _ in clean)
        if seconds < MIN_SECONDS:
            continue
        sim = similarity_to(c, previous.get(pid) or [])
        entry: dict[str, Any] = {"vector": [float(x) for x in c], "seconds": round(seconds, 1),
                                 "similarity": None if sim is None else round(sim, 3),
                                 "doubtful": sim is not None and sim < threshold,
                                 "sample": None, "sample_seconds": 0.0, "score": 0.0}
        ranges = pick_sample(clean)
        if ranges and info:
            dst = samples_dir / str(pid) / f"{ctx.video_id}.flac"
            dst.parent.mkdir(parents=True, exist_ok=True)
            n = len(info["audio_tracks"])
            track = ctx.options.get("main_track")
            extract_clips(ctx.source_path, dst, [(a, b) for a, b, _ in ranges],
                          track if track is not None and track < n else None, n)
            entry.update(sample=str(dst), sample_seconds=round(sum(b - a for a, b, _ in ranges), 1),
                         score=round(float(np.mean([s for _, _, s in ranges])), 3))
        out[pid] = entry
    ctx.report(1.0, f"{len(out)} voces guardadas")
    return out
