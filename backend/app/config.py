"""Configuración de la aplicación.

Los valores por defecto se pueden sobrescribir desde la web (se guardan en data/settings.json).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[2]
# VT_DATA_DIR permite usar otra carpeta de datos (pruebas o una segunda instancia)
DATA_DIR = Path(os.environ.get("VT_DATA_DIR") or ROOT_DIR / "data")
MODELS_DIR = ROOT_DIR / "models"
WORK_DIR = DATA_DIR / "work"
SETTINGS_FILE = DATA_DIR / "settings.json"
# VT_FRONTEND_DIST: la web de otra compilación (probar una rama sin tocar el dist que sirve la instancia del usuario)
FRONTEND_DIST = Path(os.environ.get("VT_FRONTEND_DIST") or ROOT_DIR / "frontend" / "dist")


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
    llm_n_cpu_moe: int = 24  # capas MoE cuyos expertos se ejecutan en CPU/RAM
    # Muestreo recomendado por Qwen para Qwen3.6 sin «modo razonamiento». Con temperatura baja y sin
    # penalización, el modelo puede entrar en bucles repitiendo un elemento (visto con 0,2)
    llm_temperature: float = 0.7
    llm_top_p: float = 0.8
    llm_top_k: int = 20
    llm_min_p: float = 0.0
    llm_presence_penalty: float = 1.5
    # Tokens por imagen del modelo de visión (0 = lo que indique el modelo). Más tokens = más detalle
    llm_image_min_tokens: int = 0
    llm_image_max_tokens: int = 0

    # Fotogramas
    frame_sample_every: float = 2.0  # muestreo para detectar cambios de escena
    max_frames: int = 240  # máximo de fotogramas analizados por el modelo de visión
    frame_min_interval: float = 4.0  # segundos mínimos entre fotogramas
    frame_max_interval: float = 60.0  # como máximo un fotograma cada N segundos
    frame_hash_distance: int = 6  # distancia de hash perceptual para considerar duplicado
    # Ancho máximo de los fotogramas para el modelo de visión. Con 1600 px, los nombres pequeños de una
    # grabación 4K se leían bien solo el 44 % de las veces; con 2560 px, el 100 % (≈ 1,6× más lento)
    frame_max_width: int = 2560

    # Resumen por bloques
    chunk_minutes: float = 30.0

    # Registros (data/logs/AAAA-MM-DD.log): «DEBUG» añade cada consulta de la web y el progreso de las fases
    log_level: Literal["INFO", "DEBUG"] = "INFO"
    log_keep_days: int = 30


# Valores por defecto de versiones anteriores que se guardaron en settings.json sin que el usuario los
# eligiera: si siguen igual y no existen aún los ajustes que los sustituyen, se usan los nuevos
OLD_DEFAULTS = [("llm_temperature", 0.2, "llm_presence_penalty")]


def load_settings() -> Settings:
    if SETTINGS_FILE.exists():
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        for key, old, marker in OLD_DEFAULTS:
            if data.get(key) == old and marker not in data:
                data.pop(key)
        return Settings(**data)
    return Settings()


def save_settings(settings: Settings) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(settings.model_dump_json(indent=2), encoding="utf-8")


def ensure_dirs() -> None:
    for d in (DATA_DIR, WORK_DIR, MODELS_DIR):
        d.mkdir(parents=True, exist_ok=True)
