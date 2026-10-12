# Backend: datos, API y ajustes

FastAPI en `backend/app/main.py` y SQLite en `data/app.db` (modo WAL, `foreign_keys=ON`). Las rutas
salen de `config.py`: `ROOT_DIR`, `DATA_DIR`, `MODELS_DIR`, `WORK_DIR` y `FRONTEND_DIST`.

## Modelo de datos (`models.py`)

| Tabla | Para qué | Notas |
|---|---|---|
| `Profile` | tipo de vídeo | `context`, `extra_prompt`, `summary_sections[]` y `glossary[{term, variants[], definition}]` en JSON |
| `Person` | persona global (puede estar en varios perfiles) | `aliases[]` incluye los nombres que aparecen en las videollamadas |
| `ProfilePersonLink` | relación de muchos a muchos entre perfiles y personas | |
| `VoiceEmbedding` | huella de una persona en un vídeo (fase `voiceprints`) | `vector` en JSON; `doubtful` (no se parece a sus otras huellas: `services.voice_db` no la usa hasta que el usuario la acepte), `similarity`, `seconds` |
| `VoiceSample` | muestra de voz de una persona en un vídeo | `path` en `data/voces/`, `seconds`, `score`; la ficha muestra las 3 mejores. «Olvidar voz», «Quitar» con olvidar y la fusión de personas las tratan como las huellas |
| `Video` | un vídeo | `status`: pending, processing, done o error. `analysis` guarda el JSON completo; `folder` y `video_path` se rellenan al publicar. `review` (pendiente, aplicando, propuestas o revisado) y `voices_applied` (`{etiqueta: persona}` con que se aplicó la revisión; nulo en vídeos anteriores): ver `review.py` y `AI_PIPELINE.md` |
| `Job` | un trabajo de la cola | `status`: queued, running, waiting (espera la revisión de `options.waiting_for`), done, error o cancelled. `options` (ver abajo). `error` incluye el traceback |
| `Speaker` | hablante de un vídeo (`SPEAKER_00`) | `person_id` = confirmado; `suggested_person_id` / `suggested_name` = propuesta; `source`: micrófono, voz, pantalla o contexto. En `visual_hints`, las claves con «_» son internas (`_motivo`, `_apodos`, `_split`: dos voces, con `suggested` por grupo) |
| `Segment` | intervención de la transcripción | `speaker` es la etiqueta, no el nombre. `original_text` y `corrections` vienen del glosario. `voice`: «» , «reasignada» o «dudosa» (columna añadida con `db.NEW_COLUMNS`) |
| `SpeakerOverride` | arreglo manual: de `start` a `end` habla `person_id` | ver `speaker_fix.py` |
| `Keyframe` | fotograma analizado | la ruta apunta a `<carpeta>/fotogramas/` |
| `KnowledgeItem` | conocimiento aprendido o propuesto | ver «Conocimiento aprendido» |
| `KnowledgeVersion` | foto de un perfil o persona tras cada cambio | `snapshot` = `{manual, items, person_ids?}` |
| `PersonPairDismissal` | parejas marcadas como «no son la misma persona» | |
| `StageRun` | lo que tardó una fase ejecutada | `seconds` y `units`; ver `estimates.py` |
| `VideoCorrection` | corrección escrita por el usuario sobre un vídeo | `text`, `updated_at`; la IA nunca la modifica |
| `Followup` | seguimiento (continuidad de un tema entre vídeos) | `status` abierto o archivado; `summary` + `summary_manual` (si es del usuario, la IA deja el suyo en `summary_ai`); `stale_from`/`stale_reason` = desactualizado; `folder` |
| `FollowupVideo` | vídeo de un seguimiento | `applied` (el estado lo incluye), `contribution` y `summary` (resumen tras aplicarlo, para volver atrás al rehacer) |
| `FollowupItem` | tarea, decisión o duda | `status` sale del último evento de `events[{video_id, date, t, evento, nota, source, at}]`; `manual` = tocado por el usuario (la IA ya no cambia su texto ni su estado); `hidden` = borrado por el usuario (se conserva para que la IA no lo vuelva a crear); `review` = duda de la IA que decide el usuario (`{tipo: duplicado, de, motivo}`); un evento con `posible` sin confirmar (o con `descartado`) también se decide en la revisión (`followups.needs_review`) |
| `FollowupVersion` | copia del estado antes de cada cambio | `snapshot` = `{summary, summary_manual, summary_ai, items, videos}` |

