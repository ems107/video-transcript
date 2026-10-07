"""Prompts del modelo de lenguaje y esquemas JSON de sus respuestas."""

from __future__ import annotations

from typing import Any

from .knowledge import learned_block, person_line, prompt_people


def profile_block(profile: dict[str, Any] | None, people: list[dict[str, Any]]) -> str:
    """Contexto del perfil (negocio, glosario, lo aprendido, personas) para incluir en los prompts."""
    parts: list[str] = []
    if profile:
        parts.append(f"Tipo de vídeo: {profile['name']}")
        if profile.get("description"):
            parts.append(profile["description"])
        if profile.get("context"):
            parts.append("Contexto y lógica de negocio:\n" + profile["context"])
        gl = [g for g in profile.get("glossary") or [] if g.get("term")]
        if gl:
            lines = [f"- {g['term']}" + (f": {g['definition']}" if g.get("definition") else "") for g in gl]
            parts.append("Glosario (escritura correcta de los términos):\n" + "\n".join(lines))
        learned = learned_block(profile)
        if learned:
            parts.append("Aprendido de vídeos anteriores (si contradice lo anterior, prevalece lo anterior):\n"
                         + learned)
    people = prompt_people(people)
    if people:
        parts.append("Personas habituales:\n" + "\n".join(person_line(p) for p in people))
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- visión

VISION_SYSTEM = """Analizas capturas de una grabación del escritorio de un ordenador (videollamadas, \
programas, código, navegador, presentaciones). Describe con precisión y en español lo que se ve, \
sin suponer nada que no sea visible. Transcribe literalmente nombres, términos y textos relevantes."""

VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "tipo_escena": {
            "type": "string",
            "enum": ["videollamada", "presentacion", "codigo", "navegador", "documento", "hoja_calculo",
                     "escritorio", "otro"],
        },
        "aplicacion": {"type": "string"},
        "descripcion": {"type": "string"},
        "texto_relevante": {"type": "string"},
        "participantes": {"type": "array", "items": {"type": "string"}},
        "hablante_activo": {"type": "string"},
        "terminos": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tipo_escena", "aplicacion", "descripcion", "texto_relevante", "participantes",
                 "hablante_activo", "terminos"],
}


def vision_user(context: str, t: str) -> str:
    return f"""Fotograma en {t} de la grabación.
{("Contexto del vídeo:\n" + context + "\n") if context else ""}
Devuelve:
- tipo_escena y aplicacion: nombre del programa o web visible, tal como aparezca en pantalla (cadena vacía si no se distingue).
- descripcion: 1-3 frases sobre qué se muestra y qué parece estar haciéndose.
- texto_relevante: textos importantes legibles (títulos, pestañas, archivos, funciones, cifras clave, \
diapositivas). Máximo 600 caracteres.
- participantes: nombres visibles de participantes de la videollamada (literal), si los hay.
- hablante_activo: nombre del participante resaltado como hablando (borde iluminado, indicador de voz) \
o cadena vacía si no se distingue.
- terminos: nombres propios, siglas, productos y términos técnicos visibles (literal)."""


# --------------------------------------------------------------------------- corrección

CORRECT_SYSTEM = """Revisas una transcripción automática en español. Para cada propuesta decides si \
el fragmento marcado entre [[ ]] es realmente una mala transcripción del término del glosario \
indicado. Acepta solo si, por sonido y por contexto, es claramente ese término. Ante la duda, rechaza."""

CORRECT_SCHEMA = {
    "type": "object",
    "properties": {
        "decisiones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "aceptar": {"type": "boolean"}},
                "required": ["id", "aceptar"],
            },
        }
    },
    "required": ["decisiones"],
}


# --------------------------------------------------------------------------- análisis

ANALYSIS_RULES = """Reglas:
- Usa exclusivamente la información de la transcripción y de lo visto en pantalla. No inventes datos, \
nombres, cifras ni conclusiones. Si algo no está claro, indícalo.
- Escribe los términos tal como aparecen en el glosario.
- Cita la marca de tiempo [hh:mm:ss] de donde sale cada punto importante.
- Escribe en español."""

