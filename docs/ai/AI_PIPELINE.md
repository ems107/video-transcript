# Pipeline de análisis

Orquestación: `backend/app/worker.py`. Fases: `backend/app/pipeline/*.py`. Un único hilo
procesa los trabajos (`Job`) en orden de id.

## Fases y ficheros de trabajo

Cada trabajo tiene la carpeta `data/work/job_<id>/`. Una fase lee los JSON de las fases anteriores y
escribe los suyos con `ctx.save()`, que es atómico (`.tmp` y después `replace`). Al terminar, el
worker crea `<fase>.done`.

| Fase (`STAGES`) | Módulo | Lee | Escribe | Modelo en GPU |
|---|---|---|---|---|
| `ingest` | `ingest.py` | vídeo | `probe.json`, `audio.wav`, `owner.wav`* | — |
| `frames` | `frames.py` | `probe.json` | `frames/`, `frames.json`, `thumbnail.jpg` | — (ffmpeg `-hwaccel auto`) |
| `vision` | `vision.py` | `frames.json`, `frames/` | `vision.json`, `screen_terms.json` (`vision.partial.json`) | llama-server |
| `asr` | `asr.py:run_asr` | `audio.wav`, `screen_terms.json` | `whisper_prompt.json`, `asr.json` | Whisper |
| `align` | `asr.py:run_align` | `asr.json`, `audio.wav` | `aligned.json` | wav2vec2 |
| `diarize` | `diarize.py` | `audio.wav`, `owner.wav`*, `aligned.json` | `diarization.json`, `utterances.json` | pyannote |
| `voices` | `voices.py` | `audio.wav`, `aligned.json`, `diarization.json` | `words.json`, `utterances.json` (con `voice`), `voices.json` (`splits`: cada grupo con su `centroid`, que `identify` compara con las huellas para `suggested` y no guarda en el hablante); reescribe `embeddings` y `speaking_time` de `diarization.json` | modelo de huellas de pyannote |
| `names` | `names.py` | `vision.json` (o `vision.raw.json`), `utterances.json` | `names.json`, `vision.json` unificado, `vision.raw.json` (lecturas originales), `screen_terms.json` | — |
| `identify` | `identify.py` | `diarization.json`, `utterances.json`, `vision.json` | `identities.json` y filas `Speaker` | — |
| `correct` | `correct.py` | `utterances.json` | `corrected.json` | llama-server |
| `analyze` | `analyze.py` | `corrected.json`, `vision.json`, `names.json`, `probe.json` | `analysis.json` (`analysis.partial.json`), `context_identities.json` y propuestas «contexto» en `Speaker` | llama-server |
| `voiceprints` | `voiceprints.py` vía `worker._voiceprints` (solo al aplicar la revisión) | `audio.wav` (si falta, repite `ingest`), `utterances.json` con los arreglos, `Speaker` confirmados | filas `VoiceEmbedding` y `VoiceSample` del vídeo (sustituye las anteriores), `data/voces/<persona>/<vídeo>.flac`, `Video.voices_applied` | modelo de huellas de pyannote |
| `follow` | `worker._follow` → `followups_store.update_for_video` | `analysis.json` y `corrected.json` (o `Video.analysis` y `Segment` si ya está publicado) | filas `FollowupItem`/`FollowupVideo`/`FollowupVersion` y `Seguimiento - Nombre/seguimiento.md` | llama-server (solo si el vídeo está en algún seguimiento) |
| `learn` | `learn.py` vía `worker._learn` | `corrected.json`, `vision.json`, `screen_terms.json`, `identities.json` | `proposals.json` (`learn.partial.json`; `learn_error.json` si falla), `screen_judgment.json` (valoración de los términos vistos solo en pantalla; `screen_judgment.raw.json` para reanudar) y filas `KnowledgeItem` | llama-server |
| `publish` | `worker._publish` | todo lo anterior | carpeta final (con `datos/`), `Segment`, `Keyframe`, FTS | — |

\* `owner.wav` solo existe si el usuario indica en qué pista está su micrófono.

Formas clave:
- `utterances.json` / `corrected.json`: `[{start, end, speaker, text, original_text?, corrections?}]`.
  `speaker` es la etiqueta de pyannote (`SPEAKER_00`), no un nombre.
- `diarization.json`: `{turns, speaking_time, embeddings: {label: [float]}, owner}`.
- `names.json`: `[{canonical, person_id, variants: {lectura: n}, readings, frames, heard}]`, un grupo
  por persona vista en pantalla. `vision.json` ya lleva solo las formas `canonical`; las lecturas
  originales quedan en `vision.raw.json`, y `names` se puede repetir sin perderlas. Si se repite
  `vision`, se borra `vision.raw.json`.
