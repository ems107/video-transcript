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
- Si cambias una respuesta de la API, actualiza su tipo en `frontend/src/api.ts`.
- La app nunca borra vídeos ni carpetas del usuario, salvo en «Quitar» cuando el usuario lo marca, y
  solo con `removal.plan` (ficheros que escribe la app y el vídeo elegido; una carpeta solo si queda
  vacía).
