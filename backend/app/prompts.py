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
        "identidades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"hablante": ITEM_T, "nombre": ITEM_T, "motivo": ITEM_T, "t": ITEM_T},
                "required": ["hablante", "nombre", "motivo", "t"],
            },
        },
        "apodos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"apodo": ITEM_T, "nombre": ITEM_T, "t": ITEM_T},
                "required": ["apodo", "nombre", "t"],
            },
        },
    },
    "required": ["resumen", "temas", "tareas", "decisiones", "pendientes", "identidades", "apodos"],
}


def who_block(participants: list[str], speakers: list[tuple[str, str]], nicknames: dict[str, list[str]]) -> str:
    """Quién es quién en el vídeo, para que el LLM nombre siempre igual a cada persona."""
    lines = []
    if participants:
        lines.append("- Participantes que se ven en pantalla: " + "; ".join(participants) + ".")
    if speakers:
        lines.append("- Hablantes de la transcripción:")
        lines += [f"  - {shown}: {status or 'sin identificar'}" for shown, status in speakers]
    if nicknames:
        pairs = [", ".join(f"«{a}»" for a in alias) + f" = {name}" for name, alias in nicknames.items()]
        lines.append("- Apodos o formas oídas de sus nombres: " + "; ".join(pairs) + ".")
    if not lines:
        return ""
    return "Quién es quién:\n" + "\n".join(lines) + """
Nombra a cada persona siempre con la forma exacta de esta lista. La transcripción automática puede \
escribir mal los nombres oídos, y la gente usa apodos y diminutivos: si por el contexto un nombre oído \
corresponde a un participante de la lista, usa el nombre del participante."""


def chunk_user(context: str, part: int, total: int, start: str, end: str, body: str, who: str = "") -> str:
    return f"""{("Contexto:\n" + context + "\n\n") if context else ""}{(who + "\n\n") if who else ""}\
Fragmento {part} de {total} ({start} – {end}). Líneas con «Nombre:» son habla; líneas con «(pantalla)» \
describen lo que se ve.

{body}

Devuelve:
- resumen: resumen detallado en Markdown de este fragmento, por temas, con viñetas, citando marcas \
de tiempo. Incluye argumentos, datos, problemas, lo que se muestra en pantalla y quién dice qué.
- temas: lista de temas tratados.
- tareas: acciones acordadas o encargadas (responsable o "" si no consta, plazo o "", marca de tiempo).
- decisiones: decisiones tomadas (con marca de tiempo).
- pendientes: dudas abiertas o asuntos sin cerrar.
- identidades: solo para hablantes que aparecen como «Hablante N»: su nombre, si este fragmento lo deja \
claro (por ejemplo, se presenta, o alguien se dirige a él por su nombre y es él quien responde). Indica \
el motivo y la marca de tiempo. Lista vacía si no está claro.
- apodos: nombres oídos en la transcripción que son apodos, diminutivos o malas transcripciones del \
nombre de un participante de la lista (el apodo tal como aparece escrito, el nombre del participante y \
la marca de tiempo). Lista vacía si no hay."""


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


def final_user(context: str, extra: str, sections: list[str], duration: str, speakers: str, partials: str,
               who: str = "") -> str:
    sec = ""
    if sections:
        sec = "Organiza resumen_detallado con estas secciones (## en Markdown): " + "; ".join(sections) + "."
    names = ""
    if who:
        names = "\n" + who + " Si un hablante tiene un nombre probable, nómbralo así y no como «Hablante N».\n"
    return f"""{("Contexto:\n" + context + "\n\n") if context else ""}Duración: {duration}. \
Hablantes: {speakers}.
{names}
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


# --------------------------------------------------------------------------- aprendizaje

LEARN_SYSTEM = """Extraes conocimiento duradero de la grabación de una reunión o sesión de trabajo para \
completar dos fichas:
- la del tipo de vídeo (perfil): proyectos, clientes, sistemas, procesos, siglas y términos del negocio;
- la de cada persona: cargo, organización, equipo, responsabilidades, proyectos, conocimientos, relaciones \
y cualquier dato personal que se mencione.

