"""Fase 6: separación de hablantes (pyannote community-1) y construcción de intervenciones."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import JobContext, free_gpu
from .transcript import assign_speakers, build_utterances, flatten_words, speaking_time

FRAME = 0.1  # segundos por trama de energía


def mic_activity(path: Path) -> np.ndarray:
    """Actividad de voz por tramas de 100 ms en la pista del micrófono (por energía)."""
    import whisperx

    audio = whisperx.load_audio(str(path))
    n = int(16000 * FRAME)
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-9)
    noise = np.percentile(db, 20)
    return db > max(noise + 15, -45)


def detect_owner(turns: list[dict], active: np.ndarray, min_ratio: float = 0.6) -> str | None:
    """Hablante cuyos turnos coinciden en su mayoría con actividad en la pista del micrófono."""
    ratios: dict[str, list[float]] = {}
    for t in turns:
        a, b = int(t["start"] / FRAME), int(t["end"] / FRAME)
        seg = active[a:b]
        if len(seg):
            r = ratios.setdefault(t["speaker"], [0.0, 0.0])
            r[0] += seg.sum()
            r[1] += len(seg)
    scores = {k: v[0] / v[1] for k, v in ratios.items() if v[1] > 0}
    if not scores:
        return None
    best = max(scores, key=scores.get)
    return best if scores[best] >= min_ratio else None


def run(ctx: JobContext) -> None:
    import torch
    import whisperx
    from pyannote.audio import Pipeline

    s = ctx.settings
    model_dir = Path(s.diarization_model_dir)
    if not (model_dir / "config.yaml").exists():
        raise RuntimeError(
            f"No está descargado pyannote community-1 en {model_dir}. "
            "Ejecuta: uv run python ../scripts/download_models.py --only diarization"
        )
    ctx.report(0.0, "Cargando modelo de separación de hablantes")
    pipeline = Pipeline.from_pretrained(model_dir)
    pipeline.to(torch.device("cuda"))

    audio = whisperx.load_audio(str(ctx.path("audio.wav")))
    waveform = torch.from_numpy(audio).unsqueeze(0)

    steps = {"segmentation": 0.3, "speaker_counting": 0.35, "embeddings": 0.9, "discrete_diarization": 1.0}

    def hook(step_name, step_artifact, file=None, total=None, completed=None):
        base = 0.0
        for name, end in steps.items():
            if name == step_name:
                frac = (completed / total) if total and completed is not None else 1.0
                ctx.report(0.05 + 0.9 * (base + (end - base) * frac), "Separando hablantes")
                return
            base = end

    kwargs = {k: ctx.options[k] for k in ("num_speakers", "min_speakers", "max_speakers") if ctx.options.get(k)}
    out = pipeline({"waveform": waveform, "sample_rate": 16000}, hook=hook, **kwargs)

    turns = [
        {"start": float(seg.start), "end": float(seg.end), "speaker": label}
        for seg, _, label in out.exclusive_speaker_diarization.itertracks(yield_label=True)
    ]
    embeddings = {}
    if out.speaker_embeddings is not None:
        for label, vec in zip(out.speaker_diarization.labels(), out.speaker_embeddings):
            if np.all(np.isfinite(vec)):
                embeddings[label] = [float(x) for x in vec]
    del pipeline
    free_gpu()

    owner = None
    if ctx.path("owner.wav").exists():
        ctx.report(0.96, "Identificando tu micrófono")
        owner = detect_owner(turns, mic_activity(ctx.path("owner.wav")))

    ctx.save("diarization.json", {
        "turns": turns,
        "embeddings": embeddings,
        "owner": owner,
        "speaking_time": speaking_time(turns),
    })

    aligned = ctx.load("aligned.json")
    words = assign_speakers(flatten_words(aligned["segments"]), turns)
    ctx.save("utterances.json", build_utterances(words))
    ctx.report(1.0, f"{len(embeddings) or len({t['speaker'] for t in turns})} hablantes detectados")
