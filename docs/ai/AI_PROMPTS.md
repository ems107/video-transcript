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

## Visión (`VISION_*`, `pipeline/vision.py`)

Se hace una llamada por fotograma, con un máximo de `Settings.max_frames` (240). Los fotogramas se
eligen por cambio de escena (hash perceptual), con un mínimo de 4 s y un máximo de 60 s entre ellos.
Para cada uno se obtienen `tipo_escena`, `aplicacion`, `descripcion`, `texto_relevante`,
`participantes`, `hablante_activo` y `terminos`. Los `terminos` y `participantes` más frecuentes
forman `screen_terms.json`, que alimenta el prompt de Whisper. `hablante_activo` alimenta la
identificación. Si un fotograma falla, se guarda un resultado vacío y el proceso sigue.

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

## Identificación de hablantes (`pipeline/identify.py`, `pipeline/voice.py`)

Fuentes, por orden de prioridad:
1. **Micrófono:** si existe `owner.wav`, el hablante cuya actividad coincide con esa pista en al menos
   un 60 % se marca como el dueño (`Settings.owner_name`, confianza 0.95).
2. **Voz:** coseno contra el centroide de las huellas confirmadas de cada persona, con emparejamiento
   voraz uno a uno. Solo se propone si la similitud es ≥ `voice_match_threshold` (0.55). A partir de
   `voice_auto_threshold` (0.75) la confianza es alta. Si la pantalla confirma la misma persona, la
   confianza sube a ≥ 0.9.
3. **Pantalla:** el `hablante_activo` dominante durante los turnos de un hablante (al menos 2
   apariciones y un 60 % del total). Se busca en las personas por nombre o alias
   (`token_set_ratio` ≥ 85). Si no existe, queda como `suggested_name`.

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

Al renombrar un hablante después de publicar, `services.replace_speaker_name` sustituye el nombre en
todo el análisis sin llamar al LLM. «Regenerar análisis» repite `correct`, `analyze` y `publish`.