Reglas:
- Solo lo que se dice o se ve explícitamente. No deduzcas rasgos, intenciones ni opiniones.
- Conocimiento útil para entender futuras grabaciones. NO incluyas lo puntual de esta reunión: tareas, \
acuerdos, plazos, fechas de entrega, estado de avance, incidencias concretas, propuestas o lo que se hará \
próximamente. Pregúntate: ¿seguirá siendo cierto y útil dentro de un mes? Si no, no lo incluyas. Vale \
quién se encarga de qué de forma habitual, a qué equipo u organización pertenece alguien o qué es cada \
sistema o proyecto; no vale lo que alguien hizo, revisó o propuso en esta reunión.
- Cada dato en una frase breve y autocontenida, en español, usando las palabras de la transcripción. En \
los datos de una persona no repitas su nombre: empieza por el verbo.
- Lo que alguien dice de sí mismo («yo llevo…») es un dato de quien habla; lo que se dice de otra \
persona es un dato de esa persona.
- No repitas lo ya conocido. Si algo nuevo lo actualiza o contradice, pon su número en «reemplaza»; \
si no, 0.
- Indica la marca de tiempo [hh:mm:ss] de donde sale cada dato.
- Ante la duda, no lo incluyas: mejor poco y seguro. En muchas reuniones no hay nada nuevo que aprender: \
devuelve entonces listas vacías."""

PROFILE_CATEGORY_ENUM = ["proyecto", "cliente", "sistema", "proceso", "sigla", "otro"]
PERSON_CATEGORY_ENUM = ["cargo", "organizacion", "equipo", "responsabilidad", "proyecto", "conocimiento",
                        "relacion", "personal", "otro"]

LEARN_SCHEMA = {
    "type": "object",
    "properties": {
        "terminos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"termino": {"type": "string"}, "definicion": {"type": "string"}, "t": {"type": "string"}},
                "required": ["termino", "definicion", "t"],
            },
        },
        "contexto": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "categoria": {"type": "string", "enum": PROFILE_CATEGORY_ENUM},
                    "texto": {"type": "string"},
                    "t": {"type": "string"},
                    "reemplaza": {"type": "integer"},
                },
                "required": ["categoria", "texto", "t", "reemplaza"],
            },
        },
        "personas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string"},
                    "categoria": {"type": "string", "enum": PERSON_CATEGORY_ENUM},
                    "dato": {"type": "string"},
                    "t": {"type": "string"},
                    "reemplaza": {"type": "integer"},
                },
                "required": ["nombre", "categoria", "dato", "t", "reemplaza"],
            },
        },
        "secciones": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["terminos", "contexto", "personas", "secciones"],
}


def learn_user(context: str, known: str, rejected: list[str], candidates: list[str], part: int, total: int,
               start: str, end: str, body: str, with_profile: bool, want_sections: bool,
               pending: list[str] | None = None) -> str:
    profile_part = (
        "- terminos: términos del negocio que aparecen (siglas, productos, sistemas, nombres propios que no sean "
        "personas), escritos tal como aparecen; no palabras comunes. definicion: qué es, de forma general y "
        "duradera, solo si se explica o es evidente; si no, cadena vacía.\n"
        "- contexto: hechos duraderos del negocio (categoria: proyecto, cliente, sistema, proceso, sigla u otro).\n"
        if with_profile else "- terminos y contexto: listas vacías.\n"
    )
    sections = ("- secciones: hasta 5 títulos de secciones útiles para resumir este tipo de reuniones."
                if want_sections else "- secciones: lista vacía.")
    return f"""{("Contexto:\n" + context + "\n\n") if context else ""}{("Ya conocido (no lo repitas):\n" + known + "\n\n") if known else ""}\
{("Rechazado antes por el usuario (no lo propongas):\n" + "\n".join("- " + r for r in rejected) + "\n\n") if rejected else ""}\
{("Ya propuesto y pendiente de revisar (no lo repitas, ni con otras palabras):\n" + "\n".join("- " + r for r in pending) + "\n\n") if pending else ""}\
{("Posibles términos detectados (pueden no serlo):\n" + ", ".join(candidates) + "\n\n") if candidates and with_profile else ""}\
Fragmento {part} de {total} ({start} – {end}). Líneas con «Nombre:» son habla; líneas con «(pantalla)» \
describen lo que se ve.

{body}

Devuelve:
{profile_part}- personas: datos sobre personas. nombre: el nombre tal como aparece antes de «:» si es quien habla, o \
el de la persona mencionada. categoria: cargo, organizacion, equipo, responsabilidad, proyecto, conocimiento \
(materias o sistemas que domina, no hechos concretos que sabe), relacion, personal u otro. dato: la frase.
{sections}"""
