"""Fase 1: lectura del vídeo y extracción de audio."""

from __future__ import annotations

from ..media import extract_audio, probe
from .base import JobContext


def run(ctx: JobContext) -> None:
    ctx.report(0.0, "Leyendo información del vídeo")
    info = probe(ctx.source_path)
    n = len(info["audio_tracks"])
    if n == 0:
        raise RuntimeError("El vídeo no tiene pistas de audio")
    ctx.save("probe.json", info)

    # Pista principal para transcribir: la indicada o, si hay varias, mezcla de todas
    main_track = ctx.options.get("main_track")
    if main_track is not None and main_track >= n:
        main_track = None
    ctx.report(0.2, "Extrayendo audio")
    extract_audio(ctx.source_path, ctx.path("audio.wav"), main_track, n)

    owner_track = ctx.options.get("owner_track")
    if owner_track is not None and n > 1 and owner_track < n:
        ctx.report(0.7, "Extrayendo pista del micrófono")
        extract_audio(ctx.source_path, ctx.path("owner.wav"), owner_track, n)
    ctx.report(1.0, f"Duración {info['duration'] / 60:.0f} min, {n} pista(s) de audio")
