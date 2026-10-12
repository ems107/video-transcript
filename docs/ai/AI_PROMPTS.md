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
  - Si no se oye (`K.heard`), es un término **solo de pantalla** y la IA razona si tiene relación con el
    vídeo (`learn.judge_screen_terms`, `SCREEN_*`): recibe título, resumen y temas, y por cada término
    `K.screen_summary` (fotogramas, momentos, escenas, si está en el contenido principal o solo en lo
    demás legible, y descripciones). `apply_judgment`: «sin_relacion» no se propone (queda en
    `screen_judgment.json`); «dudoso» se propone con `data.pantalla = {relacion, motivo}`, y la web lo marca y
    lo deja fuera de «Aceptar todas»; lo no valorado cuenta como dudoso. Antes había una regla fija (estar en
    el `texto_relevante` de 3 fotogramas): dejaba pasar pestañas del navegador (Trello, Jira y Firefox
    aparecían en el texto relevante de 4–5 fotogramas seguidos antes de una llamada) y una regla más dura
    quitaba términos reales del contenido. Lo que es ruido depende del vídeo: hay que razonarlo.
  - Las formas de un mismo nombre se juntan en una propuesta (`group_forms`: una contiene a la otra sin
    espacios ni signos, mínimo 6 letras). La más vista es el término y las demás van en `data.forms`, que
    se muestran en la web, entran en el contexto del LLM («también …») y orientan a Whisper. **No** son
    `variants` del glosario: esas se sustituyen en la transcripción, y «Gestibarymont» no es un error de
    «Bárymont».
  - Las secciones del resumen se piden reutilizables para cualquier vídeo del perfil (estructura, no
    contenido): sin esa indicación proponía títulos de la reunión concreta.
  - Un hecho o dato necesita una marca de tiempo dentro del bloque y líneas reales alrededor
    (`excerpt_at`). Se descartan las frases con marcas temporales (`is_ephemeral`: «ayer», «el
    lunes», «a las 9»…).
  - Límites por vídeo (40 términos, 30 hechos, 40 datos por persona, 15 personas nuevas): solo protegen
    frente a respuestas anómalas. Antes eran 15/10/8/5 y descartaban datos buenos por orden de llegada
    (en un vídeo real, Edgar perdió datos al llegar a 8). El ruido lo limitan las comprobaciones de
    cada propuesta, no el número.
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
  La voz de cada grupo (`centroid`, solo en `voices.json`) se compara al identificar con las huellas de
  otros vídeos (`speaker_fix.split_suggestions`: `greedy_assign` con `voice_match_threshold`) y da
  `suggested`, que el diálogo trae elegido. En p7, el grupo de Edgar salió a 0,95 de su huella; el de Selu
  (21 s, con huella de un solo vídeo de 58 s), a 0,41: sin propuesta. No se bajó el umbral por un caso.
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
   hablante sin empate, y esa voz con al menos 1,5 veces las lecturas del nombre que la siguiente).
   Cada fotograma se asigna con `transcript.speaker_at` sobre las intervenciones ya comprobadas por la
   voz: el fotograma se toma al cambiar el resaltado, un poco antes de la primera palabra, así que a
   menos de 0,3 s (`BORDER`) de un límite gana el turno que empieza; en un silencio no cuenta. Un nombre
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
informe final y del aprendizaje, como «notas del usuario» que prevalecen sobre la transcripción y la
pantalla pero que no son parte de la grabación (antes, el resumen las contaba como algo dicho en la
reunión: «X aclara que…»). No se verifican en Python: son la verdad del usuario. `analysis.json` guarda
`correcciones_aplicadas` (`id` y `updated_at`): `services.with_applied` marca cada corrección y
`services.corrections_pending` avisa si las actuales no coinciden. La IA no ve el análisis anterior, así
que una corrección debe ser un hecho sobre el vídeo, no una referencia al resumen. La IA nunca las escribe ni las modifica.