- **No hay migraciones.** Añadir **tablas** nuevas es seguro: `init_db()` ejecuta `create_all`, que crea
  las que falten pero **no añade columnas a tablas que ya existen**. Una columna nueva en una tabla
  existente se declara en `db.NEW_COLUMNS` (nombre, tipo SQL y valor por defecto), e `init_db` la añade con
  `ALTER TABLE` si falta (idempotente). Si no lo haces, la BD del usuario dará error al arrancar. El valor
  por defecto decide cómo quedan las filas antiguas (p. ej., `Video.review` = `revisado`).
- Para las fechas usa `NaiveDatetime` (por SQLModel 0.0.47) y `now()` de `models.py`.
- Los campos de lista o diccionario usan `sa_column=Column(JSON)`. Si modificas una lista en su sitio,
  SQLAlchemy no lo detecta: reasigna el valor completo.
- El nombre que se muestra de cada hablante se resuelve **siempre** con `services.speaker_names()`.
  El orden es: persona confirmada, persona propuesta, nombre visto en pantalla y, por último,
  «Hablante N».

## Conocimiento aprendido

Módulos:
- `knowledge.py`: lógica pura y testeable;
- `knowledge_store.py`: elementos, versiones y guardado de propuestas;
- `proposals.py`: listar las propuestas resueltas, decidir, editar, retirar, olvidar un vídeo y
  reasignar un hablante;
- `people.py`: ficha, duplicados y fusión.

**`KnowledgeItem`:**
- **Dueño.** `profile_id` para los tipos `termino`, `contexto`, `seccion` y `correccion` (corrección de
  transcripción: `{term, variants, fuente, motivo}`). `person_id` para `dato` y
  `alias`. Una propuesta de un hablante tiene `person_id = None` y `speaker_label`, y se resuelve al
  mostrarla (`proposals.Resolver`). `nueva_persona` lleva el `profile_id` del vídeo para enlazar a la
  persona al aceptarla.
- **Estados.** `propuesto` → `aceptado` | `rechazado`. Un aceptado puede pasar a `retirado`. Los
  aceptados nunca se borran: el historial los necesita. `descartado_ia` es lo que la pasada de juicio
  descartó: no cuenta como pendiente ni bloquea la revisión del vídeo, se lista aparte y el usuario lo
  puede recuperar (vuelve a `propuesto`).
- **Un solo valor.** `cargo`, `organizacion` y `equipo` tienen un único valor vigente: al aceptar uno,
  se retira el anterior (`single_value_conflicts`). `replaces_id` retira el dato reemplazado.

**Versiones:**
- **Cuándo.** Cualquier cambio de lo manual o de lo aceptado crea una versión: llama a
  `KS.ensure_baseline()` **antes** del cambio y a `KS.record_version()` después, o usa
  `proposals._Owners`. `record_version` no crea nada si la foto no cambió.
- **Restaurar.** `restore_version` crea una versión nueva y nunca borra historial.
- **Fusión.** Al fusionar personas, las versiones de la persona absorbida se borran.

**Personas:**
- Al confirmar un hablante en un vídeo con perfil, la persona se enlaza al perfil
  (`proposals.link_to_profile`).
- Al reasignar un hablante, lo aceptado de ese `(video, label)` pasa a la nueva persona
  (`reassign_speaker_items`).

## Búsqueda (`db.py`, `services.index_video`, `main.search`)

La tabla virtual FTS5 `search_fts(text, kind, video_id, ref_id, t, speaker)` usa
`unicode61 remove_diacritics 2`, así que no distingue tildes. Hay cuatro tipos (`kind`): `title`,
`summary`, `segment` y `frame`. `index_video` borra y vuelve a insertar todo lo de un vídeo; llámalo
después de cualquier cambio en el título, el análisis, los segmentos o los nombres. La consulta trata
cada palabra como prefijo (`"palabra"*`), y el texto entre comillas se busca como frase.

## Después de modificar un vídeo publicado

Ejecuta siempre las dos llamadas: `services.export_video(session, video)`, que vuelve a escribir
`transcripcion.*`, `resumen.md` y `analisis.json` en la carpeta, y `services.index_video(session,
video)`. Así lo hacen `update_video`, `update_speaker` y `_publish`.

## API (todas bajo `/api`)

