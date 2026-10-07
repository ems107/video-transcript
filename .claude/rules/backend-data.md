---
paths:
  - "backend/app/models.py"
  - "backend/app/db.py"
  - "backend/app/main.py"
  - "backend/app/services.py"
  - "backend/app/config.py"
---

# Datos, API y ajustes

Lee `docs/ai/AI_BACKEND.md` antes de editar.

- No hay migraciones: una columna nueva en una tabla existente necesita un `ALTER TABLE` idempotente
  en `init_db()`.
- Después de modificar un vídeo publicado, llama a `services.export_video` y `services.index_video`.
- Los nombres de los hablantes se obtienen siempre con `services.speaker_names()`.
- Si cambias una respuesta de la API, actualiza su tipo en `frontend/src/api.ts`.
- La app nunca borra vídeos ni carpetas del usuario.
