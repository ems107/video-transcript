"""Modelos de datos (SQLite vía SQLModel)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now()


class ProfilePersonLink(SQLModel, table=True):
    profile_id: int = Field(foreign_key="profile.id", primary_key=True, ondelete="CASCADE")
    person_id: int = Field(foreign_key="person.id", primary_key=True, ondelete="CASCADE")


class Profile(SQLModel, table=True):
    """Tipo de vídeo: contexto de negocio, glosario, personas e instrucciones."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    # Contexto general / lógica de negocio que el modelo debe conocer
    context: str = ""
    # Instrucciones extra para el análisis (resumen, foco, estilo...)
    extra_prompt: str = ""
    # Secciones que se quieren en el resumen (lista de strings)
    summary_sections: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Glosario: [{"term": str, "variants": [str], "definition": str}]
    glossary: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: NaiveDatetime = Field(default_factory=now)
    updated_at: NaiveDatetime = Field(default_factory=now)


class Person(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    role: str = ""
    # Otros nombres con los que aparece (p. ej. el nombre que muestra en las videollamadas)
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    notes: str = ""
    created_at: NaiveDatetime = Field(default_factory=now)


class VoiceEmbedding(SQLModel, table=True):
    """Huella de voz confirmada de una persona (una por hablante confirmado en un vídeo)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    person_id: int = Field(foreign_key="person.id", index=True, ondelete="CASCADE")
    video_id: Optional[int] = Field(default=None, foreign_key="video.id", ondelete="SET NULL")
    vector: list[float] = Field(sa_column=Column(JSON))
    created_at: NaiveDatetime = Field(default_factory=now)


class Video(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = ""
    source_path: str  # ruta original indicada por el usuario
    video_path: str = ""  # ruta final del vídeo (tras mover/copiar)
    folder: str = ""  # carpeta de resultados
    duration: float = 0.0
    profile_id: Optional[int] = Field(default=None, foreign_key="profile.id", ondelete="SET NULL")
    status: str = "pending"  # pending | processing | done | error
    summary_md: str = ""
    analysis: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    recorded_at: Optional[NaiveDatetime] = None
    created_at: NaiveDatetime = Field(default_factory=now)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True, ondelete="CASCADE")
    status: str = "queued"  # queued | running | done | error | cancelled
    stage: str = ""
    progress: float = 0.0  # 0..1 global
    message: str = ""
    error: str = ""
    options: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: NaiveDatetime = Field(default_factory=now)
    started_at: Optional[NaiveDatetime] = None
    finished_at: Optional[NaiveDatetime] = None


class Speaker(SQLModel, table=True):
    """Hablante detectado en un vídeo (SPEAKER_00...) y su identificación."""

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True, ondelete="CASCADE")
    label: str
    order_idx: int = 0  # orden de aparición (Hablante 1, 2...)
    person_id: Optional[int] = Field(default=None, foreign_key="person.id", ondelete="SET NULL")
    suggested_person_id: Optional[int] = Field(default=None, foreign_key="person.id", ondelete="SET NULL")
    suggested_name: str = ""  # nombre visto en pantalla que aún no es una persona conocida
    source: str = ""  # micrófono | voz | pantalla
    confidence: float = 0.0
    confirmed: bool = False
    is_owner: bool = False
    speaking_time: float = 0.0
    # Pistas de la imagen: {"nombre en pantalla": nº de coincidencias}
    visual_hints: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    embedding: Optional[list[float]] = Field(default=None, sa_column=Column(JSON))


class Segment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True, ondelete="CASCADE")
    idx: int
    start: float
    end: float
    speaker: str = ""
    text: str
    # Texto antes de la corrección de glosario (vacío si no hubo cambios)
    original_text: str = ""
    corrections: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))


class Keyframe(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True, ondelete="CASCADE")
    t: float
    path: str
    scene_type: str = ""
    description: str = ""
    visible_text: str = ""
    participants: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    active_speaker: str = ""
