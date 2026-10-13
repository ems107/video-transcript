# video-transcript

App web local (FastAPI + React) que transcribe y analiza grabaciones del escritorio: videollamadas en
español con términos técnicos sueltos en inglés, de 30 minutos a más de 3 horas. Produce la
transcripción con hablantes identificados entre vídeos, el análisis de la pantalla, un resumen, tareas
y decisiones, y un título. Cada vídeo se publica en su propia carpeta `AAAA-MM-DD - Título/`. El
usuario final es una sola persona en su PC con Windows y una RTX 5070 Ti de 16 GB.

## Restricciones (no negociables)

- **Solo software y modelos libres, gratuitos y locales.** Nada de APIs de pago ni servicios en la
  nube, y nada que envíe audio, imagen o texto fuera del equipo. Si una mejora requiere algo de pago o
  con licencia restrictiva, pregunta antes.
- **Genérico, no atado a ningún programa.** Prompts, ejemplos e interfaz no deben mencionar programas
  concretos de videollamada o escritorio. La pantalla puede mostrar cualquier cosa.
- **Fidelidad.** La transcripción y el análisis nunca inventan contenido. La corrección de términos es
  conservadora (ver `docs/ai/AI_PROMPTS.md`).
- **La IA propone y el usuario decide.** Lo manual de perfiles y personas nunca lo modifica la IA. Lo
  aprendido solo se usa tras aceptarlo, cada propuesta lleva su evidencia y todo cambio crea una
  versión que se puede restaurar.
- **Tokens y secretos.** El token de Hugging Face nunca se guarda en disco ni en el repositorio, y no
  debe pegarse en la conversación. El usuario ejecuta en su propia terminal las descargas que lo
  necesitan.
- **Una sola GPU de 16 GB.** Nunca debe haber dos modelos grandes cargados a la vez (ver
  `docs/ai/AI_MODELS_GPU.md`).

## Principios de diseño

- **Revisar antes de aprender.** Un vídeo recién analizado queda pendiente de revisar: el seguimiento, el
  aprendizaje y las huellas de voz solo se ejecutan cuando el usuario pulsa «Aplicar y continuar», y los
  vídeos relacionados esperan a esa revisión (`review.py`).
- **Razonar, no reglas fijas.** Lo que es relevante o ruido lo razona la IA con el contexto y marca lo
  dudoso para el usuario; Python comprueba lo verificable (citas, formas oídas, cifras). No se ajustan
  umbrales para que salga bien un caso concreto.
- **Poca interacción, pero calidad primero.** El usuario quiere tocar la app lo mínimo tras analizar un
  vídeo, pero prefiere decidir algo dudoso a que se guarde mal.
- **Medir antes de dar algo por mejorado.** El modelo varía entre ejecuciones: un cambio de prompt se
  compara con el actual sobre los mismos datos, al menos dos veces (`docs/ai/AI_PROMPTS.md`).

## Comandos

```powershell
.\run.ps1 [-Rebuild] [-NoBrowser]                          # app completa en http://127.0.0.1:8770
cd backend;  uv run pytest                                 # pruebas (sin GPU, unos segundos)
cd backend;  uv run uvicorn app.main:app --port 8770 --reload
cd frontend; npm run dev                                   # :5173, redirige /api a :8770
cd frontend; npm run build                                 # tsc -b + vite build (comprueba los tipos)
cd frontend; npm run lint                                  # oxlint
python scripts/release.py patch|minor|major [--push]       # publicar una versión (docs/VERSIONADO.md)
```

- El entorno Python lo gestiona `uv` (Python 3.12). No uses `pip` ni el Python del sistema para el
  backend.
- `ruff check` ya da avisos en el código existente. No los corrijas de forma masiva fuera de la tarea,
  pero el código nuevo no debe añadir más. `Optional[...]` en `models.py` es intencionado, porque
  SQLModel lo requiere.
- Shell: Windows. En Git Bash, `curl` con argumentos UTF-8 falla; envía el cuerpo con
  `--data-binary @fichero`. Usa `MSYS_NO_PATHCONV=1` si pasas rutas `/api/...` como argumentos. Los
  heredocs de bash con `\` al final de línea fallan: escribe los scripts con la herramienta Write.

## Mapa del código

```
backend/app/
  main.py        API REST + SSE (/api/events) + sirve frontend/dist
  worker.py      cola de un hilo: STAGES, reanudación por fases, publicación (_publish)
  pipeline/      una fase por módulo; base.py define JobContext
  prompts.py     todos los prompts y esquemas JSON del LLM
  services.py    helpers de BD compartidos por la API y el worker (exportar, indexar, nombres)
  knowledge.py   lógica pura del conocimiento aprendido (dedup, verificación, atribución, versiones)
  knowledge_store.py / proposals.py / people.py   conocimiento en BD, revisión de propuestas, fichas y fusión
  removal.py     quitar un vídeo (qué se borra) y copia de recuperación `datos/` en la carpeta publicada
  regenerate.py / estimates.py   niveles de regeneración y estimación de tiempos (tabla StageRun)
  speaker_fix.py arreglos manuales de hablantes (SpeakerOverride); la comprobación por la voz está en pipeline/voices.py
  followups.py / followups_store.py   seguimientos: lógica pura del estado (puntos, contexto, aplicar y deshacer) y BD
  review.py      revisión del vídeo: estados, espera de los vídeos relacionados y «Aplicar y continuar»
  logs.py        registros: fichero diario en data/logs, contexto [trabajo · vídeo · fase] y middleware HTTP
  models.py      tablas SQLModel;  db.py: motor SQLite + FTS5
  config.py      Settings (persistidos en data/settings.json) y rutas
  env.py         variables de entorno sin conexión; se importa antes que cualquier librería de IA
  llm.py         arranca y para llama-server; chat_json con salida JSON validada por esquema
  media.py       ffprobe / ffmpeg
