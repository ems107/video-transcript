# Pipeline de análisis

Orquestación: `backend/app/worker.py`. Fases: `backend/app/pipeline/*.py`. Un único hilo
procesa los trabajos (`Job`) en orden de id.

## Fases y ficheros de trabajo

Cada trabajo tiene la carpeta `data/work/job_<id>/`. Una fase lee los JSON de las fases anteriores y
escribe los suyos con `ctx.save()`, que es atómico (`.tmp` y después `replace`). Al terminar, el
worker crea `<fase>.done`.

| Fase (`STAGES`) | Módulo | Lee | Escribe | Modelo en GPU |
|---|---|---|---|---|
| `ingest` | `ingest.py` | vídeo | `probe.json`, `audio.wav`, `owner.wav`* | — |
| `frames` | `frames.py` | `probe.json` | `frames/`, `frames.json`, `thumbnail.jpg` | — (ffmpeg `-hwaccel auto`) |
| `vision` | `vision.py` | `frames.json`, `frames/` | `vision.json`, `screen_terms.json` (`vision.partial.json`) | llama-server |
| `asr` | `asr.py:run_asr` | `audio.wav`, `screen_terms.json` | `whisper_prompt.json`, `asr.json` | Whisper |
| `align` | `asr.py:run_align` | `asr.json`, `audio.wav` | `aligned.json` | wav2vec2 |
| `diarize` | `diarize.py` | `audio.wav`, `owner.wav`*, `aligned.json` | `diarization.json`, `utterances.json` | pyannote |
| `identify` | `identify.py` | `diarization.json`, `utterances.json`, `vision.json` | `identities.json` y filas `Speaker` | — |
| `correct` | `correct.py` | `utterances.json` | `corrected.json` | llama-server |
| `analyze` | `analyze.py` | `corrected.json`, `vision.json`, `probe.json` | `analysis.json` (`analysis.partial.json`) | llama-server |
| `publish` | `worker._publish` | todo lo anterior | carpeta final, `Segment`, `Keyframe`, FTS | — |

\* `owner.wav` solo existe si el usuario indica en qué pista está su micrófono.

Formas clave:
- `utterances.json` / `corrected.json`: `[{start, end, speaker, text, original_text?, corrections?}]`.
  `speaker` es la etiqueta de pyannote (`SPEAKER_00`), no un nombre.
- `diarization.json`: `{turns, speaking_time, embeddings: {label: [float]}, owner}`.
- `analysis.json`: sigue `FINAL_SCHEMA` de `prompts.py`. Las claves están en español, y la web y
  `export.py` dependen de ellas.

## Reglas del worker

- **Reanudación:** si existe `<fase>.done`, la fase se salta. Al arrancar, los trabajos `running`
  vuelven a `queued`. Las fases largas (`vision`, `analyze`) guardan un `*.partial.json` para continuar
  donde se quedaron.
- **Repetir fases:** `options["redo"] = [...]` borra esas marcas antes de ejecutar. Es lo que usa
  `POST /api/videos/{id}/regenerate` (`correct`, `analyze`, `publish`).
- **GPU:** antes de una fase de `GPU_TORCH_STAGES` (asr, align, diarize) se llama a `llm.stop()`.
  Después de las demás se llama a `free_gpu()`. Cada fase con torch descarga su modelo al acabar (`del`
  + `free_gpu()`). Las fases que usan el LLM llaman a `llm.start()`, que no hace nada si ya está
  arrancado.
- **Progreso:** `ctx.report(frac_fase, mensaje)` en el rango 0..1 de la fase. El worker lo convierte en
  progreso global con los pesos de `STAGES` y limita la frecuencia de escritura en la BD. La web lo
  recibe por SSE.
- **Cancelación:** llama a `ctx.check_cancel()` dentro de los bucles largos. Lanza `Cancelled`.
- **`ctx.speaker_names`** (etiqueta → nombre visible) se rellena después de `identify`, y también al
  reanudar. Úsalo en las fases posteriores en lugar de leer `Speaker` tú mismo.
- **Publicación:** el vídeo se mueve o se copia una sola vez (`options.file_mode` o
  `Settings.file_mode`). Si se regenera, se reutiliza la carpeta existente. `_cleanup` borra los wav y
  los fotogramas, pero conserva los JSON para poder regenerar sin repetir ASR ni diarización.

## Añadir o cambiar una fase

1. Crea `pipeline/<fase>.py` con `run(ctx, ...)`. Usa `ctx.load`/`ctx.save` y llama a `ctx.report` y
   a `ctx.check_cancel`.
2. Añade `(clave, etiqueta en español, peso)` a `STAGES` en su posición. Reajusta los pesos para que
   sumen aproximadamente 1. Añade el caso en `Worker._run_stage`. Si carga un modelo torch, añade la
   clave a `GPU_TORCH_STAGES`.
3. Si cambia el formato de un JSON intermedio, ten en cuenta que en `data/work/` puede haber trabajos
   a medias con el formato anterior. Haz que `load` tolere su ausencia (`default`), o borra el `.done`
   afectado.
4. Pon la lógica pura (sin modelos) en funciones aparte y pruébala en `tests/test_logic.py`.

## Prueba de punta a punta

Los vídeos sintéticos están en `samples/videos-prueba/`, que no se versiona:
- `reunion_prueba.mp4`: dos voces y los nombres en pantalla. Sirve para probar la identificación por
  pantalla.
- `incidencia_pedidos.mp4`: las mismas voces, sin nombres. Tras confirmar los hablantes del primero,
  sirve para probar la identificación por voz (usa `skip_vision`).

Las dos voces son la misma voz TTS con el tono cambiado, así que en vídeos reales la similitud de voz
será menor.

```bash
# API en marcha en :8770. Cuerpo en fichero para evitar problemas de UTF-8 en Windows.
echo '{"path":"C:\\...\\reunion_prueba.mp4","profile_id":null,"options":{"file_mode":"copy"}}' > job.json
curl -s -X POST localhost:8770/api/jobs -H 'Content-Type: application/json' --data-binary @job.json
curl -s localhost:8770/api/jobs        # estado / progreso / error (traceback en "error")
```

Con un vídeo de unos 2 minutos tarda 1–2 min. El primer uso de Whisper tras instalar puede tardar ~90 s
más por la compilación JIT de CUDA, y solo ocurre una vez. Los errores del LLM se registran en
`data/llama-server.log`.
