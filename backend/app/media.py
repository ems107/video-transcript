"""Utilidades de ffmpeg/ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"No se encuentra {name}. Instálalo (winget install Gyan.FFmpeg) y reinicia la app.")
    return path


def run(args: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(args, capture_output=True, creationflags=CREATE_NO_WINDOW)
    if proc.returncode != 0:
        raise RuntimeError(f"{Path(args[0]).name} falló: {proc.stderr.decode(errors='replace')[-2000:]}")
    return proc


def probe(path: str | Path) -> dict[str, Any]:
    """Duración, pistas de audio, vídeo y fecha de grabación."""
    out = run([_bin("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    info = json.loads(out.stdout)
    fmt = info.get("format", {})
    audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    video = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    created = (fmt.get("tags") or {}).get("creation_time")
    recorded_at = None
    if created:
        try:
            recorded_at = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        except ValueError:
            pass
    if recorded_at is None:
        recorded_at = datetime.fromtimestamp(Path(path).stat().st_mtime)
    return {
        "duration": float(fmt.get("duration") or 0),
        "size": int(fmt.get("size") or 0),
        "audio_tracks": [
            {
                "index": i,
                "codec": s.get("codec_name"),
                "channels": s.get("channels"),
                "title": (s.get("tags") or {}).get("title", ""),
                "language": (s.get("tags") or {}).get("language", ""),
            }
            for i, s in enumerate(audio)
        ],
        "video": bool(video),
        "width": video[0].get("width") if video else None,
        "height": video[0].get("height") if video else None,
        "recorded_at": recorded_at.isoformat(timespec="seconds"),
    }


def extract_audio(src: Path, dst: Path, track: int | None, n_tracks: int) -> None:
    """Extrae audio mono 16 kHz. track=None mezcla todas las pistas."""
    args = [_bin("ffmpeg"), "-y", "-v", "error", "-i", str(src)]
    if track is None and n_tracks > 1:
        inputs = "".join(f"[0:a:{i}]" for i in range(n_tracks))
        args += ["-filter_complex", f"{inputs}amix=inputs={n_tracks}:normalize=0[a]", "-map", "[a]"]
    else:
        args += ["-map", f"0:a:{track or 0}"]
    args += ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)]
    run(args)


def extract_clips(src: Path, dst: Path, ranges: list[tuple[float, float]], track: int | None, n_tracks: int) -> None:
    """Une en un solo audio (FLAC mono, a la frecuencia del original) unos tramos del vídeo.

    track=None mezcla todas las pistas, igual que el audio que se transcribe."""
    if track is None and n_tracks > 1:
        inputs = "".join(f"[0:a:{i}]" for i in range(n_tracks))
        chain = [f"{inputs}amix=inputs={n_tracks}:normalize=0,asplit={len(ranges)}"
                 + "".join(f"[s{i}]" for i in range(len(ranges)))]
        sources = [f"[s{i}]" for i in range(len(ranges))]
    else:
        chain = [f"[0:a:{track or 0}]asplit={len(ranges)}" + "".join(f"[s{i}]" for i in range(len(ranges)))]
        sources = [f"[s{i}]" for i in range(len(ranges))]
    for i, (a, b) in enumerate(ranges):
        chain.append(f"{sources[i]}atrim=start={a:.2f}:end={b:.2f},asetpts=PTS-STARTPTS[c{i}]")
    chain.append("".join(f"[c{i}]" for i in range(len(ranges))) + f"concat=n={len(ranges)}:v=0:a=1[out]")
    run([_bin("ffmpeg"), "-y", "-v", "error", "-i", str(src), "-filter_complex", ";".join(chain),
         "-map", "[out]", "-ac", "1", "-c:a", "flac", str(dst)])


def sample_frames(src: Path, out_dir: Path, every: float, width: int = 320) -> list[tuple[float, Path]]:
    """Extrae un fotograma pequeño cada `every` segundos (para detectar cambios de escena)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    run([
        _bin("ffmpeg"), "-y", "-v", "error", "-hwaccel", "auto", "-i", str(src), "-an",
        "-vf", f"fps=1/{every},scale={width}:-2", "-q:v", "5", str(out_dir / "f_%06d.jpg"),
    ])
    files = sorted(out_dir.glob("f_*.jpg"))
    return [(i * every, f) for i, f in enumerate(files)]


def extract_frame(src: Path, t: float, dst: Path, max_width: int = 1920) -> None:
    run([
        _bin("ffmpeg"), "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
        "-vf", f"scale='min({max_width},iw)':-2", "-q:v", "2", str(dst),
    ])