backend/tests/   un test por módulo (BD en memoria, sin GPU); conftest.py: client, session
frontend/src/    App.tsx (rutas), api.ts (tipos + cliente), util.ts, pages/*.tsx, help/*.md, index.css
scripts/         download_models.py, release.py, help_screenshots.py (capturas de la ayuda)
models/ data/ samples/   no se versionan (modelos, BD y trabajo, vídeos de prueba)
```

## Guías por tema (léelas antes de tocar esa parte)

| Si vas a… | Lee |
|---|---|
| Tocar una fase, añadir otra o cambiar la reanudación o la publicación | `docs/ai/AI_PIPELINE.md` |
| Cambiar modelos, VRAM, llama-server, dependencias de IA o la descarga | `docs/ai/AI_MODELS_GPU.md` |
| Cambiar prompts, el glosario, la identificación de hablantes, el resumen o el aprendizaje | `docs/ai/AI_PROMPTS.md` |
| Tocar el conocimiento aprendido (propuestas, versiones, fichas, fusión) | `docs/ai/AI_BACKEND.md` y `AI_PROMPTS.md` |
| Cambiar tablas, endpoints, ajustes o la búsqueda | `docs/ai/AI_BACKEND.md` |
| Cambiar páginas, tipos de la API o estilos | `docs/ai/AI_FRONTEND.md` |
| Publicar una versión | `docs/VERSIONADO.md` |

`.claude/rules/*.md` recuerdan las reglas clave de cada zona del código y se cargan solas al tocar
sus ficheros.

**La ayuda de la app (`frontend/src/help/*.md`) es la documentación del usuario.** Todo cambio visible
actualiza su página en el mismo commit. Una decisión nueva (un umbral, un límite, un ajuste) se explica en
«Decisiones, límites y umbrales»: qué, por qué, consecuencia y si se puede cambiar, con los valores como
`{{v:clave}}` (registrados en `backend/app/help_values.py`) y lo técnico en bloques `:::tecnico`. Si
cambia una pantalla, rehaz sus capturas con `scripts/help_screenshots.py`. Ver `docs/ai/AI_FRONTEND.md`.

**Mantén esta documentación al día.** Si un cambio deja algo de este fichero, de `docs/ai/` o de
`.claude/rules/` desactualizado (rutas, fases, claves, comandos, umbrales), actualízalo en el mismo
commit. Lo que se pueda deducir leyendo el código no hace falta documentarlo.

## Convenciones

- **Idioma:** la interfaz, los mensajes al usuario, los prompts, los comentarios, los docstrings y los
  mensajes de commit van en español. Los identificadores de código van en inglés, salvo las claves JSON
  del análisis (`titulo`, `tareas`…), que la web y los exportadores ya usan.
- Comentarios escasos: explican el *porqué*. Imita el estilo del fichero que edites.
- **Registros:** `log = logging.getLogger(__name__)`. Registra ids, fases, tiempos y recuentos, nunca
  contenido (transcripción, prompts, notas, nombres, títulos). Un `except` que se traga un error deja un
  WARNING con `exc_info=True`. Ver «Registros» en `docs/ai/AI_BACKEND.md`.
- **Git:** commits pequeños y descriptivos por cada paso lógico que funcione. Las funciones nuevas van
  en una rama `feature/...`. Cada cambio visible para el usuario lleva una línea bajo
  `## [Sin publicar]` en `CHANGELOG.md`, dentro del mismo commit. No hagas push, no crees tags y no
  publiques releases si el usuario no lo pide. Si hay dos versiones en curso, publica la primera antes de
  fusionar la segunda en `main` (ver `docs/VERSIONADO.md`).
- **Versión:** su única fuente es el fichero `VERSION`. Los manifiestos los actualiza `release.py`;
  no la cambies a mano.

## Verificación antes de dar algo por terminado

1. `uv run pytest` en verde. Si cambias lógica, añade o ajusta su test: hay uno por módulo
   (`test_followups.py`, `test_review.py`, `test_voices.py`, `test_learn.py`…) y `test_logic.py` para el
   glosario, la voz, el troceo y la transcripción. Comprueba que el test nuevo falla sin el arreglo.
2. Si cambias el frontend o `api.ts`, comprueba que compila sin tocar `frontend/dist`, que es el de la
   instancia del usuario: `npx tsc -b` y `npx vite build --outDir <scratchpad>`.
3. Si cambias la pipeline o los prompts, haz una prueba de punta a punta con un vídeo corto **en una
   instancia aislada** (`VT_DATA_DIR`, API en :8771, `llm_port` 8092). Así no se tocan los datos del
   usuario. Los vídeos de prueba están en `samples/videos-prueba/`. Para no mover los vídeos de muestra,
   usa `file_mode: "copy"`. Recuerda «Aplicar y continuar»: sin él no se ejecutan el seguimiento ni el
   aprendizaje. El procedimiento completo está en «Prueba de punta a punta» de `docs/ai/AI_PIPELINE.md`.
4. Al terminar, para la instancia de prueba **y su llama-server** (sigue vivo si solo paras uvicorn). Si la
   prueba crea datos que el usuario no ha pedido, bórralos o avísale.
