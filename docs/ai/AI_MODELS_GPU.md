# Modelos, GPU y dependencias de IA

## Equipo de destino

- GPU: RTX 5070 Ti, 16 GB, arquitectura Blackwell (`sm_120`). Driver 591.74 (CUDA 13.1).
- CPU y RAM: Ryzen 9 5950X, 64 GB. Sistema: Windows 10.
- Blackwell **exige PyTorch con CUDA 12.8 o posterior** (`cu128`). Las ruedas `cu121`/`cu124` no
  tienen kernels `sm_120` y fallan en ejecución. `torch`, `torchaudio` y `torchvision` están fijados en
  `backend/pyproject.toml` contra el índice `pytorch-cu128`. Si los actualizas, hazlo los tres a la vez
  y comprueba que `whisperx` y `pyannote-audio` los aceptan.

## Modelos

| Uso | Modelo | Dónde | Licencia |
|---|---|---|---|
| ASR | `Systran/faster-whisper-large-v3` (float16, beam 5) | `models/hf/` (caché de HF) | MIT |
| Alineamiento | `jonatasgrosman/wav2vec2-large-xlsr-53-spanish` | `models/hf/` | Apache-2.0 |
| VAD | pyannote, incluido en whisperx | paquete | MIT |
| Diarización + huellas de voz | `pyannote/speaker-diarization-community-1` | `models/pyannote-community-1/` (carpeta local) | CC-BY-4.0, con acceso condicionado |
| Visión + texto | `unsloth/Qwen3.6-35B-A3B-GGUF` UD-Q4_K_XL + `mmproj-F16` | `models/llm/Qwen3.6-35B-A3B.gguf`, `models/llm/mmproj-Qwen3.6-35B-A3B.gguf` | Apache-2.0 |
| Servidor del LLM | llama.cpp `llama-server.exe` (build `win-cuda-13.4`) | `models/llama.cpp/` | MIT |

`scripts/download_models.py --only <partes>` descarga cada pieza. Las partes son `llama`, `llm`,
`whisper`, `align`, `nltk` y `diarization`. La parte `diarization` pide el token de HF con `getpass`
o lo toma de la variable de entorno `HF_TOKEN`, y **nunca lo guarda**. Si das esta instrucción, el
usuario debe ejecutarla en su propia terminal, y nunca debe pegar el token en el chat.

## Modo sin conexión

`backend/app/env.py` fija `HF_HOME=models/hf`, `NLTK_DATA=models/nltk_data`, `HF_HUB_OFFLINE=1` y
`TRANSFORMERS_OFFLINE=1`, y desactiva la telemetría. Tiene que importarse **antes** que cualquier
librería de IA: es la primera línea de `main.py`. Si un script nuevo usa estos modelos, importa
`app.env` primero. Si no lo haces, intentará conectarse a internet o buscará los modelos en
`~/.cache`.

## Presupuesto de VRAM (16 GB)

- Solo hay **un modelo grande cargado a la vez**. El worker para llama-server antes de asr, align y
  diarize, y cada fase con torch libera su modelo al terminar (ver `AI_PIPELINE.md`).
- Con Qwen3.6-35B-A3B y `-c 65536`, la caché KV en `q8_0` y `--n-cpu-moe 24`, la GPU queda cerca del
  límite. Con `--n-cpu-moe 20` llegaba a 15,6/16 GB y se subió a 24. Si aumentas el contexto o cargas
  más capas en la GPU, comprueba el uso con `nvidia-smi` durante la fase `vision`.
- Los fotogramas van a 2560 px (`frame_max_width`), unos 3900 tokens de imagen cada uno, sin límites de
  tokens en llama-server (`llm_image_min_tokens`/`llm_image_max_tokens` = 0). Midiendo con fotogramas
  4K, 2560 px lee bien todos los nombres pequeños y tarda ~14,5 s por fotograma frente a ~9 s a 1600 px.

## llama-server (`backend/app/llm.py`)