- `context_identities.json`: `{identidades: {label: {nombre, motivo, t, votos}}, apodos: {nombre: [apodo]},
  evaluados: [label]}`. Una propuesta por contexto anterior solo se retira si su hablante está en
  `evaluados`: al regenerar, los hablantes con propuesta ya no son «Hablante N» y no se reevalúan.
- `analysis.json`: sigue `FINAL_SCHEMA` de `prompts.py`. Las claves están en español, y la web y
  `export.py` dependen de ellas.

## Revisión del vídeo (`review.py`)

`Video.review`: `pendiente` → `aplicando` → `propuestas` → `revisado` (los vídeos anteriores a la 1.6.0
quedan `revisado` por la columna de `db.NEW_COLUMNS`).
- **Fases tras la revisión** (`worker.AFTER_REVIEW`: `voiceprints`, `follow`, `learn`): solo se ejecutan en
  un trabajo con `options.apply` o si están en `only`. El trabajo inicial y las regeneraciones manuales se
  las saltan **sin** crear su marca y dejan el vídeo `pendiente`.
- **«Aplicar y continuar»** (`POST videos/{id}/apply`): `_requeue` con `review.apply_stages` (`correct` y
  `analyze` si hay correcciones o arreglos de hablantes sin aplicar, y siempre `voiceprints`, `follow`,
  `learn`, `publish`), `apply: true` y `follow_rebuild` con sus seguimientos abiertos. Al terminar, el
  vídeo pasa a `propuestas` y `review.check_done` lo deja `revisado` si no queda nada por decidir
  (propuestas `propuesto` de ese vídeo ni puntos con `followups.needs_review`). Lo comprueban también
  `proposals/decide` y los endpoints de puntos del seguimiento.
- **Espera:** antes de la primera fase de `review.GATED_STAGES` (names, identify, correct, analyze) que haya
  que ejecutar, `worker._wait` busca con `review.blocker` un vídeo relacionado (mismo perfil o seguimiento)
  de `id` menor sin revisar. Si lo hay, el trabajo pasa a `waiting` con `options.waiting_for` y el worker
  sigue con otro. `review.release_waiting` (en cada vuelta del bucle del worker y al quitar un vídeo) los
  vuelve a `queued`. Los trabajos con `only` no esperan.
- **Cambios del usuario** (correcciones, arreglos de hablantes, confirmar o cambiar un hablante) llaman a
  `review.mark_changed`: un vídeo `revisado` o en `propuestas` vuelve a `pendiente`. `review.changes` lista
  lo que falta por aplicar (`voices_applied` frente a los hablantes confirmados para las voces).
- **Prioridad:** los trabajos cortos (`worker.is_short`: `apply` u `only`) se eligen antes que los demás, y
  un análisis largo cede el turno entre fase y fase si hay uno en cola (`_yield_to_short`: vuelve a
  `queued` y se reanuda por sus marcas). Sin esto, «Aplicar y continuar» esperaba a que terminara el
  análisis pesado del vídeo siguiente (unos 45 min).
- **Audio:** `_cleanup(keep_audio=True)` mientras el vídeo no está revisado (lo necesita `voiceprints`);
  `review.drop_audio` lo borra al quedar revisado.
- **Seguimientos:** `rebuild_from` y `first_from` se saltan los vídeos `pendiente`; se aplican al aplicar
  su revisión.

## Reglas del worker

- **Reanudación:** si existe `<fase>.done`, la fase se salta. Al arrancar, los trabajos `running`
  vuelven a `queued`. Las fases largas (`vision`, `analyze`, `learn`) guardan un `*.partial.json` para
  continuar donde se quedaron.
- **Repetir fases:** `options["redo"] = [...]` borra esas marcas, y los parciales de `worker.PARTIALS`,
  antes de ejecutar. Lo usa `main._requeue()`:
  - `regenerate {level}`: las fases de `regenerate.stages(level)`. Los niveles son `analysis` (correct,
    analyze, learn, publish), `speakers` (+ identify), `screen` (+ frames, vision, names) y `full`
    (todo). `regenerate.availability` dice qué nivel se puede usar: `screen` y `full` necesitan el
    archivo de vídeo, y los demás, los JSON de trabajo. `full` llama antes a
    `regenerate.unconfirm_speakers`: al volver a separar las voces, las etiquetas ya no significan lo
    mismo. Las huellas de voz se conservan, así que `identify` vuelve a proponer a cada persona.
  - `videos/{id}/learn`, `profiles/from-video` y `profiles/{id}/learn-all`: solo `learn`, como trabajo de una
    sola fase (`only: ["learn"]`), que no cambia el estado de la revisión del vídeo.
  - `videos/{id}/apply`: ver «Revisión del vídeo».
  - Opciones de un solo encolado (`main.ONE_SHOT_OPTIONS`, `_requeue` las quita del encolado anterior,
    porque cada vídeo reutiliza su último `Job`): `only` (el worker se salta todas las fases que no estén en
    la lista; lo usan los trabajos que solo rehacen un seguimiento), `follow_rebuild` (ids de seguimientos
    cuyo estado se rehace desde este vídeo), `apply` (ejecutar las fases de después de la revisión) y
    `waiting_for`. Una opción nueva que solo valga para un encolado va en esa lista: si no, se arrastra
    (pasó con `apply` hasta la 1.7.1: regenerar un vídeo revisado aplicaba otra vez su revisión).
