---
paths:
  - "backend/app/models.py"
  - "backend/app/db.py"
  - "backend/app/main.py"
  - "backend/app/services.py"
  - "backend/app/config.py"
  - "backend/app/knowledge_store.py"
  - "backend/app/proposals.py"
  - "backend/app/people.py"
  - "backend/app/followups.py"
  - "backend/app/followups_store.py"
  - "backend/app/review.py"
  - "backend/app/speaker_fix.py"
  - "backend/app/regenerate.py"
  - "backend/app/removal.py"
  - "backend/app/estimates.py"
  - "backend/app/help_values.py"
  - "backend/tests/**"
---

# Datos, API y ajustes

Lee `docs/ai/AI_BACKEND.md` antes de editar.

- No hay migraciones: las tablas nuevas son seguras, pero una columna nueva en una tabla existente
  se declara en `db.NEW_COLUMNS` (`init_db` la añade si falta).
- Cambios en lo manual o lo aceptado de perfiles y personas: `KS.ensure_baseline` antes y
  `KS.record_version` después (o `proposals._Owners`). Nunca borres elementos aceptados: se retiran.
- Las pruebas de API usan `tests/conftest.py` (`client`, `session`), con la BD en memoria.
- Después de modificar un vídeo publicado, llama a `services.export_video` y `services.index_video`.
- Los nombres de los hablantes se obtienen siempre con `services.speaker_names()`.
- Seguimientos: antes de cambiar su estado, `followups_store.record_version`; después,
  `followups_store.export`. Lo que toca el usuario es `manual` (y lo que borra, `hidden`): la IA nunca
  cambia su texto ni su estado.
- Si cambias una respuesta de la API, actualiza su tipo en `frontend/src/api.ts`.
- Registros: ids, fases y recuentos, nunca contenido (ver «Registros» en `AI_BACKEND.md`). Una acción
  del usuario que cambie el estado deja una línea INFO con lo que hizo.
- Un endpoint que devuelve un fichero (`FileResponse`) llama antes a `_release(session)`: si no, retiene
  una conexión a la BD mientras se envía y un vídeo largo agota el pool (ver `AI_BACKEND.md`).
- Revisión del vídeo (`review.py`): `follow`, `learn` y `voiceprints` solo corren al aplicar la revisión.
  Un cambio del usuario que requiera la IA llama a `review.mark_changed`; lo que puede dejar el vídeo
  revisado, a `review.check_done`. Una opción de `Job.options` que valga para un solo encolado va en
  `main.ONE_SHOT_OPTIONS` (cada vídeo reutiliza su último `Job`). Ver `docs/ai/AI_PIPELINE.md`.
- Un umbral o límite nuevo que vea el usuario se explica en la ayuda (`decisiones.md`) con `{{v:clave}}`
  registrada en `help_values.py`.
- La app nunca borra vídeos ni carpetas del usuario, salvo en «Quitar» cuando el usuario lo marca, y
  solo con `removal.plan` (ficheros que escribe la app y el vídeo elegido; una carpeta solo si queda
  vacía).