**Marcas de tiempo.** El campo `t` de tareas, decisiones, pendientes, señales y eventos usa `TS_T`, un
`pattern` `0h:mm:ss` que la gramática de llama.cpp impone (comprobado en vivo). La hora empieza por 0: con una
hora libre, el modelo escribía «20:42:00» por el minuto 20:42. Sin él, el modelo a veces ponía
en `t` el texto de la tarea o una fecha copiada del contexto. Los pendientes son objetos `{pendiente, t}`;
los análisis antiguos los tienen como texto (`followups.pending_parts` acepta los dos). El plazo se pide «solo si se dice y
tal como se dice»: el modelo convertía «el lunes» en una fecha e inventaba plazos («antes de la sesión X»).
`ANALYSIS_RULES` recuerda que el contexto (perfil, personas, seguimiento, notas) no es contenido de la
grabación: el resumen contaba edades o estudios de las fichas que no se decían en el vídeo. El informe
final pone cada asunto en una sola lista (tarea, decisión o pendiente).

**Seguimientos** (`prompts.followup_block`, `FOLLOW_CHECK_*`, `FOLLOW_*`, `followups.py`).
- **Al resumir**, cada fragmento recibe el estado de cada seguimiento del vídeo según los vídeos
  **anteriores** a su fecha (`followups.context_block`, sin ids), solo para entender referencias.
- **Fase `follow`**, por seguimiento y vídeo (`followups_store.apply_video`):
  1. `mentions`: por cada bloque de la transcripción, `FOLLOW_CHECK_*` **con modo razonamiento** pregunta de
     qué puntos del estado (con ids `[T3]`, `[D2]`, `[P1]`) se habla, con evento, `t` y la cita literal.
     `followups.check_signals` comprueba cada cita (`quoted`: `partial_ratio` ≥ `QUOTE_SIMILAR` en
     ±`QUOTE_WINDOW` s; troceada con «…», cada trozo; mínimo `QUOTE_MIN_CHARS`) y marca `verified`.
     Medido con dos vídeos reales: dentro del resumen o sin razonar, el modelo no encontraba los cierres
     dichos de pasada («lo que ayer fallaba ya ha funcionado») e inventaba momentos («00:57:33» en un vídeo
     de 25 min) y citas; con razonamiento, todas las citas existían y encontró el cierre (unos 2 min por
     bloque de 25 min). Recibe también de qué trata el vídeo (título y resumen breve): sin eso no cerraba
     «Realizar la sesión de diagnóstico» en la propia sesión. Si un bloque se corta por `max_tokens`
     (`LLMTruncated`), se repite en dos mitades.
  2. `FOLLOW_*` sin razonamiento: con el estado, los **puntos del vídeo** (`followups.analysis_points`:
     tareas, decisiones y pendientes del análisis, con clave `[N…]`), las menciones, el resumen, **lo que
     aportó cada vídeo anterior** (`FollowupVideo.contribution`) y **los puntos borrados por el usuario**
     (`followups.hidden_block`, con su id), devuelve `clasificacion` (por cada `[N…]`: `mismo`, `nuevo` o
     `dudoso` frente a un punto del estado, uno borrado u otro `[N…]`, con motivo), `resumen` (de toda la
     serie; las marcas con fecha `[AAAA-MM-DD hh:mm:ss]`, que la web y `followups.link_moments` enlazan
     con el vídeo) y `aporte`. Antes, con `mismos` y la comparación difusa, cada vídeo repetía 3–6 puntos
     con otra redacción, los borrados volvían al rehacer y el resumen describía solo el último vídeo.
  3. `followups.apply_update`: los hitos salen de las menciones (un cambio de estado con cita comprobada se
     aplica; sin ella queda como «avanza» con `posible: <evento>`, que la web muestra como «¿hecha?» con un
     botón Confirmar o «No pasó», que marca el evento `descartado`); a un punto manual solo se le anotan
     avances. Los puntos nuevos son los del análisis menos los «mismo» (`followups.classify` descarta los
     ids que no existen) y los casi iguales en texto a uno existente o borrado (`DUPLICATE`, red de
     seguridad): no los inventa la IA, que variaba en cada ejecución. Los «dudoso» se crean con
     `review = {tipo: duplicado, de, texto, motivo}` y los decide el usuario (`POST …/resolve`).

El contexto se limita a `FOLLOW_CONTEXT_CHARS`, recortando primero lo cerrado. Tests en `test_followups.py`.