- **`persist_speakers` fusiona:** al repetir `identify`, un hablante confirmado conserva su persona y su
  `id`. Solo cambian las propuestas de los no confirmados, y se borran las etiquetas que ya no existen.
- **Fotogramas publicados:** si en este trabajo se han vuelto a elegir fotogramas, `_publish` vacía
  `fotogramas/` antes de copiar los nuevos.
- **Tiempos:** el worker guarda un `StageRun` por cada fase ejecutada: segundos y unidades (fotogramas
  en `vision`, minutos de audio en el resto). `estimates.estimate` divide el total de segundos entre el
  total de unidades de las últimas 10 ejecuciones (un vídeo corto, donde pesa cargar el modelo, no
  distorsiona la estimación de uno largo) y, sin historial, usa `DEFAULT_RATES`, medidos con
  grabaciones reales. Al reencolar, el
  trabajo reinicia `started_at`. Si cambias mucho lo que tarda una fase, ajusta `DEFAULT_RATES`.
- **Arreglos manuales de hablantes** (`SpeakerOverride`, `speaker_fix.py`): «de `start` a `end` habla
  esta persona». Antes de `identify` y de `correct`, `worker._apply_overrides` reconstruye
  `utterances.json` con `voices.rebuild`: palabras de `words.json` (o, en trabajos anteriores a la fase
  `voices`, de `aligned.json` + turnos) → `apply_overrides` → intervenciones. Mandan sobre lo
  automático. Una persona sin hablante en el vídeo recibe la etiqueta `MANUAL_<id>`, ya confirmada,
  que `unconfirm_speakers` no toca. Al crearlos o borrarlos, `speaker_fix.refresh_segments` actualiza
  las filas `Segment` al momento, partiendo líneas por palabras si hace falta. `analysis.json` guarda
  `hablantes_aplicados` para avisar de los que faltan en el resumen.
- **Correcciones del usuario:** el worker carga las del vídeo en `ctx.corrections` al empezar el
  trabajo. `analyze` y `learn` las incluyen en su contexto (ver `AI_PROMPTS.md`).
- **Seguimientos** (`followups.py` lógica pura, `followups_store.py` BD). El worker carga en
  `ctx.followups` el estado de cada seguimiento del vídeo **anterior a su fecha** (`context_for_video`) y
  `analyze` lo añade al contexto (`prompts.followup_block`). La fase `follow` decide por seguimiento:
  - rehacer desde la fecha del vídeo (`rebuild_from`: versión, `revert_videos` de ese vídeo, los
    posteriores y los quitados sin rehacer, y `apply_video` de cada uno en orden) si está en
    `follow_rebuild` o si el vídeo es nuevo y el último por fecha;
  - si no, marcarlo desactualizado (`stale_from`, `stale_reason`): desde la cola no se puede preguntar.

  Es de mejor esfuerzo como `learn`: si falla, el seguimiento queda desactualizado con el motivo. Sin
  seguimientos no hace nada y no guarda `StageRun` (no hay nada que medir). Las unidades de su
  `StageRun` son los minutos de **todos** los vídeos aplicados (al rehacer pueden ser varios). Rehacer
  desde la web (`POST followups/{id}/rebuild`, añadir o quitar un vídeo) encola en el primer vídeo
  afectado un trabajo con `only: ["follow"]` y `follow_rebuild: [id]`.
- **`learn` es de mejor esfuerzo.** Si falla, se guarda `learn_error.json` y el vídeo se publica igual
  (ver `test_learn_failure_does_not_break_the_job`). Si el vídeo no tiene perfil, solo propone datos
  de personas. Los detalles están en `AI_PROMPTS.md` (aprendizaje).
- **GPU:** antes de una fase de `GPU_TORCH_STAGES` (asr, align, diarize, voices, voiceprints) se llama a `llm.stop()`.
  Después de las demás se llama a `free_gpu()`. Cada fase con torch descarga su modelo al acabar (`del`
  + `free_gpu()`). Las fases que usan el LLM llaman a `llm.start()`, que no hace nada si ya está
  arrancado.
