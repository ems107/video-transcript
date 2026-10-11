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
    # Comprobación por la voz: "" | "reasignada" (la voz era de otro hablante) | "dudosa" (no está claro)
    voice: str = ""


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


class KnowledgeItem(SQLModel, table=True):
    """Conocimiento aprendido de los vídeos (o propuesto por la IA) sobre un perfil o una persona.

    Lo manual vive en Profile/Person y la IA nunca lo toca; esto son elementos sueltos que el usuario
    acepta o rechaza. Los aceptados no se borran: se retiran.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: Optional[int] = Field(default=None, foreign_key="profile.id", index=True, ondelete="CASCADE")
    person_id: Optional[int] = Field(default=None, foreign_key="person.id", index=True, ondelete="CASCADE")
    # termino | contexto | seccion (perfil) · dato | alias (persona) · nueva_persona
    kind: str
    category: str = ""
    data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    key: str = Field(default="", index=True)  # texto normalizado para deduplicar
    status: str = "propuesto"  # propuesto | aceptado | rechazado | retirado
    # Origen: vídeo y hablante (los datos de un hablante se atribuyen a la persona al resolverlo)
    video_id: Optional[int] = Field(default=None, foreign_key="video.id", index=True, ondelete="SET NULL")
    speaker_label: str = ""
    replaces_id: Optional[int] = None
    # [{video_id, t, lines: [{t, label, text}]}]
    evidence: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    seen_count: int = 1  # nº de vídeos distintos en los que aparece
    last_seen_at: Optional[NaiveDatetime] = None
    created_at: NaiveDatetime = Field(default_factory=now)
    decided_at: Optional[NaiveDatetime] = None


class KnowledgeVersion(SQLModel, table=True):
    """Foto del estado de un perfil o persona (manual + aprendido aceptado) tras cada cambio."""

    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: Optional[int] = Field(default=None, foreign_key="profile.id", index=True, ondelete="CASCADE")
    person_id: Optional[int] = Field(default=None, foreign_key="person.id", index=True, ondelete="CASCADE")
    reason: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: NaiveDatetime = Field(default_factory=now)


class PersonPairDismissal(SQLModel, table=True):
    """Pareja de personas que el usuario ha marcado como «no son la misma persona»."""

    a: int = Field(foreign_key="person.id", primary_key=True, ondelete="CASCADE")
    b: int = Field(foreign_key="person.id", primary_key=True, ondelete="CASCADE")


class StageRun(SQLModel, table=True):
    """Cuánto tardó una fase ejecutada, para estimar las siguientes (ver `services.estimate`)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: Optional[int] = Field(default=None, foreign_key="job.id", ondelete="SET NULL")
    video_id: Optional[int] = Field(default=None, foreign_key="video.id", ondelete="SET NULL")
    stage: str = Field(index=True)
    seconds: float
    units: float  # minutos de audio, o fotogramas en «vision»
    created_at: NaiveDatetime = Field(default_factory=now)


class VideoCorrection(SQLModel, table=True):
    """Corrección escrita por el usuario sobre un vídeo. La IA la recibe como un hecho y nunca la modifica."""

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True, ondelete="CASCADE")
    text: str
    created_at: NaiveDatetime = Field(default_factory=now)
    updated_at: NaiveDatetime = Field(default_factory=now)


class SpeakerOverride(SQLModel, table=True):
    """Arreglo manual: «de `start` a `end` habla esta persona». Se guarda por tiempo y persona, no por
    línea ni etiqueta, para que sobreviva a cualquier regeneración (ver `pipeline/voices.apply_overrides`)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="video.id", index=True, ondelete="CASCADE")
    start: float
    end: float
    person_id: int = Field(foreign_key="person.id", ondelete="CASCADE")
    created_at: NaiveDatetime = Field(default_factory=now)


class Followup(SQLModel, table=True):
    """Seguimiento: continuidad de un tema a lo largo de varios vídeos, con su estado acumulado.

    Es independiente del perfil. El estado lo actualiza la IA con cada vídeo; lo que edita el usuario
    queda marcado como manual y la IA ya no lo cambia (ver `followups.py`)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    status: str = "abierto"  # abierto | archivado
    summary: str = ""
    summary_manual: bool = False  # el usuario lo ha editado: la IA ya no lo reescribe
    summary_ai: str = ""  # último resumen de la IA cuando el vigente es el del usuario
    # Fecha de grabación desde la que el estado no está al día (hay que rehacerlo), y por qué
    stale_from: Optional[NaiveDatetime] = None
    stale_reason: str = ""
    folder: str = ""
    created_at: NaiveDatetime = Field(default_factory=now)
    updated_at: NaiveDatetime = Field(default_factory=now)


class FollowupVideo(SQLModel, table=True):
    followup_id: int = Field(foreign_key="followup.id", primary_key=True, ondelete="CASCADE")
    video_id: int = Field(foreign_key="video.id", primary_key=True, ondelete="CASCADE")
    applied: bool = False  # el estado ya incluye este vídeo
    contribution: str = ""  # lo que aportó al tema
    summary: str = ""  # resumen de la evolución tras aplicarlo (para volver atrás al rehacer)
    added_at: NaiveDatetime = Field(default_factory=now)


class FollowupItem(SQLModel, table=True):
    """Tarea, decisión o duda del seguimiento. Su estado sale siempre del último evento de su recorrido."""

    id: Optional[int] = Field(default=None, primary_key=True)
    followup_id: int = Field(foreign_key="followup.id", index=True, ondelete="CASCADE")
    kind: str  # tarea | decision | duda
    text: str
    owner: str = ""
    due: str = ""
    status: str = ""
    manual: bool = False  # creado o editado por el usuario
    hidden: bool = False  # borrado por el usuario: se conserva para que la IA no lo vuelva a crear
    # [{video_id, t, evento, nota, source: ia|manual, at}]
    events: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: NaiveDatetime = Field(default_factory=now)


class FollowupVersion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    followup_id: int = Field(foreign_key="followup.id", index=True, ondelete="CASCADE")
    reason: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: NaiveDatetime = Field(default_factory=now)
