# video-transcript

[![Versión](https://img.shields.io/github/v/release/ems107/video-transcript?label=versi%C3%B3n)](https://github.com/ems107/video-transcript/releases)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-blue.svg)](LICENSE)

Aplicación web local para transcribir y analizar grabaciones del escritorio (videollamadas, código, presentaciones,
programas) con IA **100 % local, libre y gratuita**. Ningún audio, imagen ni texto sale del ordenador.

Qué aporta cada versión: [CHANGELOG](CHANGELOG.md).

## Índice

- [Qué hace](#qué-hace)
- [Requisitos](#requisitos)
- [Instalación](#instalación-una-sola-vez)
- [Uso](#uso)
- [Cómo funciona](#cómo-funciona)
- [Desarrollo](#desarrollo)
- [Versiones](#versiones)
- [Licencias](#licencias)

## Qué hace

- **Transcripción fiel** en español, con términos técnicos sueltos en inglés y vocabulario de negocio
  (Whisper large-v3).
- **Separación de hablantes** (pyannote community-1) y **reconocimiento de las mismas personas** en
  distintos vídeos por su huella de voz. La app propone y tú confirmas.
- **Análisis de lo que se ve en pantalla** (Qwen3.6-35B-A3B): videollamada, código, documentos o
  diapositivas. Lo visto aporta contexto, nombres y términos a la transcripción y al resumen.
- **Resumen detallado**, tareas, decisiones, temas pendientes y un título corto, con marcas de tiempo
  para comprobar cada punto.
- **Perfiles** por tipo de vídeo, con contexto de negocio, glosario, personas habituales, instrucciones
  y secciones del resumen.
- **Conocimiento que se acumula.** Con cada vídeo, la IA propone lo que aprende del negocio (términos,
  proyectos, clientes, sistemas) y de cada persona (cargo, equipo, responsabilidades, conocimientos…).
  Tú lo apruebas. Lo manual nunca se toca, cada propuesta indica de dónde sale y todo tiene historial
  con vuelta atrás.
- **Fichas de persona** con lo aprendido, sus vídeos, el tiempo que ha hablado y las tareas que se le
  han asignado. Avisa de posibles personas duplicadas y permite fusionarlas.
- **Carpeta de resultados por vídeo**: `AAAA-MM-DD - Título/` contiene el vídeo original (movido o
  copiado) y todos los documentos.
- **Biblioteca web** con miniaturas, reproductor sincronizado con la transcripción, búsqueda en todos
  los vídeos y botón «Abrir carpeta».

## Requisitos

- Windows 10/11 con GPU NVIDIA de 16 GB (probado con una RTX 5070 Ti) y un driver con CUDA 12.8 o
  posterior.
- 32 GB de RAM o más: parte del modelo de lenguaje se carga en RAM. Se ha probado con 64 GB.
- Unos 30 GB libres para los modelos.
- [uv](https://docs.astral.sh/uv/), [Node.js](https://nodejs.org/) 20+, [git](https://git-scm.com/).
- ffmpeg y llama.cpp (build CUDA). El script de descarga instala llama.cpp en `models/`.

## Instalación (una sola vez)

```powershell
git clone https://github.com/ems107/video-transcript.git
cd video-transcript
winget install Gyan.FFmpeg        # reabrir la terminal después
cd backend
uv sync                           # Python 3.12 + PyTorch CUDA 12.8 + WhisperX + pyannote
uv run python ../scripts/download_models.py --only llama llm whisper align nltk   # ~25 GB
```

**pyannote community-1** (separación de hablantes) es gratuito y tiene licencia CC-BY-4.0, pero su
descarga exige aceptar sus condiciones una vez:

1. Crea una cuenta gratuita en <https://huggingface.co> y acepta las condiciones en
   <https://huggingface.co/pyannote/speaker-diarization-community-1>.
2. Crea un token de lectura en <https://huggingface.co/settings/tokens>.
3. Ejecuta lo siguiente. Pedirá el token, que no se guarda en ningún sitio:

   ```powershell
   cd backend
   uv run python ../scripts/download_models.py --only diarization
   ```

Después todo funciona sin conexión a internet.

## Uso

```powershell
.\run.ps1            # abre http://127.0.0.1:8770
.\run.ps1 -Rebuild   # recompila el frontend tras actualizar
```

1. **Perfiles**: crea uno por tipo de vídeo con el contexto de negocio, el glosario y las personas
   habituales. Cada línea del glosario tiene el formato `Término | variantes mal oídas | definición`.
2. **Nuevo análisis**: pega la ruta del vídeo (en el Explorador, Mayús + clic derecho → «Copiar como
   ruta»), elige el perfil y si el vídeo se mueve o se copia, y añádelo a la cola.
3. **Cola**: muestra el progreso de cada fase. Si cierras la app, el trabajo se reanuda donde se quedó.
4. Al terminar, el vídeo y sus resultados están en `<carpeta de analizados>/AAAA-MM-DD - Título/`:
   `transcripcion.md`, `transcripcion.txt`, `resumen.md`, `analisis.json`, `miniatura.jpg` y
   `fotogramas/`.
5. En el detalle del vídeo, **confirma los hablantes**. La app guarda su huella de voz y los reconocerá
   en los próximos vídeos. Si cambias nombres o el perfil, «Regenerar análisis» rehace el resumen.
6. **Propuestas**: revisa lo que la IA ha aprendido del vídeo (ver abajo).
7. **Buscar**: busca en todas las transcripciones y resúmenes (sin distinguir tildes; las comillas
   buscan la frase exacta).

### Conocimiento aprendido (perfiles y personas)

- **Cómo se genera.** Tras cada análisis, la IA propone:
  - para el perfil: términos, hechos duraderos del negocio y secciones del resumen;
  - para las personas: datos de cada una, a partir de lo que dice y de lo que otros dicen de ella.

  Cada propuesta muestra el vídeo y el momento del que sale. Lo que no aparece en la transcripción o
  en la pantalla se descarta.
- **Cómo se revisa.** En **Propuestas** (o en el detalle del vídeo, del perfil o de la persona)
  aceptas, editas o rechazas cada propuesta. Nada se usa hasta que lo aceptas, y lo rechazado no se
  vuelve a proponer.
- **Lo que dice cada hablante.** Se atribuye a su persona cuando está confirmada o reconocida por voz
  con confianza alta. Si no, la propuesta espera a que confirmes al hablante.
- **Separación entre lo manual y lo aprendido.** Lo que escribes a mano en un perfil o una persona es
  tuyo y la IA nunca lo modifica. Lo aprendido va aparte, y si hay contradicción prevalece lo manual.
  Lo aceptado se usa en los análisis siguientes: contexto del resumen y vocabulario de Whisper. Los
  términos aprendidos nunca corrigen la transcripción sin que el LLM valide cada cambio.
- **Deshacer.** Cada cambio crea una versión en el **Historial** del perfil o de la persona, y puedes
  restaurar cualquiera. También puedes **retirar** un dato concreto, u **olvidar lo aprendido de un
  vídeo** si ese vídeo era atípico.
- **Crear un perfil desde un vídeo.** En el detalle de un vídeo sin perfil, pulsa «Crear perfil a
  partir de este vídeo»: la IA propone su contenido. Para aprovechar vídeos ya analizados, usa
  «Aprender de todos sus vídeos» en el perfil.

### Actualizar a una nueva versión

```powershell
git pull
cd backend; uv sync; cd ..
.\run.ps1 -Rebuild
```

Antes de actualizar, lee en el [CHANGELOG](CHANGELOG.md) si la versión requiere algún paso adicional.
Las versiones mayores pueden requerirlo.

## Cómo funciona

| Fase | Qué hace |
|---|---|
| Ingesta | ffprobe y extracción del audio a 16 kHz (mezcla de pistas o la elegida; pista de micrófono opcional) |
| Fotogramas | Muestreo cada 2 s y selección por cambio de escena (hash perceptual) |
| Visión | Qwen3.6 describe cada fotograma: tipo de escena, texto visible, participantes y hablante resaltado |
| Transcripción | Whisper large-v3 con detección de voz y un contexto inicial con el glosario (manual y aprendido), las personas y los términos vistos en pantalla |
| Alineamiento | wav2vec2 español: tiempos por palabra |
| Hablantes | pyannote community-1 y huella de voz de cada hablante |
| Identificación | Huellas de voz conocidas, nombre resaltado en pantalla y pista de micrófono |
| Corrección | Glosario: variantes declaradas y mayúsculas directas; los parecidos fonéticos los valida el LLM |
| Análisis | Resumen por bloques de 30 min y redacción final: título, resumen, tareas, decisiones y pendientes |
| Aprendizaje | Propuestas verificadas para el perfil y las personas (términos, hechos, datos de cada persona) |
| Publicación | Carpeta propia con el vídeo y los documentos, indexada para la búsqueda |

Solo un modelo ocupa la GPU en cada momento: llama-server se arranca y se detiene según la fase. Cada
fase guarda un punto de control en `data/work/`.

## Desarrollo

```
backend/    API FastAPI + pipeline de IA (Python 3.12, uv, SQLite + FTS5)
  app/pipeline/   una fase por módulo (ingest, frames, vision, asr, diarize, identify, correct, analyze, export)
  tests/          pruebas de la lógica sin GPU
frontend/   Web React + Vite + TypeScript
scripts/    download_models.py (modelos), release.py (versiones)
docs/       documentación del proyecto (docs/ai/: guías técnicas para asistentes de IA)
models/     modelos descargados (no se versiona)
data/       base de datos, ajustes y ficheros de trabajo (no se versiona)
```

```powershell
# backend con recarga automática
cd backend; uv run uvicorn app.main:app --port 8770 --reload
# frontend con recarga automática (http://localhost:5173, redirige /api al backend)
cd frontend; npm install; npm run dev
# pruebas
cd backend; uv run pytest
```

Para desarrollar con asistentes de IA (Claude Code), [`CLAUDE.md`](CLAUDE.md) recoge las restricciones,
los comandos y el mapa del código, y enlaza las guías de cada parte en [`docs/ai/`](docs/ai/).

## Versiones

El proyecto usa [versionado semántico](https://semver.org/lang/es/). Cada versión tiene:

- un tag `vX.Y.Z`;
- una [release en GitHub](https://github.com/ems107/video-transcript/releases);
- su entrada en el [CHANGELOG](CHANGELOG.md), donde se explica qué aporta.

La versión instalada se muestra en la barra lateral de la web.

El flujo para desarrollar nuevas funciones y publicar versiones está en
[docs/VERSIONADO.md](docs/VERSIONADO.md). En resumen:

```powershell
git switch -c feature/mi-funcion      # desarrollar en una rama
# ... commits + entrada en "Sin publicar" del CHANGELOG ...
git switch main; git merge --no-ff feature/mi-funcion
python scripts/release.py minor --push   # o patch / major
```

## Licencias

El código de este repositorio se distribuye bajo la licencia [MIT](LICENSE).

Todos los componentes y modelos son gratuitos y se ejecutan localmente:

| Componente | Licencia |
|---|---|
| Whisper large-v3 (OpenAI) | MIT |
| wav2vec2-large-xlsr-53-spanish (J. Grosman) | Apache-2.0 |
| Qwen3.6-35B-A3B (Alibaba Qwen) | Apache-2.0 |
| llama.cpp, faster-whisper, WhisperX | MIT / BSD |
| ffmpeg | LGPL/GPL |
| pyannote speaker-diarization-community-1 | CC-BY-4.0 |

### Atribución

Separación de hablantes: *pyannote/speaker-diarization-community-1* por pyannoteAI
([modelo](https://huggingface.co/pyannote/speaker-diarization-community-1)), licencia
[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/). Su descarga requiere una cuenta gratuita de
Hugging Face y aceptar sus condiciones una única vez. Después funciona sin conexión.