| Grupo | Endpoints |
|---|---|
| Sistema | `GET status` (versión, comprobación de componentes, `pending_proposals` y `to_review`), `GET/PUT settings` (PUT aplica `log_level` al momento), `POST logs/open-folder`, `POST client-log {message, stack, url}`, `GET probe?path=`, `GET help/values` (valores `{{v:…}}` de la ayuda), `GET help/changelog` |
| Trabajos | `POST jobs {path, profile_id, options}`, `GET jobs`, `POST jobs/{id}/cancel`, `POST jobs/{id}/retry`, `GET events` (SSE, evento `jobs` cada segundo si hay cambios) |
| Vídeos | `GET videos?profile_id&person_id` (tarjetas: `people` sin repetir, `review` y `to_decide`, lo que queda por decidir si está en `propuestas`), `GET/PUT/DELETE videos/{id}`, `GET videos/{id}/file` (con rangos), `GET videos/{id}/thumbnail`, `GET keyframes/{id}/image`, `POST videos/{id}/open-folder`, `GET videos/{id}/regenerate` (niveles, disponibilidad y estimación), `POST videos/{id}/regenerate {level}` (sin cuerpo = `analysis`), `GET/POST videos/{id}/corrections`, `PUT/DELETE corrections/{id}`, `GET/POST videos/{id}/speaker-overrides {ranges, person_id | new_person_name}`, `DELETE speaker-overrides/{id}`, `GET videos/{id}/words?start&end`, `POST videos/{id}/confirm-speakers`, `GET videos/{id}/removal`, `POST videos/{id}/remove {delete_files, delete_video, delete_original, forget}` |
| Hablantes | `PUT speakers/{id} {person_id \| new_person_name, confirm}` |
| Perfiles | CRUD de `profiles` (`person_ids[]` en el cuerpo; la respuesta incluye `learned_count` y `pending_count`), `GET profiles/{id}/knowledge`, `GET profiles/{id}/versions`, `POST profiles/{id}/versions/{vid}/restore`, `POST profiles/from-video {video_id, name}`, `POST profiles/{id}/learn-all` |
| Personas | CRUD de `people` (`GET people/{id}` devuelve la ficha completa), `DELETE people/{id}/voices`, `GET people/{id}/knowledge`, `GET/POST people/{id}/versions[/{vid}/restore]`, `GET people/duplicates`, `POST people/duplicates/dismiss {a, b}`, `POST people/{id}/merge {into_id}` |
| Conocimiento | `GET proposals?video_id&profile_id&person_id` (`{items, waiting, discarded}`), `POST knowledge/{id}/recover` (recupera un `descartado_ia`), `POST proposals/decide {accept, reject, edits}`, `PUT knowledge/{id}`, `POST knowledge/{id}/retire`, `POST knowledge/forget-video/{video_id}`, `POST videos/{id}/learn` |
| Voces | `GET people/{id}/voice` (huellas y las 3 mejores muestras), `GET voice-samples/{id}/audio`, `POST voice-embeddings/{id}/decide {keep}` (huella dudosa), `POST voices/recompute` (encola `only: ["voiceprints"]` en los vídeos revisados con datos de trabajo y archivo de vídeo), `DELETE people/{id}/voices` (también las muestras) |
| Revisión | `GET videos/{id}/apply` (fases, segundos estimados y cambios), `POST videos/{id}/apply` («Aplicar y continuar»), `GET videos/{id}/review-items` (puntos de sus seguimientos con una duda de la IA), `POST followups/{id}/items/{item_id}/resolve {action: mismo\|distinto\|descartar}`. El detalle del vídeo incluye `review` (`review.out`), la tarjeta `review`, y `GET status`, `to_review` |
| Seguimientos | `GET/POST followups`, `GET/PUT/DELETE followups/{id}` (PUT: `name`, `description`, `status`, `summary`, `use_ai_summary`; DELETE `?delete_folder`), `POST followups/{id}/open-folder`, `POST followups/{id}/videos/{video_id} {apply, regenerate}`, `DELETE followups/{id}/videos/{video_id}?rebuild`, `POST followups/{id}/rebuild?all_videos&since_video_id`, `POST/PUT/DELETE followups/{id}/items[/{item_id}]` (DELETE oculta), `GET followups/{id}/versions`, `POST followups/{id}/versions/{vid}/restore`. `POST jobs` admite `followup_ids`; `POST videos/{id}/regenerate` y `POST videos/{id}/remove`, `follow_rebuild[]`; el detalle del vídeo, `GET …/regenerate` y `GET …/removal` incluyen `followups` |
| Búsqueda | `GET search?q&profile_id&person_id` |

**Ficheros (`FileResponse`):** un endpoint que sirve un fichero llama a `main._release(session)` antes de
devolverlo. Con FastAPI 0.142, la sesión de `SessionDep` se cierra cuando termina de enviarse la
respuesta, y el reproductor abre una descarga parcial por cada salto en el vídeo: con 15 abiertas se agotaba
el pool de SQLAlchemy (5 + 10) y toda la API fallaba a los 30 s. Pasó en la 1.7.0 y no se veía con los
vídeos de prueba, que caben enteros en el búfer de red: se reproduce con un fichero de cientos de MB y
varias descargas lentas (`curl --limit-rate`).

