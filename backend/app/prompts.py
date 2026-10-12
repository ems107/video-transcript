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
- El contexto que se te da (tipo de vídeo, personas, vídeos anteriores, notas del usuario) sirve para \
entender lo que se dice, pero no forma parte de esta grabación: no cuentes sus datos (edades, estudios, \
cargos, lo que pasó en otros vídeos) como si se dijeran aquí, salvo que se digan o se vean en ella.
- Un plazo solo si se dice; no lo deduzcas (por ejemplo, «antes de la próxima reunión» sin que nadie lo diga).
- Cita la marca de tiempo [hh:mm:ss] de donde sale cada punto importante.
- Escribe en español."""

CHUNK_SYSTEM = """Eres un analista que resume grabaciones de reuniones y sesiones de trabajo \
(videollamadas, demostraciones, revisión de código) a partir de su transcripción con hablantes y de \
la descripción de lo que se ve en pantalla.

""" + ANALYSIS_RULES

ITEM_T = {"type": "string"}
# Marca de tiempo con formato obligatorio (la gramática de llama.cpp lo impone). Sin él, el modelo a veces
# ponía en «t» el texto de la tarea o una fecha copiada del contexto; y con una hora libre escribía «20:42:00»
# por el minuto 20:42. La hora empieza por 0 (hasta 9 h de vídeo), como en las marcas de la transcripción.
TS_T = {"type": "string", "pattern": "^0[0-9]:[0-5][0-9]:[0-5][0-9]$"}
TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "responsable": {"type": "string"},
        "tarea": {"type": "string"},
        "plazo": {"type": "string"},
        "t": TS_T,
    },
    "required": ["responsable", "tarea", "plazo", "t"],
}
DECISION_SCHEMA = {
    "type": "object",
    "properties": {"decision": {"type": "string"}, "t": TS_T},
    "required": ["decision", "t"],
}
PENDING_SCHEMA = {
    "type": "object",
    "properties": {"pendiente": {"type": "string"}, "t": TS_T},
    "required": ["pendiente", "t"],
}

CHUNK_SCHEMA = {
    "type": "object",
    "properties": {
        "resumen": {"type": "string"},
        "temas": {"type": "array", "items": ITEM_T},
        "tareas": {"type": "array", "items": TASK_SCHEMA},
        "decisiones": {"type": "array", "items": DECISION_SCHEMA},
        "pendientes": {"type": "array", "items": PENDING_SCHEMA},
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
Nombra a cada persona de la lista siempre con la forma exacta que aparece en ella. Un nombre oído que \
no está en la lista (un apodo, un diminutivo o un nombre mal transcrito) puede ser de un participante o \
de otra persona: atribúyelo a un participante solo si el contexto lo deja claro, por ejemplo porque se \
dirigen a él con ese nombre y es él quien responde. Si no está claro, escríbelo tal como se oye y no lo \
relaciones con nadie."""


def corrections_block(texts: list[str]) -> str:
    """Correcciones del usuario sobre el vídeo: hechos que prevalecen sobre lo que parezca decir la grabación.

    Se presentan como notas ajenas a la grabación: si no, el resumen las contaba como algo dicho en la
    reunión («X aclara que…», con una marca de tiempo)."""
    texts = [t.strip() for t in texts if t.strip()]
    if not texts:
        return ""
    return ("Notas del usuario sobre este vídeo. Son hechos verificados y prevalecen sobre lo que parezca \
decir la transcripción o la pantalla: úsalas para escribir bien quién es quién, los nombres y lo que se \
dice. No son parte de la grabación ni las dice nadie en ella: no las atribuyas a ningún participante, no \
les pongas marca de tiempo y no las cuentes como algo que se dijo o se aclaró en la reunión:\n"
            + "\n".join(f"- {t}" for t in texts))


