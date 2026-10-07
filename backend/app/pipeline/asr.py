"""Fases 4 y 5: transcripción (Whisper large-v3) y alineamiento palabra a palabra (wav2vec2)."""

from __future__ import annotations

from typing import Any

from ..knowledge import effective_glossary
from .base import JobContext, free_gpu
from .glossary import normalize

# Whisper admite ~223 tokens de contexto previo; en español ≈ 3 caracteres/token
PROMPT_MAX_CHARS = 550


def build_whisper_prompt(profile: dict[str, Any] | None, people: list[dict[str, Any]], screen_terms: list[str]) -> str:
    """Contexto inicial para Whisper: nombres y vocabulario, por prioridad.

    Prioridad: glosario del perfil > personas > términos vistos en pantalla.
    """
    terms: list[str] = []
    seen: set[str] = set()

    def add(t: str) -> None:
        k = normalize(t)
        if k and k not in seen:
            seen.add(k)
            terms.append(t.strip())

    for g in effective_glossary(profile):  # manual primero, después lo aprendido
        add(g["term"])
    names = [p["name"] for p in people]
    seen.update(normalize(n) for n in names)
    for t in screen_terms:
        add(t)

    head = "Reunión de trabajo en español."
    if names:
        head += " Participan " + ", ".join(names[:12]) + "."
    prompt = head
    if terms:
        prompt += " Se habla de"
        for i, t in enumerate(terms):
            piece = (" " if i == 0 else ", ") + t
            if len(prompt) + len(piece) + 1 > PROMPT_MAX_CHARS:
                break
            prompt += piece
        prompt += "."
    return prompt


def drop_prompt_echoes(segments: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
    """Elimina segmentos que solo repiten el contexto inicial (alucinación típica en silencios)."""
    p = normalize(prompt)
    out = []
    for s in segments:
        t = normalize(s["text"])
        if len(t) > 15 and t in p:
            continue
        out.append(s)
    return out


def run_asr(ctx: JobContext) -> None:
    import torch  # noqa: F401  (carga las DLL de CUDA/cuDNN antes que ctranslate2)
    import whisperx

    s = ctx.settings
    prompt = build_whisper_prompt(ctx.profile, ctx.people, ctx.load("screen_terms.json", []))
    ctx.save("whisper_prompt.json", {"prompt": prompt})
    ctx.report(0.0, "Cargando Whisper large-v3")
    model = whisperx.load_model(
        s.whisper_model,
        "cuda",
        compute_type="float16",
        language=s.language,
        asr_options={"initial_prompt": prompt, "beam_size": 5, "best_of": 5},
        vad_method="pyannote",
        local_files_only=True,
    )
    audio = whisperx.load_audio(str(ctx.path("audio.wav")))
    ctx.check_cancel()

    def progress(pct: float) -> None:
        ctx.report(0.05 + 0.95 * pct / 100, f"Transcribiendo ({pct:.0f}%)")

    result = model.transcribe(audio, batch_size=s.whisper_batch_size, language=s.language, progress_callback=progress)
    segments = drop_prompt_echoes(result["segments"], prompt)
    ctx.save("asr.json", {"language": result.get("language", s.language), "segments": segments})
    del model
    free_gpu()


def run_align(ctx: JobContext) -> None:
    import torch  # noqa: F401
    import whisperx

    s = ctx.settings
    asr = ctx.load("asr.json")
    ctx.report(0.0, "Cargando modelo de alineamiento")
    model_a, metadata = whisperx.load_align_model(language_code=s.language, device="cuda", model_name=s.align_model)
    audio = whisperx.load_audio(str(ctx.path("audio.wav")))

    def progress(pct: float) -> None:
        ctx.report(0.05 + 0.95 * pct / 100, f"Alineando palabras ({pct:.0f}%)")

    aligned = whisperx.align(
        asr["segments"], model_a, metadata, audio, "cuda", return_char_alignments=False, progress_callback=progress
    )
    ctx.save("aligned.json", {"segments": aligned["segments"]})
    del model_a
    free_gpu()