- **Progreso:** `ctx.report(frac_fase, mensaje)` en el rango 0..1 de la fase. El worker lo convierte en
  progreso global con los pesos de `STAGES` y limita la frecuencia de escritura en la BD. La web lo
  recibe por SSE.
- **Cancelación:** llama a `ctx.check_cancel()` dentro de los bucles largos. Lanza `Cancelled`.
- **`ctx.speaker_names`** (etiqueta → nombre visible) se rellena después de `identify`, y también al
  reanudar. Úsalo en las fases posteriores en lugar de leer `Speaker` tú mismo.
- **Publicación:** el vídeo se mueve o se copia una sola vez (`options.file_mode` o
  `Settings.file_mode`). Si se regenera, se reutiliza la carpeta existente. `_cleanup` borra los wav y
  los fotogramas, pero conserva los JSON para poder regenerar sin repetir ASR ni diarización.
- **Carpeta del seguimiento:** `followups_store.export` escribe `Seguimiento - Nombre/seguimiento.md`
  en `analyzed_dir` (renombra la carpeta si cambia el nombre) al aplicar, editar o restaurar, y
  `_publish` la reescribe al final para enlazar la carpeta del vídeo recién creada.
- **Copia de recuperación:** `_publish` escribe `datos/` en la carpeta publicada
  (`removal.save_recovery`): `video.json` (metadatos y hablantes con su persona, confirmación, huella y
  pistas) y los JSON de `removal.WORK_FILES`. «Quitar» sin borrar ficheros la vuelve a escribir. Si
  añades un JSON intermedio necesario para reconstruir el análisis, añádelo a `WORK_FILES`.
- **Quitar un vídeo** (`removal.py`): siempre lo saca de la BD y borra sus propuestas pendientes. Las
  opciones (`Options`) deciden qué se borra del disco; `removal.plan` es la única que decide rutas y
  solo toca `APP_FILES`/`APP_DIRS`, las carpetas de trabajo y el vídeo marcado.

## Añadir o cambiar una fase

1. Crea `pipeline/<fase>.py` con `run(ctx, ...)`. Usa `ctx.load`/`ctx.save` y llama a `ctx.report` y
   a `ctx.check_cancel`.
2. Añade `(clave, etiqueta en español, peso)` a `STAGES` en su posición. Reajusta los pesos para que
   sumen aproximadamente 1. Añade el caso en `Worker._run_stage`. Si carga un modelo torch, añade la
   clave a `GPU_TORCH_STAGES`.
3. Si cambia el formato de un JSON intermedio, ten en cuenta que en `data/work/` puede haber trabajos
   a medias con el formato anterior. Haz que `load` tolere su ausencia (`default`), o borra el `.done`
   afectado.
4. Pon la lógica pura (sin modelos) en funciones aparte y pruébala en `tests/test_logic.py`.

## Prueba de punta a punta

**No uses `data/` del usuario ni su instancia en :8770.** Arranca una instancia aislada con otra
carpeta de datos y otro puerto para el LLM:

```bash
# settings.json de la carpeta de prueba: {"analyzed_dir": "<scratchpad>\\analizados", "file_mode": "copy", "llm_port": 8092}
VT_DATA_DIR='<scratchpad>\e2e\data' uv run uvicorn app.main:app --port 8771   # en segundo plano
export MSYS_NO_PATHCONV=1   # Git Bash no debe convertir los argumentos «/api/...» en rutas de Windows
```

Comprueba antes con `nvidia-smi` que la GPU está libre: si la instancia del usuario está procesando
algo, no caben dos modelos a la vez. Al terminar, para la instancia de prueba.

Los vídeos sintéticos están en `samples/videos-prueba/`, que no se versiona:
- `reunion_prueba.mp4`: dos voces y los nombres en pantalla. Sirve para probar la identificación por
  pantalla.
- `incidencia_pedidos.mp4`: las mismas voces, sin nombres. Tras confirmar los hablantes del primero,
  sirve para probar la identificación por voz (usa `skip_vision`).

Las dos voces son la misma voz TTS con el tono cambiado, así que en vídeos reales la similitud de voz
será menor.

```bash
# API en marcha en :8770. Cuerpo en fichero para evitar problemas de UTF-8 en Windows.
echo '{"path":"C:\\...\\reunion_prueba.mp4","profile_id":null,"options":{"file_mode":"copy"}}' > job.json
curl -s -X POST localhost:8770/api/jobs -H 'Content-Type: application/json' --data-binary @job.json
curl -s localhost:8770/api/jobs        # estado / progreso / error (traceback en "error")
```

Con un vídeo de unos 2 minutos tarda 1–2 min; `learn` añade unos 10 s (sin recargar el LLM). El primer uso de Whisper tras instalar puede tardar ~90 s
más por la compilación JIT de CUDA, y solo ocurre una vez. Los errores del LLM se registran en
`data/llama-server.log`.