def chunk_user(context: str, part: int, total: int, start: str, end: str, body: str, who: str = "") -> str:
    return f"""{("Contexto:\n" + context + "\n\n") if context else ""}{(who + "\n\n") if who else ""}\
Fragmento {part} de {total} ({start} – {end}). Líneas con «Nombre:» son habla; líneas con «(pantalla)» \
describen lo que se ve.

{body}

Devuelve:
- resumen: resumen detallado en Markdown de este fragmento, por temas, con viñetas, citando marcas \
de tiempo. Incluye argumentos, datos, problemas, lo que se muestra en pantalla y quién dice qué.
- temas: lista de temas tratados.
- tareas: acciones acordadas o encargadas (responsable o "" si no consta, plazo tal como se dice o "", marca de \
tiempo hh:mm:ss de este vídeo).
- decisiones: decisiones tomadas (con su marca de tiempo hh:mm:ss).
- pendientes: dudas abiertas o asuntos sin cerrar (con la marca de tiempo hh:mm:ss donde se plantean).
- identidades: solo para hablantes que aparecen como «Hablante N»: su nombre, si este fragmento lo deja \
claro (por ejemplo, se presenta, o alguien se dirige a él por su nombre y es él quien responde). Indica \
el motivo y la marca de tiempo. Lista vacía si no está claro.
- apodos: nombres oídos en la transcripción que son apodos, diminutivos o malas transcripciones del \
nombre de un participante de la lista (el apodo tal como aparece escrito, el nombre del participante y \
la primera marca de tiempo). Cada apodo una sola vez. Lista vacía si no hay."""


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
        "pendientes": {"type": "array", "items": PENDING_SCHEMA},
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
- temas, tareas, decisiones, pendientes: listas consolidadas y sin duplicados, cada punto con la marca \
de tiempo hh:mm:ss de este vídeo donde se trata; el plazo, solo si se dice y tal como se dice. Cada \
asunto va en una sola lista: si alguien debe hacer algo, es una tarea, aunque también quede por resolver; \
los pendientes son las dudas o asuntos abiertos que no son ya una tarea ni una decisión.
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
        "correcciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"oido": {"type": "string"}, "correcto": {"type": "string"},
                               "motivo": {"type": "string"}, "t": {"type": "string"}},
                "required": ["oido", "correcto", "motivo", "t"],
            },
        },
    },
    "required": ["terminos", "contexto", "personas", "secciones", "correcciones"],
}


