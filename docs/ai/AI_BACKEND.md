# Backend: datos, API y ajustes

FastAPI en `backend/app/main.py` y SQLite en `data/app.db` (modo WAL, `foreign_keys=ON`). Las rutas
salen de `config.py`: `ROOT_DIR`, `DATA_DIR`, `MODELS_DIR`, `WORK_DIR` y `FRONTEND_DIST`.

## Modelo de datos (`models.py`)

| Tabla | Para qué | Notas |
|---|---|---|
| `Profile` | tipo de vídeo | `context`, `extra_prompt`, `summary_sections[]` y `glossary[{term, variants[], definition}]` en JSON |
| `Person` | persona global (puede estar en varios perfiles) | `aliases[]` incluye los nombres que aparecen en las videollamadas |
| `ProfilePersonLink` | relación de muchos a muchos entre perfiles y personas | |
| `VoiceEmbedding` | huella confirmada (una por hablante confirmado y vídeo) | `vector` en JSON |
| `Video` | un vídeo | `status`: pending, processing, done o error. `analysis` guarda el JSON completo; `folder` y `video_path` se rellenan al publicar |
| `Job` | un trabajo de la cola | `status`: queued, running, done, error o cancelled. `options` (ver abajo). `error` incluye el traceback |
| `Speaker` | hablante de un vídeo (`SPEAKER_00`) | `person_id` = confirmado; `suggested_person_id` / `suggested_name` = propuesta; `source`: micrófono, voz o pantalla |
| `Segment` | intervención de la transcripción | `speaker` es la etiqueta, no el nombre. `original_text` y `corrections` vienen del glosario |
| `Keyframe` | fotograma analizado | la ruta apunta a `<carpeta>/fotogramas/` |

- **No hay migraciones.** `init_db()` solo ejecuta `create_all`, que crea tablas nuevas pero **no
  añade columnas a tablas que ya existen**. Si añades un campo a una tabla existente, añade también en
  `init_db()` un `ALTER TABLE … ADD COLUMN` idempotente: comprueba antes con `PRAGMA table_info`.
  Indícalo en el CHANGELOG. Si no lo haces, la BD del usuario dará error al arrancar.
- Para las fechas usa `NaiveDatetime` (por SQLModel 0.0.47) y `now()` de `models.py`.
- Los campos de lista o diccionario usan `sa_column=Column(JSON)`. Si modificas una lista en su sitio,
  SQLAlchemy no lo detecta: reasigna el valor completo.
- El nombre que se muestra de cada hablante se resuelve **siempre** con `services.speaker_names()`.
  El orden es: persona confirmada, persona propuesta, nombre visto en pantalla y, por último,
  «Hablante N».

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
| Sistema | `GET status` (versión + comprobación de componentes), `GET/PUT settings`, `GET probe?path=` |
| Trabajos | `POST jobs {path, profile_id, options}`, `GET jobs`, `POST jobs/{id}/cancel`, `POST jobs/{id}/retry`, `GET events` (SSE, evento `jobs` cada segundo si hay cambios) |
| Vídeos | `GET videos?profile_id&person_id`, `GET/PUT/DELETE videos/{id}`, `GET videos/{id}/file` (con rangos), `GET videos/{id}/thumbnail`, `GET keyframes/{id}/image`, `POST videos/{id}/open-folder`, `POST videos/{id}/regenerate`, `POST videos/{id}/confirm-speakers` |
| Hablantes | `PUT speakers/{id} {person_id \| new_person_name, confirm}` |
| Perfiles | CRUD de `profiles` (`person_ids[]` en el cuerpo) |
| Personas | CRUD de `people`, `DELETE people/{id}/voices` |
| Búsqueda | `GET search?q&profile_id&person_id` |

Las demás rutas sirven el SPA desde `frontend/dist`. Los errores se devuelven como
`HTTPException(código, "mensaje en español")`, y la web muestra `detail` tal cual.

`Job.options` admite: `file_mode` (move o copy), `skip_vision`, `main_track` (índice de pista o
ausente para mezclar todas), `owner_track`, `min_speakers`, `max_speakers`, `num_speakers` y `redo[]`
(uso interno).

`DELETE videos/{id}` solo quita el vídeo de la BD y **no borra archivos**. Ninguna operación de la app
borra vídeos ni carpetas publicadas. Mantenlo así, salvo que el usuario pida otra cosa de forma
explícita.

## Ajustes (`config.Settings`)

Es un modelo pydantic que se guarda en `data/settings.json`. La web lo edita con `PUT /api/settings`.
Al añadir un ajuste:
1. Créalo con un valor por defecto, para que los `settings.json` antiguos sigan siendo válidos.
2. Añádelo en `frontend/src/pages/Settings.tsx` solo si el usuario debe poder cambiarlo.
3. El worker lee los ajustes al empezar cada trabajo (`load_settings()`), así que no hace falta
   reiniciar.