Las demás rutas sirven el SPA desde `frontend/dist`. Los errores se devuelven como
`HTTPException(código, "mensaje en español")`, y la web muestra `detail` tal cual.

`Job.options` admite: `file_mode` (move o copy), `skip_vision`, `main_track` (índice de pista o
ausente para mezclar todas), `owner_track`, `min_speakers`, `max_speakers`, `num_speakers` y, de uso
interno, `redo[]`, `only[]`, `follow_rebuild[]`, `apply` y `waiting_for` (ver `AI_PIPELINE.md`; las de un
solo encolado están en `main.ONE_SHOT_OPTIONS`).

Quitar un vídeo (`removal.py`, ver `AI_PIPELINE.md`): `POST videos/{id}/remove` lo saca de la BD,
borra sus propuestas pendientes y, solo con las opciones que marque el usuario, borra ficheros. Sin
opciones (y en `DELETE videos/{id}`) no se borra nada y se reescribe `datos/` para poder recuperarlo.
Ninguna otra operación borra vídeos ni carpetas publicadas: mantenlo así. Lo que se borra lo decide
siempre `removal.plan` (tests en `test_removal.py`).

`/api/people/duplicates` va declarada antes que `/api/people/{person_id}` en `main.py`. Si no, FastAPI
intenta convertir «duplicates» en un entero.

## Registros (`logs.py`)

- **Dónde:** `DATA_DIR/logs/AAAA-MM-DD.log` y la consola, con el mismo formato: fecha y hora con milisegundos,
  nivel, logger, contexto y mensaje. `DailyFileHandler` abre el fichero del día al cambiar la fecha, sin
  renombrar (el rotado estándar renombra a medianoche y en Windows falla con el fichero abierto), y
  `cleanup` borra los de hace `log_keep_days` días o más.
- **Cuándo:** `logs.setup` se llama en el `lifespan`, no al importar: los tests (`TestClient` sin `with`) y
  los scripts no crean ficheros. Quita los handlers de uvicorn para que sus líneas y sus trazas pasen por
  nuestro formato, y baja `uvicorn.access` y `httpx` a WARNING.
- **Contexto:** `with logs.context(job=…, video=…, stage=…)` añade «[trabajo 3 · vídeo 1 · analyze]» a
  todo lo registrado dentro (`ContextVar`; el worker lo pone por trabajo y por fase). Para seguir un flujo
  se busca su vídeo.
- **Niveles:** ERROR, falló y el usuario lo nota (con `log.exception`); WARNING, falló y se recuperó o se
  saltó (con `exc_info=True`); INFO, los pasos del flujo y las acciones del usuario; DEBUG, el detalle
  (cada GET y el progreso de las fases), activable con `Settings.log_level`.
- **Peticiones:** `logs.RequestLog` (middleware ASGI propio; `BaseHTTPMiddleware` da problemas con el
  streaming) escribe una línea por petición a `/api/…`: POST/PUT/DELETE en INFO, error o > `SLOW_MS` en
  WARNING y el resto en DEBUG. No registra `/api/events`, los ficheros ni `/api/client-log`.
- **LLM:** `chat_json` registra duración, tokens y `finish_reason` de cada llamada.
- **Web:** `POST /api/client-log` recibe los errores de JavaScript (`main.tsx`) y los registra con el logger
  `web`, una vez por mensaje y minuto. Los `ApiError` de `api.ts` no se mandan: ya los registra el servidor.
- **Qué no se registra nunca:** transcripciones, prompts, respuestas del LLM, notas o correcciones, nombres
  de personas, títulos de vídeo (llevan nombres), la consulta de una URL ni el cuerpo de una petición. Se
  registran ids, fases, tiempos, recuentos y nombres de claves. Un mensaje nuevo sigue esta regla: así el
  usuario puede pasar el registro a otra persona.
- **Añadir un mensaje:** `log = logging.getLogger(__name__)` en el módulo. Un `except` que se traga un
  error deja un WARNING con `exc_info=True`; ruff (`BLE001`) lo exige.

## Ajustes (`config.Settings`)

Es un modelo pydantic que se guarda en `data/settings.json`. La web lo edita con `PUT /api/settings`.
`VT_DATA_DIR` (variable de entorno) cambia la carpeta de datos: base de datos, ajustes, `work/` y
`voces/`. Se usa para pruebas y para segundas instancias.

Al añadir un ajuste:
1. Créalo con un valor por defecto, para que los `settings.json` antiguos sigan siendo válidos.
2. Añádelo en `frontend/src/pages/Settings.tsx` solo si el usuario debe poder cambiarlo.
3. El worker lee los ajustes al empezar cada trabajo (`load_settings()`), así que no hace falta
   reiniciar.
