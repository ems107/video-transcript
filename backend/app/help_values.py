"""Valores que cita la ayuda de la web («{{v:clave}}»), leídos de su sitio para que no se desfasen.

Si cambias un umbral o un límite, la ayuda lo muestra solo. Si añades uno que la ayuda deba citar,
regístralo aquí; `tests/test_help.py` comprueba que toda clave usada en las páginas existe.
"""

from __future__ import annotations

import inspect
from typing import Any

from . import estimates
from . import followups
from . import knowledge as K
from .config import load_settings
from .pipeline import analyze, identify, learn, names, transcript, voices
from .pipeline.voice import assign_visual_names
from .prompts import LIST_LIMITS
from .services import CONTEXT_CONFIDENCE


def _default(fn: Any, param: str) -> Any:
    return inspect.signature(fn).parameters[param].default


def values() -> dict[str, Any]:
    out: dict[str, Any] = dict(load_settings().model_dump())
    out.update({
        # Comprobación por la voz
        "voz_ventana": voices.WINDOW,
        "voz_paso": voices.HOP,
        "voz_minimo_limpia": voices.CLEAN_MIN,
        "voz_parecido_minimo": voices.MIN_SIM,
        "voz_margen": voices.MARGIN,
        "voz_margen_dudosa": voices.DOUBT_MARGIN,
        "voz_tramo_minimo": voices.MIN_RUN,
        "voz_division_silueta": voices.SPLIT_SILHOUETTE,
        "voz_division_segundos": voices.SPLIT_SECONDS,
        # Nombres en pantalla
        "nombres_parecido": names.SIMILAR,
        "nombres_tildes_pct": round(names.ACCENT_SHARE * 100),
        "pantalla_dominancia": _default(assign_visual_names, "dominance"),
        "pantalla_minimo": _default(assign_visual_names, "min_count"),
        "pantalla_confianza": identify.VISUAL_CONFIDENCE,
        "borde_turno": transcript.BORDER,
        "contexto_confianza": CONTEXT_CONFIDENCE,
        "apodo_parecido": analyze.NICKNAME_SIMILAR,
        # Aprendizaje
        "aprender_max_terminos": learn.MAX_TERMS,
        "aprender_max_contexto": learn.MAX_CONTEXT,
        "aprender_max_por_persona": learn.MAX_PER_PERSON,
        "aprender_max_personas_nuevas": learn.MAX_NEW_PEOPLE,
        "aprender_max_secciones": learn.MAX_SECTIONS,
        "termino_fotogramas": K.SCREEN_MIN_FRAMES,
        # Seguimientos
        "seguimiento_contexto": followups.FOLLOW_CONTEXT_CHARS,
        "seguimiento_recientes": followups.RECENT_VIDEOS,
        "seguimiento_parecido": followups.DUPLICATE,
        "seguimiento_max_eventos": LIST_LIMITS["eventos"],
        "seguimiento_max_senales": LIST_LIMITS["seguimiento"],
        "seguimiento_cita_parecido": followups.QUOTE_SIMILAR,
        "seguimiento_cita_ventana": round(followups.QUOTE_WINDOW),
        # Estimaciones de tiempo (segundos por minuto de audio, o por fotograma en «vision»)
        "estimacion_historial": estimates.HISTORY,
        **{f"ritmo_{stage}": rate for stage, rate in estimates.DEFAULT_RATES.items()},
    })
    return out
