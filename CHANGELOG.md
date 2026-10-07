# Historial de cambios

Todos los cambios relevantes de cada versión se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[versionado semántico](https://semver.org/lang/es/). Cómo añadir entradas y publicar una versión:
[docs/VERSIONADO.md](docs/VERSIONADO.md).

## [Sin publicar]

### Añadido

- Documentación para asistentes de IA: `CLAUDE.md`, guías por tema en `docs/ai/` y reglas por zona
  del código en `.claude/rules/`.

## [1.0.0] - 2026-10-07

Primera versión completa: transcripción, hablantes, visión, análisis y biblioteca, todo local.

### Añadido

- **Transcripción** en español con Whisper large-v3 (faster-whisper/WhisperX). El prompt inicial se
  construye con el glosario, las personas y los términos vistos en pantalla, y se filtran los ecos del
  prompt.
- **Tiempos por palabra** mediante alineamiento con wav2vec2 español.
- **Separación de hablantes** con pyannote speaker-diarization-community-1, cargado desde una carpeta
  local y sin conexión.
- **Identificación de personas entre vídeos**:
  - Huellas de voz comparadas con las ya conocidas, con propuesta automática y confirmación por el
    usuario. Cada confirmación guarda una nueva muestra de voz.
  - Nombre del hablante resaltado en pantalla.
  - Pista del micrófono propio en grabaciones con varias pistas de audio.
- **Análisis de la imagen** con Qwen3.6-35B-A3B (llama.cpp). Se seleccionan fotogramas por cambio de
  escena y se obtienen el tipo de escena, el programa visible, el texto relevante, los participantes y
  los términos.
- **Corrección conservadora con el glosario**: se aplican las variantes declaradas y las mayúsculas, y
  el LLM solo valida los parecidos fonéticos.
- **Análisis** por bloques de 30 minutos, pensado para vídeos de varias horas: título corto, resumen
  breve y detallado, participantes, temas, tareas, decisiones y pendientes, con marcas de tiempo.
- **Perfiles** por tipo de vídeo: contexto de negocio, glosario, personas, instrucciones adicionales y
  secciones del resumen.
- **Publicación** en `<carpeta de analizados>/AAAA-MM-DD - Título/`. El vídeo se mueve o se copia, y la
  carpeta incluye `transcripcion.md`, `transcripcion.txt`, `resumen.md`, `analisis.json`,
  `miniatura.jpg` y `fotogramas/`.
- **Cola de trabajos** de un solo hilo: progreso en tiempo real por SSE, cancelación, reintento y
  reanudación por fases. Solo un modelo ocupa la GPU en cada momento.
- **Web** (React + Vite):
  - Biblioteca con miniaturas.
  - Detalle con un reproductor sincronizado con la transcripción, resumen, tareas y decisiones, y la
    cronología de pantalla.
  - Confirmación y renombrado de hablantes, y regeneración del análisis.
  - Botón «Abrir carpeta».
  - Búsqueda en todos los vídeos (FTS5, sin distinguir tildes).
  - Páginas de Perfiles, Personas y Ajustes.
- `scripts/download_models.py` descarga todos los modelos. El token de Hugging Face no se guarda.
- `run.ps1` arranca la app con un solo comando.
- La versión de la app se muestra en la web y en `/api/status`.

[Sin publicar]: https://github.com/ems107/video-transcript/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ems107/video-transcript/releases/tag/v1.0.0
