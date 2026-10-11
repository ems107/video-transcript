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
| `Speaker` | hablante de un vídeo (`SPEAKER_00`) | `person_id` = confirmado; `suggested_person_id` / `suggested_name` = propuesta; `source`: micrófono, voz, pantalla o contexto. En `visual_hints`, las claves con «_» son internas (`_motivo`, `_apodos`) |
| `Segment` | intervención de la transcripción | `speaker` es la etiqueta, no el nombre. `original_text` y `corrections` vienen del glosario |
| `Keyframe` | fotograma analizado | la ruta apunta a `<carpeta>/fotogramas/` |
| `KnowledgeItem` | conocimiento aprendido o propuesto | ver «Conocimiento aprendido» |
| `KnowledgeVersion` | foto de un perfil o persona tras cada cambio | `snapshot` = `{manual, items, person_ids?}` |
| `PersonPairDismissal` | parejas marcadas como «no son la misma persona» | |
| `StageRun` | lo que tardó una fase ejecutada | `seconds` y `units`; ver `estimates.py` |
| `VideoCorrection` | corrección escrita por el usuario sobre un vídeo | `text`, `updated_at`; la IA nunca la modifica |

- **No hay migraciones.** Añadir **tablas** nuevas es seguro. `init_db()` solo ejecuta `create_all`, que crea tablas nuevas pero **no
  añade columnas a tablas que ya existen**. Si añades un campo a una tabla existente, añade también en
  `init_db()` un `ALTER TABLE … ADD COLUMN` idempotente: comprueba antes con `PRAGMA table_info`.
  Indícalo en el CHANGELOG. Si no lo haces, la BD del usuario dará error al arrancar.
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
- **Dueño.** `profile_id` para los tipos `termino`, `contexto` y `seccion`. `person_id` para `dato` y
  `alias`. Una propuesta de un hablante tiene `person_id = None` y `speaker_label`, y se resuelve al
  mostrarla (`proposals.Resolver`). `nueva_persona` lleva el `profile_id` del vídeo para enlazar a la
  persona al aceptarla.
- **Estados.** `propuesto` → `aceptado` | `rechazado`. Un aceptado puede pasar a `retirado`. Los
  aceptados nunca se borran: el historial los necesita.
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
| Sistema | `GET status` (versión, comprobación de componentes y `pending_proposals`), `GET/PUT settings`, `GET probe?path=` |
| Trabajos | `POST jobs {path, profile_id, options}`, `GET jobs`, `POST jobs/{id}/cancel`, `POST jobs/{id}/retry`, `GET events` (SSE, evento `jobs` cada segundo si hay cambios) |
| Vídeos | `GET videos?profile_id&person_id`, `GET/PUT/DELETE videos/{id}`, `GET videos/{id}/file` (con rangos), `GET videos/{id}/thumbnail`, `GET keyframes/{id}/image`, `POST videos/{id}/open-folder`, `GET videos/{id}/regenerate` (niveles, disponibilidad y estimación), `POST videos/{id}/regenerate {level}` (sin cuerpo = `analysis`), `GET/POST videos/{id}/corrections`, `PUT/DELETE corrections/{id}`, `POST videos/{id}/confirm-speakers`, `GET videos/{id}/removal`, `POST videos/{id}/remove {delete_files, delete_video, delete_original, forget}` |
| Hablantes | `PUT speakers/{id} {person_id \| new_person_name, confirm}` |
| Perfiles | CRUD de `profiles` (`person_ids[]` en el cuerpo; la respuesta incluye `learned_count` y `pending_count`), `GET profiles/{id}/knowledge`, `GET profiles/{id}/versions`, `POST profiles/{id}/versions/{vid}/restore`, `POST profiles/from-video {video_id, name}`, `POST profiles/{id}/learn-all` |
| Personas | CRUD de `people` (`GET people/{id}` devuelve la ficha completa), `DELETE people/{id}/voices`, `GET people/{id}/knowledge`, `GET/POST people/{id}/versions[/{vid}/restore]`, `GET people/duplicates`, `POST people/duplicates/dismiss {a, b}`, `POST people/{id}/merge {into_id}` |
| Conocimiento | `GET proposals?video_id&profile_id&person_id` (`{items, waiting}`), `POST proposals/decide {accept, reject, edits}`, `PUT knowledge/{id}`, `POST knowledge/{id}/retire`, `POST knowledge/forget-video/{video_id}`, `POST videos/{id}/learn` |
| Búsqueda | `GET search?q&profile_id&person_id` |

Las demás rutas sirven el SPA desde `frontend/dist`. Los errores se devuelven como
`HTTPException(código, "mensaje en español")`, y la web muestra `detail` tal cual.

`Job.options` admite: `file_mode` (move o copy), `skip_vision`, `main_track` (índice de pista o
ausente para mezclar todas), `owner_track`, `min_speakers`, `max_speakers`, `num_speakers` y `redo[]`
(uso interno).

Quitar un vídeo (`removal.py`, ver `AI_PIPELINE.md`): `POST videos/{id}/remove` lo saca de la BD,
borra sus propuestas pendientes y, solo con las opciones que marque el usuario, borra ficheros. Sin
opciones (y en `DELETE videos/{id}`) no se borra nada y se reescribe `datos/` para poder recuperarlo.
Ninguna otra operación borra vídeos ni carpetas publicadas: mantenlo así. Lo que se borra lo decide
siempre `removal.plan` (tests en `test_removal.py`).

`/api/people/duplicates` va declarada antes que `/api/people/{person_id}` en `main.py`. Si no, FastAPI
intenta convertir «duplicates» en un entero.

## Ajustes (`config.Settings`)

`VT_DATA_DIR` (variable de entorno) cambia la carpeta de datos: base de datos, ajustes y `work/`. Se
usa para pruebas y para segundas instancias.


Es un modelo pydantic que se guarda en `data/settings.json`. La web lo edita con `PUT /api/settings`.
Al añadir un ajuste:
1. Créalo con un valor por defecto, para que los `settings.json` antiguos sigan siendo válidos.
2. Añádelo en `frontend/src/pages/Settings.tsx` solo si el usuario debe poder cambiarlo.
3. El worker lee los ajustes al empezar cada trabajo (`load_settings()`), así que no hace falta
   reiniciar.
