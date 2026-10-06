"""Descarga (una sola vez) todos los modelos y binarios necesarios a la carpeta models/.

Uso (desde backend/):
    uv run python ../scripts/download_models.py            # todo
    uv run python ../scripts/download_models.py --only llm # solo una parte

Partes: llama (binarios llama.cpp CUDA), llm (Qwen3.6 GGUF), whisper, align, diarization.

La parte "diarization" (pyannote community-1, CC-BY-4.0) requiere una cuenta gratuita de
Hugging Face, aceptar las condiciones en
https://huggingface.co/pyannote/speaker-diarization-community-1 y un token de lectura.
El token se pide por consola (o variable HF_TOKEN) y NO se guarda en ningún sitio.
"""

from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
os.environ.setdefault("HF_HOME", str(MODELS / "hf"))

from huggingface_hub import hf_hub_download, snapshot_download  # noqa: E402

LLM_REPO = "unsloth/Qwen3.6-35B-A3B-GGUF"
LLM_FILE = "Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf"
MMPROJ_FILE = "mmproj-F16.gguf"
WHISPER_REPO = "Systran/faster-whisper-large-v3"
ALIGN_REPO = "jonatasgrosman/wav2vec2-large-xlsr-53-spanish"
DIAR_REPO = "pyannote/speaker-diarization-community-1"
LLAMA_CUDA = "cuda-13.4"


def download_llama() -> None:
    dest = MODELS / "llama.cpp"
    if (dest / "llama-server.exe").exists():
        print("llama.cpp ya descargado:", dest)
        return
    api = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"
    with urllib.request.urlopen(api) as r:
        releases = json.load(r)
    for rel in releases:
        assets = {a["name"]: a["browser_download_url"] for a in rel["assets"]}
        main = next((n for n in assets if n.endswith(f"bin-win-{LLAMA_CUDA}-x64.zip") and n.startswith("llama-")), None)
        rt = next((n for n in assets if n.startswith("cudart-") and n.endswith(f"win-{LLAMA_CUDA}-x64.zip")), None)
        if main and rt:
            break
    else:
        sys.exit("No se encontró una release de llama.cpp con CUDA para Windows")
    dest.mkdir(parents=True, exist_ok=True)
    for name in (main, rt):
        print("Descargando", name)
        with urllib.request.urlopen(assets[name]) as r:
            zipfile.ZipFile(io.BytesIO(r.read())).extractall(dest)
    # Algunas releases empaquetan en subcarpeta: aplanar
    if not (dest / "llama-server.exe").exists():
        found = next(dest.rglob("llama-server.exe"))
        for f in found.parent.iterdir():
            f.replace(dest / f.name)
    print("llama.cpp listo en", dest, f"({rel['tag_name']})")


def download_llm() -> None:
    dest = MODELS / "llm"
    for f in (LLM_FILE, MMPROJ_FILE):
        print("Descargando", f, "(puede tardar)")
        hf_hub_download(LLM_REPO, f, local_dir=dest)
    # Nombres estables usados por la configuración
    (dest / LLM_FILE).replace(dest / "Qwen3.6-35B-A3B.gguf") if (dest / LLM_FILE).exists() else None
    (dest / MMPROJ_FILE).replace(dest / "mmproj-Qwen3.6-35B-A3B.gguf") if (dest / MMPROJ_FILE).exists() else None
    print("LLM listo en", dest)


def download_whisper() -> None:
    snapshot_download(WHISPER_REPO)
    print("Whisper large-v3 en caché")


def download_align() -> None:
    snapshot_download(ALIGN_REPO)
    print("wav2vec2 español en caché")


def download_nltk() -> None:
    import nltk

    nltk.download("punkt_tab", download_dir=str(MODELS / "nltk_data"), quiet=True)
    print("nltk punkt_tab listo")


def download_diarization() -> None:
    dest = MODELS / "pyannote-community-1"
    if (dest / "config.yaml").exists():
        print("pyannote community-1 ya descargado:", dest)
        return
    token = os.environ.get("HF_TOKEN") or getpass.getpass(
        "Token de Hugging Face (lectura) para pyannote community-1 (no se guarda): "
    )
    snapshot_download(DIAR_REPO, local_dir=dest, token=token)
    print("pyannote community-1 listo en", dest)


PARTS = {
    "llama": download_llama,
    "llm": download_llm,
    "whisper": download_whisper,
    "align": download_align,
    "nltk": download_nltk,
    "diarization": download_diarization,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(PARTS), nargs="*")
    args = ap.parse_args()
    for name in args.only or PARTS:
        print(f"== {name} ==")
        PARTS[name]()


if __name__ == "__main__":
    main()