**Correcciones de transcripción** (`kind = correccion`, `learn.collect_corrections`). Una propuesta por
término con las formas en que se oye mal (`data = {term, variants, fuente, motivo}`; clave
`término|formas`, así una forma nueva es otra propuesta). Fuentes: la lista `correcciones` de
`LEARN_SCHEMA` (la IA, que ve tus notas y la pantalla), `learn.notes_corrections` (una llamada que saca
de las correcciones del usuario los pares «oído → correcto»: la extracción por fragmentos no los recogía)
y `knowledge.corrections_from_correct_stage` (lo que `correct` ya validó). Se probó también buscar por
sonido los términos de la pantalla en la transcripción (`find_candidates` a 75): con un vídeo real de 37
min salían 15 parejas sin sentido («Meta» por «está»), y la pasada de juicio las daba por buenas. Cada forma debe oírse tal cual (`knowledge.heard_at`, sobre `original_text`).
`knowledge.correction_source` dice en qué se apoya: `usuario` > `pantalla` > `glosario` > `ia` (solo la
IA: `juicio` dudosa). Aceptadas, `effective_glossary` las añade como variantes **fiables** de su término
(o lo crea). Antes, el aprendizaje solo proponía términos escritos tal cual en la transcripción, así que
nunca proponía uno mal transcrito, que es justo lo que más falta hace.

**Pasada de juicio** (`learn.judge_proposals`, `JUDGE_*`). Después de recoger y comprobar las
propuestas, la IA las revisa todas juntas (cada término con cuántas veces aparece y si se oye: con solo su
frase de ejemplo, «Un segundito», descartaba términos clave), en tandas de `JUDGE_BATCH` ordenadas por dueño y tipo:
`util`, `dudosa` o `descartar` con motivo, `igual_que` (duplicado de otra propuesta) y `ya_guardado` (el
`[#id]` de lo ya aceptado que repite: recibe `known_block` solo con los términos y el contexto del perfil, y
`known_items` guarda en `judgment.raw.json` qué número es cada cosa). Sin lo aceptado, el perfil acumulaba la
misma frase de vídeos distintos con otras palabras. Con las fichas de las personas también a la vista, descartaba
datos personales nuevos (salario, cuentas) que antes marcaba dudosos: por eso no se le pasan. Se probó también pasar al perfil los
datos de persona que fueran del negocio, pero el texto perdía su sujeto («Documenta la configuración…») y
el modelo lo marcaba con datos que sí eran de la persona: se quitó. `apply_proposal_judgment`: lo descartado y lo repetido se guarda con `status =
descartado_ia` (la web lo lista plegado y lo deja recuperar, `POST knowledge/{id}/recover`); lo dudoso
lleva `data.juicio`; las alias y las secciones no se juzgan. En la misma llamada valora si las secciones
del perfil encajan con el vídeo y, si no, propone hasta 2 generales (`section_proposals`, `replaces` solo
sobre una aprendida; solo si el perfil ya tiene secciones). Las correcciones de transcripción no admiten
nombres de personas: la IA proponía «Juan, puedes» → «Juan Pérez». Va **con modo razonamiento**
(`max_tokens` 16000; una tanda que se corta se parte en dos): sin él, el mismo código promocional salía
útil o descartado según la ejecución (unos 3 min por tanda de `JUDGE_BATCH`). Cada dato lleva la línea que
más lo respalda (`knowledge.claim_score`: palabras comunes y, sobre todo, sus cifras) y la siguiente; con
la línea del momento aproximado, el juicio veía la pregunta («¿salario neto?») y descartaba datos ciertos.
Lo que sale de las correcciones del usuario (`fuente = usuario`) no se juzga. Es de mejor esfuerzo: si
falla, las propuestas quedan como estaban. Medido en la
prueba de los 3 vídeos de tutoría: 16 propuestas «Sabe que…» (lo explicado en la clase como dato de quien lo
explicaba), términos como un código promocional o el nombre de un programa del escritorio y un duplicado
de un término ya aceptado; el prompt de extracción ya pedía no incluirlos.

**Respuestas no válidas.** `llm.chat_json` guarda en `data/llm_failures/` cada respuesta que no es JSON
válido, con su `finish_reason` y los mensajes sin imágenes. Si `finish_reason == "length"`, no se
reintenta, porque la misma petición se volvería a cortar. Antes de subir un `max_tokens`, mira ahí el
caso real: puede ser una repetición en bucle y no falta de espacio.