**Muestreo** (`Settings.llm_*`): el que recomienda Qwen para Qwen3.6 sin «modo razonamiento»:
temperatura 0,7, top_p 0,8, top_k 20, min_p 0 y presence_penalty 1,5. Antes se usaba temperatura 0,2 sin
penalización, y el modelo entraba en bucles repitiendo un elemento de una lista hasta agotar los tokens
(el resumen o el aprendizaje fallaban o se llenaban de copias). Medido con el vídeo de 37 min y dos
regeneraciones: el aprendizaje pasó de 31 datos repetidos a ninguno, sin respuestas no válidas ni
mezcla de idiomas (la ficha avisa de que una penalización alta puede provocarla). No bajes la
temperatura ni quites la penalización sin volver a medir. `config.OLD_DEFAULTS` sustituye el 0,2 que
quedó guardado en el `settings.json` de versiones anteriores.

- Opciones: `-ngl 999 --n-cpu-moe N -c 65536 -np 1 -fa on --jinja --cache-type-k/v q8_0 --mmproj ...`,
  escuchando en `127.0.0.1:<llm_port>` (8091). El log se guarda en `data/llama-server.log`.
- `chat_json(system, user, schema)` usa `response_format: json_schema`, por lo que la salida siempre se
  ajusta al esquema. Usa `chat_template_kwargs.enable_thinking = false`: sin razonamiento, para una
  salida directa y más rápida. Reintenta 2 veces. Con `thinking=True` activa el razonamiento con el
  muestreo `llm.THINKING_SAMPLING` (temperatura 0,6, top_p 0,95, top_k 20): la gramática del esquema se
  aplica a la respuesta, no a lo que piensa, y `max_tokens` incluye lo pensado (unos 24 000 caracteres para un
  bloque de 25 min). Solo lo usa `followups_store.mentions`, donde se midió que hace falta.
- Las imágenes se envían como `image_part(path)`, en base64 JPEG dentro del contenido del usuario.
- Para cambiar de modelo GGUF hay que actualizar `download_models.py` (repositorio y fichero), las rutas
  en `config.py`, las etiquetas de `CHECK_LABELS` en `frontend/src/App.tsx` y las tablas de licencias
  del README.

## Detalles conocidos de las librerías

- **whisperx 3.8.6:** `load_model(..., vad_method="pyannote", asr_options={"initial_prompt": ...})`.
  `transcribe` acepta `progress_callback`. Para Whisper, el prompt inicial está limitado a 550
  caracteres (`PROMPT_MAX_CHARS`); con más contexto alucina en los silencios. `drop_prompt_echoes`
  elimina los segmentos que repiten el prompt.
- **pyannote.audio 4.x:** `Pipeline.from_pretrained(<carpeta local>)` devuelve un `DiarizeOutput`.
  Se usa `exclusive_speaker_diarization` para los turnos (sin solapes) y `speaker_embeddings` en el
  orden de `speaker_diarization.labels()`. El audio se pasa ya decodificado
  (`{"waveform", "sample_rate"}`), así que torchcodec no se usa y su aviso se silencia en `env.py`.
- **Huellas por tramo** (fase `voices`): `Model.from_pretrained(<carpeta>/embedding)` e
  `Inference(window="whole")` con `crop`. Usa poca VRAM y se libera al terminar. En un vídeo de 37 min
  calcula unas 3300 ventanas en unos 40 s.
- **Primer uso de CUDA:** la primera transcripción tras instalar tarda unos 90 s más por la compilación
  JIT de los kernels. Solo pasa una vez y no indica ningún error.
- **SQLModel 0.0.47:** los campos de fecha deben anotarse como `NaiveDatetime`. Con `datetime` a
  secas, la validación los rechaza.

## Cambiar o añadir un modelo

1. Debe ser libre, gratuito y funcionar en local. Comprueba que cabe en 16 GB **sin** otro modelo
   cargado, o que puede pasar parte de su carga a la RAM.
2. Añade su descarga a `download_models.py`, guardándolo en `models/`.
3. Añade su comprobación en `/api/status` (`main.py:status`) y su etiqueta en `App.tsx`, para que la
   web avise si falta.
4. Actualiza las tablas de licencias del README y el CHANGELOG.
