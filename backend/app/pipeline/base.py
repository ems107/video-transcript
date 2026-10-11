"""Contexto de un trabajo y utilidades comunes a todas las fases."""

from __future__ import annotations

import gc
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..config import Settings


class Cancelled(Exception):
    pass


@dataclass
class JobContext:
    job_id: int
    video_id: int
    source_path: Path
    work_dir: Path
    settings: Settings
    options: dict[str, Any]
    profile: dict[str, Any] | None
    people: list[dict[str, Any]]  # personas conocidas (id, name, role, aliases)
    report: Callable[[float, str], None]  # (progreso de la fase 0..1, mensaje)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    # Etiqueta de pyannote -> nombre a mostrar (se rellena tras la identificación)
    speaker_names: dict[str, str] = field(default_factory=dict)
    # Etiqueta -> cómo se sabe quién es («confirmado», «probable, por pantalla; sin confirmar» o «»)
    speaker_status: dict[str, str] = field(default_factory=dict)
    # Correcciones del usuario sobre este vídeo: [{id, text, updated_at}]
    corrections: list[dict[str, Any]] = field(default_factory=list)
    # Arreglos manuales de hablantes aplicados en este trabajo: [{id, start, end, person_id}]
    overrides: list[dict[str, Any]] = field(default_factory=list)
    # Estado de los seguimientos del vídeo antes de su fecha (contexto del análisis)
    followups: list[str] = field(default_factory=list)

    def path(self, name: str) -> Path:
        return self.work_dir / name

    def save(self, name: str, data: Any) -> None:
        tmp = self.path(name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path(name))

    def load(self, name: str, default: Any = None) -> Any:
        p = self.path(name)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))

    def check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()


def free_gpu() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass
