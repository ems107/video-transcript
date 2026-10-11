# Prompts, glosario, identificación y resumen

Todos los prompts y esquemas están en `backend/app/prompts.py`. No pongas texto de prompt dentro de
las fases.

## Principios de los prompts

- Escribe en español, pidiendo una salida en español.
- **No inventar.** Cada prompt de análisis incluye `ANALYSIS_RULES`: usar solo la transcripción y lo
  visto en pantalla, indicar lo que no esté claro y citar `[hh:mm:ss]`. Si añades un prompt de
  análisis, compón `ANALYSIS_RULES` en él.
- **Genérico.** Nada de nombres de programas concretos, ni como ejemplo. Describe *qué* buscar, por
  ejemplo "borde iluminado, indicador de voz", sin decir en qué programa. El usuario lo pidió
  expresamente.
- **Salida con esquema.** Cada llamada usa un `*_SCHEMA` con todos los campos en `required`. Las claves
  van en español (`titulo`, `resumen_breve`, `tareas[].responsable`…) y las consumen `export.py`,
  `services.py`, `frontend/src/api.ts` (tipo `Analysis`) y `VideoDetail.tsx`. Si renombras o añades una
  clave, cambia también todos esos sitios. Los vídeos ya publicados conservan el formato antiguo en
  `Video.analysis`, así que la web debe tolerar claves ausentes.
- El contexto del perfil se construye con `profile_block(profile, people)` y se reutiliza en visión,
  correcciones y análisis.
- Temperatura: 0.2 por defecto y 0.0 para validar correcciones.

## Uso de lo aprendido en los prompts

- **`profile_dict`** añade `learned` (lo aceptado del perfil) y **`people_for`** añade a cada persona
  sus `facts` y sus alias aprendidos.
- **`profile_block`**:
  - añade «Aprendido de vídeos anteriores» (`knowledge.learned_block`), con un máximo de unos 6000
    caracteres ordenados por `seen_count`;
  - las personas salen con `knowledge.person_line`, y solo las del vídeo y del perfil
    (`prompt_people`, como máximo 30);
  - lo manual va primero y prevalece.
- **Glosario efectivo** (`knowledge.effective_glossary`): el manual seguido del aprendido.
  - Los términos aprendidos tienen `trusted=False`: en la corrección, sus coincidencias de mayúsculas
    o variante **pasan por el LLM** y nunca se aplican solas (`Candidate.trusted`).
  - En Whisper van después de los manuales.
- Las secciones del resumen son las manuales seguidas de las aprendidas (`effective_sections`).

## Aprendizaje (`LEARN_*`, `pipeline/learn.py`)

- **Llamadas al LLM.** Se hace una por bloque del `timeline` (los mismos bloques que el resumen).
- **Entrada de cada llamada:**
  - `profile_block`;
  - `known_block`: lo aceptado con su `[#id]`, para que pueda proponer `reemplaza`;
  - lo rechazado y lo pendiente de **otros** vídeos (`KS.rejected_texts`, `KS.pending_texts`), para
    que no lo repita;
  - los candidatos a término (`knowledge.term_candidates`).
- **Reglas del prompt:**
  - solo lo dicho o visto, sin deducir;
  - solo conocimiento **duradero**: se pregunta «¿seguirá siendo cierto dentro de un mes?» y da
    ejemplos de Sí y No;
  - los datos de persona no repiten su nombre;
  - «conocimiento» significa materias que domina, no hechos concretos que sabe;
  - ante la duda, listas vacías.
  - Si cambias el prompt, prueba con un vídeo real: el modelo tiende a colar detalles de la reunión.
- **Verificación en Python** (`collect_proposals`): no se confía en el LLM.
  - Un término debe aparecer literalmente (`term_occurrences`). Además debe parecer un término
    (`looks_like_term`: con mayúsculas o cifras, o visto en pantalla). No puede ser ya conocido ni el
    nombre de una persona.
  - Un hecho o dato necesita una marca de tiempo dentro del bloque y líneas reales alrededor
    (`excerpt_at`). Se descartan las frases con marcas temporales (`is_ephemeral`: «ayer», «el
    lunes», «a las 9»…).
  - Límites por vídeo: 15 términos, 10 hechos, 8 datos por persona y 5 personas nuevas.
  - La evidencia guarda etiquetas de hablante (`label`), no nombres. Los nombres se ponen al mostrarla.
- **Atribución** (`knowledge.resolve_name`): el `nombre` devuelto por el LLM se resuelve así:
  - si es un hablante del vídeo → `speaker_label`. «Hablante N» solo vale con coincidencia exacta;
  - si es una persona conocida o uno de sus alias → `person_id`;
  - si no → `nueva_persona`;
  - si no es un nombre utilizable → se descarta.
- **Cuándo se muestra lo de un hablante** (`speaker_person`): si está confirmado, o si fue reconocido
  por micrófono o por voz con ≥ `voice_auto_threshold`. Si no, queda «en espera».
- **Alias.** Si un grupo de `names.json` corresponde a una persona conocida y su forma en pantalla
  (`screen`, al menos 2 lecturas) no es su nombre ni uno de sus otros nombres, se propone como `alias`
  de esa persona. Ya no se usa el hablante activo: no es fiable y proponía nombres de otras personas.
- **Guardado** (`KS.merge_proposals`):
  1. `drop_pending_from` borra las pendientes anteriores de **este** vídeo: una nueva pasada las
     sustituye. Lo aceptado y lo rechazado se conserva.
  2. Para cada propuesta se busca un elemento equivalente del mismo dueño (`find_match`: clave idéntica
     para términos y nombres; `token_sort_ratio` ≥ 85 para frases):
     - si está rechazado o retirado, se descarta;
     - si está propuesto o aceptado, se suma la evidencia, y `seen_count` solo sube con un vídeo
       distinto.
  3. Los datos de una persona nueva se agrupan en una sola propuesta `nueva_persona`.

## Visión (`VISION_*`, `pipeline/vision.py`)

Se hace una llamada por fotograma, con un máximo de `Settings.max_frames` (240). Los fotogramas se
eligen por cambio de escena (hash perceptual), con un mínimo de 4 s y un máximo de 60 s entre ellos, y
se extraen a `Settings.frame_max_width` (2560 px). Medido con una grabación 4K: los nombres pequeños de
una videollamada se leían bien el 44 % de las veces a 1600 px, el 56 % a 1920 y el 100 % a 2560, con
1,6 veces más tiempo por fotograma. Forzar más tokens por imagen (`llm_image_*_tokens`) no mejoró nada.
`hablante_activo` **no es fiable**: el modelo suele señalar al mismo recuadro aunque hable otro, así que
la identificación nunca se basa en un fotograma suelto (ver abajo).
Para cada uno se obtienen `tipo_escena`, `aplicacion`, `descripcion`, `texto_relevante`,
`participantes`, `hablante_activo` y `terminos`. Los `terminos` y `participantes` más frecuentes
forman `screen_terms.json`, que alimenta el prompt de Whisper. `hablante_activo` alimenta la
identificación. Si un fotograma falla, se guarda un resultado vacío y el proceso sigue.

## Unificación de nombres (`pipeline/names.py`)

Cada fotograma se lee por separado, y el mismo nombre sale escrito de muchas formas. La fase `names`
(sin LLM, después de `diarize`) agrupa las lecturas y elige una forma por persona:
- **Nunca agrupa** dos nombres que aparecen a la vez entre los `participantes` de un fotograma (son
  recuadros distintos). Sí agrupa variantes de tildes y mayúsculas, el mismo nombre de pila con
  apellido mal leído, apellidos iguales al oído con distinto nombre de pila, y nombres cortos con alguna
  letra cambiada («Edge»/«Edgar»). Descarta descripciones («Usuario con gafas»).
- **Forma elegida, palabra a palabra:** gana la palabra que se oye en la transcripción (salvo
  partículas como «de») y, si no, la más leída. Una tilde se conserva si aparece en al menos el 25 %
  de las lecturas, porque al leer texto pequeño es más fácil perderla que inventarla. Si el grupo
  coincide con una persona conocida, se usa su nombre.
- Reescribe `participantes`, `hablante_activo`, y las variantes exactas dentro de `descripcion` y
  `texto_relevante`; también los nombres de pila mal leídos que solo pueden ser de un grupo.

Los tests están en `test_logic.py` con lecturas reales. Si tocas los umbrales (`SIMILAR`,
`ACCENT_SHARE`), comprueba con los datos de un vídeo real que no se mezclan personas distintas.

## Contexto inicial de Whisper (`asr.build_whisper_prompt`)

Su forma es "Reunión de trabajo en español. Participan … Se habla de …". La prioridad es: términos del
glosario, luego nombres de personas, luego términos de pantalla. Está limitado a 550 caracteres. **No
lo conviertas en instrucciones**: Whisper no sigue órdenes, solo condiciona el vocabulario, y un
prompt largo o en forma de frase provoca alucinaciones que repiten el prompt.

## Corrección con el glosario (`pipeline/glossary.py`, `pipeline/correct.py`)

Formato del glosario en el perfil: `[{term, variants[], definition}]`. En la web se escribe una línea
por término: `Término | variante1, variante2 | definición`.

Funciona en dos pasadas por intervención:
1. **Deterministas:** una coincidencia exacta con otras mayúsculas o tildes da `mayusculas`; una
   variante declarada da `variante`. Ambas se aplican directamente, y las apariciones ya correctas
   quedan protegidas.
2. **Fonéticas:** clave fonética española (`phonetic()`) y `rapidfuzz.ratio` ≥ 86, sobre ventanas de
   n−1 a n+1 palabras. Se descartan los términos de menos de 4 letras y se eligen los mejores
   candidatos sin solaparse. El LLM valida cada candidato fonético en lotes de 25, con la regla "ante
   la duda, rechaza".

En cada intervención corregida se guardan `original_text` y `corrections`, y la web los muestra.
**Nunca dejes que el LLM reescriba texto libremente.** Solo decide sí o no sobre sustituciones
concretas.

## Comprobación por la voz (`pipeline/voices.py`)

pyannote se equivoca en saludos, cambios de turno y frases cortas, y a veces deja una línea con dos
voces. La fase `voices` lo comprueba:
- **Voz de cada hablante** (`clean_centroids`): la media de sus intervenciones de 3 s o más, sin las
  que se parecen más a otro.
- **Ventanas** de 1,5 s cada 0,5 s dentro de cada intervención de 1,5 s o más. Para cada palabra se
  promedian las ventanas que la cubren, ponderadas hacia la centrada en ella (las de los lados ya
  recogen la voz vecina). Se reasigna si el ganador tiene parecido ≥ `MIN_SIM` (0,35) y saca
  ≥ `MARGIN` (0,2) al segundo. Si apunta a otro con menos margen, la palabra queda `dudosa`. Un tramo
  reasignado de menos de `MIN_RUN` (0,4 s) se deshace y queda dudoso.
- **Medido** con el vídeo de 37 min y 9 tramos que el usuario revisó escuchando: todas las
  reasignaciones fueron correctas, incluidos un saludo de 0,5 s en mitad de una línea y una línea
  partida justo donde cambia la voz. Los intercambios de varias voces en menos de 2 s («El martes 15.
  Sí. Vale.») no se pueden resolver por la voz: quedan para el arreglo manual. Si tocas los umbrales,
  vuelve a medir con tramos revisados.
- **Dos voces en un hablante** (`detect_splits`): 2-medias sobre sus intervenciones largas ya
  reasignadas. Se propone si la silueta es ≥ 0,45, cada grupo suma ≥ 15 s y los grupos se parecen
  ≤ 0,5. Se guarda en `visual_hints["_split"]`, y el usuario asigna cada grupo con arreglos manuales.
- Las huellas por intervención están en el mismo espacio que las de pyannote (parecido 0,92–0,99), así
  que los centroides limpios sustituyen a los de pyannote en `diarization.json` y son los que se
  guardan al confirmar un hablante.

## Identificación de hablantes (`pipeline/identify.py`, `pipeline/voice.py`)

Fuentes, por orden de prioridad:
1. **Micrófono:** si existe `owner.wav`, el hablante cuya actividad coincide con esa pista en al menos
   un 60 % se marca como el dueño (`Settings.owner_name`, confianza 0.95).
2. **Voz:** coseno contra el centroide de las huellas confirmadas de cada persona, con emparejamiento
   voraz uno a uno. Solo se propone si la similitud es ≥ `voice_match_threshold` (0.55). A partir de
   `voice_auto_threshold` (0.75) la confianza es alta. Si la pantalla confirma la misma persona, la
   confianza sube a ≥ 0.9.
3. **Pantalla** (`voice.assign_visual_names`): con los nombres ya unificados, cada nombre se asigna a
   un solo hablante, el que más coincide con él (al menos 2 coincidencias, el nombre más leído de ese
   hablante sin empate, y ese hablante debe concentrar al menos la mitad de las lecturas del nombre). Un nombre
   repartido entre varias voces, como el de quien presenta, no se asigna. Se busca en las personas por
   nombre o alias (`token_set_ratio` ≥ 85). Si no existe, queda como `suggested_name`.
4. **Contexto** (en `analyze`, ver abajo): para los hablantes que siguen sin nombre, el LLM propone una
   identidad con su motivo. `source = "contexto"`, confianza 0.5.

Las pistas internas de un hablante (`_motivo`, `_apodos`) se guardan en `Speaker.visual_hints` con
claves que empiezan por «_»; el resto del código las ignora y la API las expone como `reason` y
`aliases`. Al confirmar la propuesta como persona nueva, los apodos pasan a sus `aliases`.

**Nada se confirma solo.** El usuario confirma en la web (`PUT /api/speakers/{id}` o
`confirm-speakers`). Cada confirmación guarda un `VoiceEmbedding`, así que confirmar mal contamina
futuras identificaciones (la página Personas tiene la opción «Olvidar voz»). Si cambias umbrales,
ajusta `test_voice_matching`.

## Resumen (`pipeline/analyze.py`)

Es un map-reduce. Se monta una línea temporal con habla y descripciones de pantalla, y se trocea en
bloques de `chunk_minutes` (30 min, con un máximo de 90 000 caracteres). Cada bloque pasa por
`CHUNK_*`, que da resumen, temas, tareas, decisiones y pendientes. Después, `FINAL_*` con todos los
parciales produce `titulo` (máximo 8 palabras), resúmenes, participantes y listas consolidadas. Usa
`extra_prompt` y `summary_sections` del perfil. Los parciales se guardan en `analysis.partial.json`
para poder reanudar, y quedan en `analysis["fragmentos"]`.

**Quién es quién.** `who_block` se añade a cada bloque y al final: los participantes unificados con al
menos 2 lecturas (`analyze.participants`) y el estado de cada hablante (`ctx.speaker_status`:
confirmado, probable por voz/pantalla/contexto, o sin identificar). Pide usar siempre la forma exacta
de la lista. Un nombre oído que no está en ella solo se atribuye a un participante si el contexto lo
deja claro; si no, se escribe tal como se oye. (Una versión anterior pedía atribuirlos «si corresponden»
y la IA adivinaba: escribió que un apodo de una persona era de otra.) Cada bloque
devuelve además `identidades` (para «Hablante N») y `apodos`. `collect_identities` los verifica en
Python: el nombre debe estar en la lista o oírse; el apodo debe oírse, no ser el nombre de pila de
otro participante y parecerse a una parte del nombre de la persona (`NICKNAME_SIMILAR`: «Selu» en
«JoSELUis»; en una ejecución real el LLM atribuyó «Selu» a Sandra, y esta regla lo descarta); no se repite un nombre ya asignado, y un empate entre dos nombres no decide nada.
El resultado se guarda en `context_identities.json`, se aplica a los hablantes libres
(`services.apply_context_identities`, nunca sobre lo confirmado ni sobre propuestas de voz o pantalla)
y el informe final ya lo recibe en el bloque.

Las personas aparecen en los prompts con sus otros nombres («también llamado …», `person_line`), y en
el prompt de Whisper como «Nombre (alias)».

Al renombrar un hablante después de publicar, `services.replace_speaker_name` sustituye el nombre en
todo el análisis sin llamar al LLM. «Regenerar análisis» tiene niveles (ver `AI_PIPELINE.md`).

**Correcciones del usuario** (`VideoCorrection`, `prompts.corrections_block`). Son hechos escritos por
el usuario sobre un vídeo («X es quien presenta, no Y»). Se añaden al contexto de cada bloque, del
informe final y del aprendizaje, con la indicación de que prevalecen sobre la transcripción y la
pantalla. No se verifican en Python: son la verdad del usuario. `analysis.json` guarda
`correcciones_aplicadas` (`id` y `updated_at`): `services.with_applied` marca cada corrección y
`services.corrections_pending` avisa si las actuales no coinciden. La IA no ve el análisis anterior, así
que una corrección debe ser un hecho sobre el vídeo, no una referencia al resumen. La IA nunca las escribe ni las modifica.

**Respuestas no válidas.** `llm.chat_json` guarda en `data/llm_failures/` cada respuesta que no es JSON
válido, con su `finish_reason` y los mensajes sin imágenes. Si `finish_reason == "length"`, no se
reintenta, porque la misma petición se volvería a cortar. Antes de subir un `max_tokens`, mira ahí el
caso real: puede ser una repetición en bucle y no falta de espacio.