CHUNK_SYSTEM = """Eres un analista que resume grabaciones de reuniones y sesiones de trabajo \
(videollamadas, demostraciones, revisión de código) a partir de su transcripción con hablantes y de \
la descripción de lo que se ve en pantalla.

""" + ANALYSIS_RULES

ITEM_T = {"type": "string"}
TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "responsable": {"type": "string"},
        "tarea": {"type": "string"},
        "plazo": {"type": "string"},
        "t": {"type": "string"},
    },
    "required": ["responsable", "tarea", "plazo", "t"],
}
DECISION_SCHEMA = {
    "type": "object",
    "properties": {"decision": {"type": "string"}, "t": {"type": "string"}},
    "required": ["decision", "t"],
}

CHUNK_SCHEMA = {
    "type": "object",
    "properties": {
        "resumen": {"type": "string"},
        "temas": {"type": "array", "items": ITEM_T},
        "tareas": {"type": "array", "items": TASK_SCHEMA},
        "decisiones": {"type": "array", "items": DECISION_SCHEMA},
        "pendientes": {"type": "array", "items": ITEM_T},
    },
    "required": ["resumen", "temas", "tareas", "decisiones", "pendientes"],
}


def chunk_user(context: str, part: int, total: int, start: str, end: str, body: str) -> str:
    return f"""{("Contexto:\n" + context + "\n\n") if context else ""}Fragmento {part} de {total} \
({start} – {end}). Líneas con «Nombre:» son habla; líneas con «(pantalla)» describen lo que se ve.

{body}

Devuelve:
- resumen: resumen detallado en Markdown de este fragmento, por temas, con viñetas, citando marcas \
de tiempo. Incluye argumentos, datos, problemas, lo que se muestra en pantalla y quién dice qué.
- temas: lista de temas tratados.
- tareas: acciones acordadas o encargadas (responsable o "" si no consta, plazo o "", marca de tiempo).
- decisiones: decisiones tomadas (con marca de tiempo).
- pendientes: dudas abiertas o asuntos sin cerrar."""


FINAL_SYSTEM = """Eres un analista que redacta el informe final de una grabación (reunión o sesión de \
trabajo) a partir de los resúmenes parciales de sus fragmentos.

""" + ANALYSIS_RULES

FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "resumen_breve": {"type": "string"},
        "resumen_detallado": {"type": "string"},
        "participantes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"nombre": {"type": "string"}, "papel": {"type": "string"}},
                "required": ["nombre", "papel"],
            },
        },
        "temas": {"type": "array", "items": ITEM_T},
        "tareas": {"type": "array", "items": TASK_SCHEMA},
        "decisiones": {"type": "array", "items": DECISION_SCHEMA},
        "pendientes": {"type": "array", "items": ITEM_T},
    },
    "required": ["titulo", "resumen_breve", "resumen_detallado", "participantes", "temas", "tareas",
                 "decisiones", "pendientes"],
}


def final_user(context: str, extra: str, sections: list[str], duration: str, speakers: str, partials: str) -> str:
    sec = ""
    if sections:
        sec = "Organiza resumen_detallado con estas secciones (## en Markdown): " + "; ".join(sections) + "."
    return f"""{("Contexto:\n" + context + "\n\n") if context else ""}Duración: {duration}. \
Hablantes: {speakers}.

Resúmenes parciales en orden cronológico:

{partials}

Devuelve:
- titulo: título corto y simple (máximo 8 palabras, sin fecha, sin comillas) que identifique el vídeo.
- resumen_breve: 2-4 frases.
- resumen_detallado: informe completo en Markdown, organizado por temas, con todo el detalle relevante \
y marcas de tiempo. {sec}
- participantes: quién intervino y su papel en la reunión.
- temas, tareas, decisiones, pendientes: listas consolidadas y sin duplicados.
{("\nInstrucciones adicionales del usuario:\n" + extra) if extra else ""}"""
