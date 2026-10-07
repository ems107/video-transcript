"""video-transcript: transcripción y análisis local de vídeos."""

from pathlib import Path

# Única fuente de la versión: el fichero VERSION de la raíz del repositorio.
__version__ = (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