def learn_user(context: str, known: str, rejected: list[str], candidates: list[str], part: int, total: int,
               start: str, end: str, body: str, with_profile: bool, want_sections: bool,
               pending: list[str] | None = None) -> str:
    profile_part = (
        "- terminos: términos del negocio que aparecen (siglas, productos, sistemas, nombres propios que no sean "
        "personas), escritos tal como aparecen; no palabras comunes. definicion: qué es, de forma general y "
        "duradera, solo si se explica o es evidente; si no, cadena vacía.\n"
        "- contexto: hechos duraderos del negocio (categoria: proyecto, cliente, sistema, proceso, sigla u otro).\n"
        "- correcciones: nombres propios o términos del negocio que la transcripción escribe mal (suenan como "
        "otro nombre que encaja por el contexto, la pantalla o las notas del usuario; por ejemplo, una empresa "
        "conocida escrita como otra palabra). oido: tal como aparece escrito en la transcripción; correcto: "
        "cómo se escribe; motivo: por qué lo crees; t: la marca de tiempo. No incluyas palabras comunes ni "
        "faltas de ortografía. Lista vacía si no hay.\n"
        if with_profile else "- terminos, contexto y correcciones: listas vacías.\n"
    )
    sections = ("- secciones: hasta 5 títulos de secciones para organizar el resumen de cualquier vídeo de este \
tipo, no solo de este. Deben servir aunque el próximo vídeo trate otro tema: describen la estructura (por \
ejemplo, qué se trató, qué se decidió, qué queda pendiente), no el contenido concreto de esta reunión, \
sus herramientas ni sus personas."
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


# --------------------------------------------------------------------------- juicio de las propuestas

# Segunda pasada: la IA revisa todas las propuestas juntas antes de enseñarlas. La extracción, fragmento a
# fragmento, proponía lo que se explicaba en la reunión como datos de quien lo explicaba («Sabe que la regla
# del 72…») y términos sin valor para el perfil; pedírselo con más fuerza en el mismo prompt no bastaba.
JUDGE_SYSTEM = """Revisas lo que la IA ha propuesto aprender de una grabación (reunión o sesión de trabajo) \
antes de enseñárselo al usuario. Lo aceptado se usará para reconocer a las personas y para entender y \
transcribir las próximas grabaciones del mismo tipo. Razona cada propuesta con lo que se sabe del vídeo y \
de su evidencia; no apliques reglas fijas por palabras."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "propuestas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "valor": {"type": "string", "enum": ["util", "dudosa", "descartar"]},
                    "motivo": {"type": "string"},
                    "igual_que": {"type": "integer"},
                    "ya_guardado": {"type": "integer"},
                },
                "required": ["id", "valor", "motivo", "igual_que", "ya_guardado"],
            },
        },
        "secciones": {
            "type": "object",
            "properties": {
                "encajan": {"type": "boolean"},
                "motivo": {"type": "string"},
                "propuestas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"titulo": {"type": "string"}, "reemplaza": {"type": "integer"}},
                        "required": ["titulo", "reemplaza"],
                    },
                },
            },
            "required": ["encajan", "motivo", "propuestas"],
        },
    },
    "required": ["propuestas", "secciones"],
}


def judge_user(about: str, profile: str, sections: str, proposals: str, known: str = "") -> str:
    sec = (f"""
Secciones con las que se organiza el resumen de este tipo de vídeo:
{sections}
""" if sections else "")
    sec += (f"""
Ya guardado en el perfil (aceptado en vídeos anteriores):
{known}
""" if known else "")
    return f"""De qué trata el vídeo:
{about}

Tipo de vídeo: {profile or "(sin perfil)"}
{sec}
Propuestas (número, a quién o a qué se refiere, tipo, texto y una frase de ejemplo):
{proposals}

La frase de un término o de una corrección solo muestra dónde aparece: juzga el término por sí mismo, por \
cuántas veces aparece y por el tema del vídeo, no por esa frase. La de un dato de una persona sí debe \
decirlo.

Para cada propuesta devuelve:
- id: su número.
- valor: «util» si es un dato duradero de una persona para su ficha (quién es, su cargo, su organización, \
su relación con los demás, cómo la llaman, y también sus datos personales: estudios, edad, familia, \
contacto, documento o dirección, que el usuario quiere guardar) o si ayuda a entender o transcribir \
próximas grabaciones de este tipo (un término o un \
nombre que se repetirá, cómo se oye mal un nombre, un hecho duradero del negocio); «dudosa» si puede servir \
pero no está claro, o si la frase de la que sale no lo dice del todo; «descartar» si es contenido puntual \
de esta reunión (lo que se explicó, se enseñó o se hizo en ella, una tarea, un dato de un momento), algo \
obvio, algo que se ve en pantalla sin relación con el tema, o algo que la frase no dice.
- motivo: por qué, en pocas palabras.
- igual_que: el número de otra propuesta de esta lista que dice lo mismo (la que sobra lleva el número de \
la que se queda), o 0.
- ya_guardado: el número [#…] de lo ya guardado que la propuesta repite sin añadir nada nuevo (aunque esté \
escrito de otra forma), o 0. Si añade algo que lo guardado no dice, no es una repetición: 0.
Y en «secciones»: encajan (si las secciones sirven para organizar el resumen de este vídeo y de los \
siguientes de este tipo), motivo, y propuestas: si no encajan, hasta 2 títulos generales que sirvan para \
cualquier vídeo de este tipo (reemplaza: el número [#…] de la sección que sustituye, o 0). Si encajan o no \
hay secciones, lista vacía."""


# Correcciones de transcripción que el usuario escribe en sus notas del vídeo
NOTES_SYSTEM = """Lees las notas que un usuario ha escrito sobre la transcripción de una grabación y sacas \
las palabras o nombres que dice que están mal transcritos, con su forma correcta. Solo lo que dicen las \
notas: no deduzcas nada."""

NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "pares": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"oido": {"type": "string"}, "correcto": {"type": "string"}},
                "required": ["oido", "correcto"],
            },
        },
    },
    "required": ["pares"],
}


def notes_user(notes: list[str]) -> str:
    return "Notas del usuario:\n" + "\n".join(f"- {n}" for n in notes) + """

Devuelve en «pares» cada palabra o nombre que según las notas está mal escrito en la transcripción: oido, \
tal como aparece mal escrito; correcto, cómo debe escribirse. Si una nota dice que algo «no se escribe» de \
una forma, esa forma es la oída. Lista vacía si las notas no hablan de cómo se escribe nada."""


# --------------------------------------------------------------------------- seguimientos

def followup_block(states: list[str]) -> str:
    """Estado de los seguimientos del vídeo, como contexto del análisis."""
    states = [s for s in states if s.strip()]
    if not states:
        return ""
    return ("Este vídeo continúa uno o varios temas tratados en vídeos anteriores. Estado del tema según \
esos vídeos (solo para entender referencias y relacionar; no es parte de este vídeo):\n\n"
            + "\n\n".join(states) + """

Usa este estado solo para entender a qué se refiere lo que se dice y para relacionarlo con lo anterior \
(por ejemplo, «continúa lo de…» o «da por hecha la tarea de…»), solo si se dice en este vídeo y con la \
marca de tiempo de este vídeo. No añadas al resumen, a las tareas ni a las decisiones nada que no se \
diga o se vea en este vídeo.""")


FOLLOW_SYSTEM = """Mantienes el estado de un tema que se trata a lo largo de varias grabaciones (reuniones \
o sesiones de trabajo): sus tareas, decisiones y dudas, y un resumen de su evolución. Recibes el estado \
según los vídeos anteriores y el análisis de un vídeo nuevo, y devuelves solo lo que cambia.

""" + ANALYSIS_RULES

FOLLOW_SCHEMA = {
    "type": "object",
    "properties": {
        "clasificacion": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nuevo": {"type": "string"},
                    "relacion": {"type": "string", "enum": ["mismo", "nuevo", "dudoso"]},
                    "existente": {"type": "string"},
                    "motivo": {"type": "string"},
                },
                "required": ["nuevo", "relacion", "existente", "motivo"],
            },
        },
        "resumen": {"type": "string"},
        "aporte": {"type": "string"},
    },
    "required": ["clasificacion", "resumen", "aporte"],
}

# Qué dice el vídeo de cada punto abierto. Va aparte y con el modo razonamiento: dentro del resumen, o sin
# razonar, el modelo no encontraba los cierres dichos de pasada («lo que ayer fallaba ya ha funcionado») e
# inventaba momentos y citas (medido con vídeos reales)
FOLLOW_CHECK_SYSTEM = """Revisas la transcripción de una reunión para saber qué dice sobre asuntos pendientes \
de reuniones anteriores. Solo cuenta lo que se dice en la transcripción; no deduzcas nada que no se diga."""

FOLLOW_CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "menciones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "evento": {"type": "string", "enum": ["avanza", "hecha", "descartada", "reabierta", "cambiada",
                                                          "anulada", "resuelta"]},
                    "t": TS_T,
                    "cita": {"type": "string"},
                },
                "required": ["id", "evento", "t", "cita"],
            },
        },
    },
    "required": ["menciones"],
}


def follow_check_user(points: str, video: str, part: int, total: int, body: str, about: str = "") -> str:
    meeting = (f"""
De qué trata esta reunión: {about}
Si un asunto es hacer esta misma reunión o sesión (por ejemplo, «realizar la sesión de X» y esta es esa \
sesión), está hecho: márcalo con la primera frase que muestre que se está haciendo.
""" if about else "")
    return f"""Asuntos pendientes de reuniones anteriores del mismo tema:
{points}
{meeting}
Transcripción de la reunión del {video} (parte {part} de {total}):
{body}

Para cada asunto del que se hable en esta parte, devuelve:
- id: el del asunto ([T…] tarea, [D…] decisión, [P…] duda).
- evento: hecha o descartada (tareas), cambiada o anulada (decisiones), resuelta (dudas), reabierta, o \
avanza si se habla de él pero sigue igual.
- t: la marca de tiempo de la frase.
- cita: la frase que lo dice, copiada literalmente, sin comillas ni puntos suspensivos.
Se puede hablar de un asunto sin nombrarlo igual (por ejemplo, «lo que ayer fallaba ya funciona» o «ya \
sale como predeterminado»). Algo que se dice que se hará después de la reunión no está hecho aunque se \
hable de ello. Si no se habla de un asunto, no lo pongas."""


def follow_user(state: str, video: str, analysis: str, contributions: list[str] | None = None,
                hidden: str = "") -> str:
    previous = ("Estado del tema según los vídeos anteriores:\n" + state) if state else \
        "Es el primer vídeo del tema: aún no hay estado."
    history = ("\n\nLo que aportó cada vídeo anterior, en orden:\n" + "\n".join(f"- {c}" for c in contributions)) \
        if contributions else ""
    removed = ("\n\nPuntos que el usuario borró: no se vuelven a crear (si un punto de este vídeo es uno de ellos, "
               "es «mismo»):\n" + hidden) if hidden else ""
    return f"""{previous}{history}{removed}

Vídeo nuevo: {video}

{analysis}

Devuelve:
- clasificacion: una entrada por cada punto de este vídeo ([N…]). relacion: «mismo» si es el mismo asunto \
que un punto anterior (del estado, uno borrado por el usuario u otro punto de este vídeo), aunque cambie la \
redacción o el detalle (la misma tarea encargada otra vez, o la misma cuestión como tarea y como duda); \
«nuevo» si no tiene que ver con ninguno; «dudoso» si puede ser el mismo pero no está claro. existente: el \
id con el que lo comparas ([T…], [D…], [P…] o [N…]), o "" si es nuevo. motivo: por qué, en pocas palabras. \
Una decisión que cambia otra anterior no es «la misma».
- resumen: la evolución del tema desde el primer vídeo hasta este incluido, en 1-3 párrafos: de dónde se \
partió, qué ha pasado en cada vídeo y dónde está ahora. Usa lo que aportó cada vídeo anterior y el estado \
de los puntos; no lo centres en este vídeo. Si citas un momento, escribe la fecha de su vídeo y la marca, \
así: [AAAA-MM-DD hh:mm:ss]. Usa lo que dicen las menciones comprobadas sobre los asuntos anteriores; no \
des por hecho lo que no dicen.
- aporte: lo que aporta este vídeo al tema, en 1-3 frases."""


# --------------------------------------------------------------------------- términos vistos solo en pantalla

SCREEN_SYSTEM = """Valoras si los términos que solo se han visto en pantalla durante una grabación (reunión o \
sesión de trabajo) tienen relación con lo que se trata en ella. La pantalla puede mostrar contenido de la \
reunión, pero también el escritorio, pestañas, notificaciones o programas ajenos a ella: depende del vídeo. \
Razona con lo que se sabe del vídeo y de dónde aparece cada término; no lo decidas por el tipo de programa \
ni por lo conocido que sea."""

SCREEN_SCHEMA = {
    "type": "object",
    "properties": {
        "terminos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "termino": {"type": "string"},
                    "relacion": {"type": "string", "enum": ["relacionado", "dudoso", "sin_relacion"]},
                    "motivo": {"type": "string"},
                },
                "required": ["termino", "relacion", "motivo"],
            },
        },
    },
    "required": ["terminos"],
}


def screen_user(about: str, terms: str) -> str:
    return f"""De qué trata la grabación:
{about}

Términos que no se mencionan en la conversación y solo se ven en pantalla, con dónde aparecen:
{terms}

Para cada término, devuelve:
- relacion: «relacionado» si forma parte de lo que se trabaja, se muestra o se consulta en la reunión; \
«sin_relacion» si es algo de la pantalla ajeno a la reunión (por ejemplo, otras pestañas o programas abiertos \
que no se usan); «dudoso» si no está claro. Si dudas entre «relacionado» y «sin_relacion», responde «dudoso»: lo decidirá el usuario.
- motivo: por qué, en una frase, citando lo que lo indica (cuándo y dónde aparece, qué se ve)."""


# --------------------------------------------------------------------------- límites de las listas

# Sin un máximo, el modelo puede entrar en un bucle repitiendo un elemento hasta agotar los tokens (pasó
# con «apodos»: la misma pareja decenas de veces). El límite se aplica en la gramática de llama.cpp.
LIST_LIMITS = {"apodos": 10, "identidades": 10, "participantes": 20, "terminos": 30, "secciones": 12,
               "clasificacion": 40, "menciones": 20, "correcciones": 15, "propuestas": 30}
LIST_DEFAULT = 40


def _limit_lists(schema: Any) -> None:
    if not isinstance(schema, dict):
        return
    for key, sub in (schema.get("properties") or {}).items():
        if isinstance(sub, dict) and sub.get("type") == "array":
            sub.setdefault("maxItems", LIST_LIMITS.get(key, LIST_DEFAULT))
        _limit_lists(sub)
    _limit_lists(schema.get("items"))


for _schema in (VISION_SCHEMA, CORRECT_SCHEMA, CHUNK_SCHEMA, FOLLOW_CHECK_SCHEMA, FINAL_SCHEMA, LEARN_SCHEMA,
                FOLLOW_SCHEMA, SCREEN_SCHEMA):
    _limit_lists(_schema)
