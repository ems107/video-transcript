"""Fase 2: selección de fotogramas representativos (cambios de escena) y miniatura."""

from __future__ import annotations

import shutil

import imagehash
from PIL import Image

from ..media import extract_frame, sample_frames
from .base import JobContext


def select_frames(hashes: list[tuple[float, imagehash.ImageHash]], threshold: int, min_gap: float, max_gap: float) -> list[float]:
    kept: list[float] = []
    last_hash, last_t = None, -1e9
    for t, h in hashes:
        changed = last_hash is None or (h - last_hash) > threshold
        if (changed and t - last_t >= min_gap) or t - last_t >= max_gap:
            kept.append(t)
            last_hash, last_t = h, t
    return kept


def run(ctx: JobContext) -> None:
    s = ctx.settings
    info = ctx.load("probe.json")
    frames_dir = ctx.path("frames")
    frames_dir.mkdir(exist_ok=True)
    if not info.get("video"):
        ctx.save("frames.json", [])
        return

    ctx.report(0.0, "Muestreando fotogramas")
    samples_dir = ctx.path("samples")
    shutil.rmtree(samples_dir, ignore_errors=True)
    samples = sample_frames(ctx.source_path, samples_dir, s.frame_sample_every)
    ctx.check_cancel()

    ctx.report(0.4, f"Detectando cambios de escena en {len(samples)} muestras")
    hashes = []
    for t, f in samples:
        with Image.open(f) as im:
            hashes.append((t, imagehash.phash(im)))

    threshold = s.frame_hash_distance
    kept = select_frames(hashes, threshold, s.frame_min_interval, s.frame_max_interval)
    while len(kept) > s.max_frames:
        threshold += 2
        kept = select_frames(hashes, threshold, s.frame_min_interval, max(s.frame_max_interval, info["duration"] / s.max_frames))

    out = []
    for i, t in enumerate(kept):
        ctx.check_cancel()
        dst = frames_dir / f"kf_{int(t):06d}.jpg"
        if not dst.exists():
            extract_frame(ctx.source_path, t, dst, max_width=1600)
        out.append({"t": t, "file": dst.name})
        if i % 10 == 0:
            ctx.report(0.5 + 0.45 * i / max(1, len(kept)), f"Extrayendo fotograma {i + 1}/{len(kept)}")

    # Miniatura: un fotograma temprano pero no el primero (suele ser negro o de carga)
    thumb_t = min(60.0, info["duration"] * 0.1)
    extract_frame(ctx.source_path, thumb_t, ctx.path("thumbnail.jpg"), max_width=640)
    shutil.rmtree(samples_dir, ignore_errors=True)
    ctx.save("frames.json", out)
    ctx.report(1.0, f"{len(out)} fotogramas seleccionados")
