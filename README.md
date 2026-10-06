# video-transcript

Aplicación web local para transcribir y analizar grabaciones de escritorio (videollamadas, código, presentaciones) con IA 100 % local.

- Transcripción fiel en español con vocabulario de negocio (Whisper large-v3).
- Separación de hablantes (pyannote community-1) y reconocimiento de personas entre vídeos mediante huellas de voz.
- Análisis de lo que se ve en pantalla (Qwen3.6-35B-A3B, modelo de visión y texto vía llama.cpp).
- Resumen detallado, tareas, decisiones y título corto.
- Perfiles con contexto, glosario y personas.
- Biblioteca con miniaturas, búsqueda entre vídeos y carpeta de resultados por vídeo.

## Estructura

```
backend/    API FastAPI + pipeline de IA (Python 3.12, uv)
frontend/   Web React + Vite + TypeScript
scripts/    Utilidades (descarga de modelos, etc.)
models/     Modelos descargados (no se versiona)
data/       Base de datos y ficheros de trabajo (no se versiona)
```

## Requisitos

- Windows 10/11 con GPU NVIDIA (probado con RTX 5070 Ti, 16 GB) y driver con CUDA 12.8+.
- [uv](https://docs.astral.sh/uv/), Node.js 20+, ffmpeg, llama.cpp (build CUDA).

## Licencias de los modelos

Todo el software y los modelos son gratuitos y se ejecutan localmente:

| Componente | Licencia |
|---|---|
| Whisper large-v3 (OpenAI) | MIT |
| wav2vec2-large-xlsr-53-spanish (J. Grosman) | Apache-2.0 |
| Qwen3.6-35B-A3B (Alibaba Qwen) | Apache-2.0 |
| llama.cpp, faster-whisper, WhisperX | MIT / BSD |
| ffmpeg | LGPL/GPL |
| pyannote speaker-diarization-community-1 | CC-BY-4.0 |

### Atribución

Separación de hablantes: *pyannote/speaker-diarization-community-1* por pyannoteAI ([modelo](https://huggingface.co/pyannote/speaker-diarization-community-1)), licencia [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). Su descarga requiere una cuenta gratuita de Hugging Face y aceptar sus condiciones una única vez; después funciona sin conexión.
