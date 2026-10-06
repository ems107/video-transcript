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

## Instalación (una sola vez)

```powershell
winget install Gyan.FFmpeg        # reabrir la terminal después
cd backend
uv sync                           # Python 3.12 + PyTorch CUDA 12.8 + WhisperX + pyannote
uv run python ../scripts/download_models.py --only llama llm whisper align nltk   # ~25 GB
```

**pyannote community-1** (separación de hablantes) requiere aceptar sus condiciones una vez:

1. Crea una cuenta gratuita en <https://huggingface.co> y acepta las condiciones en
   <https://huggingface.co/pyannote/speaker-diarization-community-1>.
2. Crea un token de lectura en <https://huggingface.co/settings/tokens>.
3. Ejecuta (pedirá el token; no se guarda en ningún sitio):

   ```powershell
   cd backend
   uv run python ../scripts/download_models.py --only diarization
   ```

Después todo funciona sin conexión a internet.

## Uso

```powershell
.\run.ps1            # abre http://127.0.0.1:8770
.\run.ps1 -Rebuild   # recompila el frontend tras cambios
```

1. **Perfiles**: crea uno por tipo de vídeo con el contexto de negocio, el glosario y las personas habituales.
2. **Nuevo análisis**: pega la ruta del vídeo (Explorador → Mayús + clic derecho → «Copiar como ruta»), elige el perfil y añádelo a la cola.
3. Al terminar, el vídeo y sus resultados están en `<carpeta de analizados>/AAAA-MM-DD - Título/`:
   `transcripcion.md`, `transcripcion.txt`, `resumen.md`, `analisis.json`, `miniatura.jpg`, `fotogramas/`.
4. En el detalle del vídeo, **confirma los hablantes**: la app guarda su huella de voz y los reconocerá en próximos vídeos.
   Si cambias nombres o el perfil, «Regenerar análisis» rehace el resumen.

## Cómo funciona

| Fase | Qué hace |
|---|---|
| Ingesta | ffprobe + extracción de audio 16 kHz (mezcla de pistas o la elegida; pista de micrófono opcional) |
| Fotogramas | Muestreo cada 2 s y selección por cambio de escena (hash perceptual) |
| Visión | Qwen3.6 describe cada fotograma: tipo de escena, texto visible, participantes y hablante resaltado |
| Transcripción | Whisper large-v3 con detección de voz y contexto inicial con glosario, personas y términos vistos en pantalla |
| Alineamiento | wav2vec2 español: tiempos por palabra |
| Hablantes | pyannote community-1 + huella de voz por hablante |
| Identificación | Huellas de voz conocidas + nombre resaltado en pantalla + pista de micrófono |
| Corrección | Glosario: variantes declaradas y mayúsculas directas; parecidos fonéticos validados por el LLM |
| Análisis | Resumen por bloques de 30 min y redacción final: título, resumen, tareas, decisiones, pendientes |
| Publicación | Carpeta propia con el vídeo y los documentos; indexado para la búsqueda |

Solo un modelo ocupa la GPU en cada momento. Cada fase guarda un punto de control en `data/work/`,
así que si se cierra la app el trabajo se reanuda donde se quedó.

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
