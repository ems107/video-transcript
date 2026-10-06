"""Configuración de la aplicación.

Los valores por defecto se pueden sobrescribir desde la web (se guardan en data/settings.json).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
WORK_DIR = DATA_DIR / "work"
SETTINGS_FILE = DATA_DIR / "settings.json"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


class Settings(BaseModel):
    # Dónde se publican los vídeos analizados (una subcarpeta por vídeo)
    analyzed_dir: str = str(Path.home() / "Videos" / "Analizados")
    # "move": mueve el vídeo original a su carpeta; "copy": lo copia
    file_mode: Literal["move", "copy"] = "move"
    # Nombre con el que se etiqueta al dueño del micrófono cuando hay pista separada
    owner_name: str = "Yo"

    # Transcripción
    language: str = "es"
    whisper_model: str = "large-v3"
    whisper_batch_size: int = 16
    align_model: str = "jonatasgrosman/wav2vec2-large-xlsr-53-spanish"

    # Separación de hablantes (carpeta local con el modelo descargado)
    diarization_model_dir: str = str(MODELS_DIR / "pyannote-community-1")

    # Identificación de personas por voz
    voice_match_threshold: float = 0.55  # similitud coseno mínima para proponer
    voice_auto_threshold: float = 0.75  # a partir de aquí la propuesta es "alta confianza"

    # Modelo de lenguaje y visión (llama.cpp)
    llama_server_path: str = str(MODELS_DIR / "llama.cpp" / "llama-server.exe")
    llm_model_path: str = str(MODELS_DIR / "llm" / "Qwen3.6-35B-A3B.gguf")
    llm_mmproj_path: str = str(MODELS_DIR / "llm" / "mmproj-Qwen3.6-35B-A3B.gguf")
    llm_port: int = 8091
    llm_ctx: int = 65536
    llm_n_cpu_moe: int = 20  # capas MoE cuyos expertos se ejecutan en CPU/RAM
    llm_temperature: float = 0.2

    # Fotogramas
    frame_sample_every: float = 2.0  # muestreo para detectar cambios de escena
    max_frames: int = 240  # máximo de fotogramas analizados por el modelo de visión
    frame_min_interval: float = 4.0  # segundos mínimos entre fotogramas
    frame_max_interval: float = 60.0  # como máximo un fotograma cada N segundos
    frame_hash_distance: int = 6  # distancia de hash perceptual para considerar duplicado

    # Resumen por bloques
    chunk_minutes: float = 30.0


def load_settings() -> Settings:
    if SETTINGS_FILE.exists():
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return Settings(**data)
    return Settings()


def save_settings(settings: Settings) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(settings.model_dump_json(indent=2), encoding="utf-8")


def ensure_dirs() -> None:
    for d in (DATA_DIR, WORK_DIR, MODELS_DIR):
        d.mkdir(parents=True, exist_ok=True)
