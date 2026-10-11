---
titulo: Modelos y equipo
seccion: Por dentro
orden: 42
claves: modelos, gpu, memoria, whisper, pyannote, qwen, llama, requisitos, equipo, privacidad
---
La app usa cuatro modelos de IA, todos **libres, gratuitos y locales**. Nada sale de tu equipo.

| Para qué | Modelo |
|---|---|
| Transcribir la voz | **Whisper large-v3** |
| Saber cuándo se dice cada palabra | **wav2vec2** en español |
| Separar las voces y reconocerlas | **pyannote community-1** |
| Leer la pantalla, resumir y aprender | **Qwen3.6-35B-A3B** |

## Por qué este modelo de IA

Qwen3.6-35B-A3B (abril de 2026) **ve imágenes**, que es necesario para leer la pantalla, y es de tipo
**«mezcla de expertos»**. Tiene 35.000 millones de parámetros, pero para cada palabra solo usa unos 3.000
millones. Por eso cabe en el equipo y va rápido, aunque no quepa entero en la tarjeta gráfica: la parte que
no se usa en cada momento espera en la memoria del ordenador sin coste.

Un modelo «denso» más nuevo y más pequeño en total, como Qwen3.8-27B, usaría sus 27.000 millones en cada
palabra. La parte que no cupiera en la tarjeta la tendría que calcular el procesador entero, palabra tras
palabra, y leer los fotogramas de un vídeo pasaría de minutos a horas.

## Una sola tarjeta gráfica

Con una tarjeta de 16 GB solo cabe un modelo grande a la vez. Por eso los vídeos se procesan de uno en uno
y las fases se turnan: mientras se transcribe no se lee la pantalla, y al revés.

:::tecnico Detalles
- **Whisper large-v3** con faster-whisper y WhisperX; detección de voz con pyannote.
- **wav2vec2:** `jonatasgrosman/wav2vec2-large-xlsr-53-spanish`, para alinear palabras.
- **pyannote community-1:** separación de voces (VBx) y su modelo de huellas, que también usa la
  comprobación por la voz. Se carga desde una carpeta local, sin conexión.
- **Qwen3.6-35B-A3B** cuantizado a 4 bits (Unsloth UD-Q4_K_XL, 22 GB) con su proyector de visión, servido
  por llama.cpp (`llama-server`) en el puerto {{v:llm_port}}. Contexto de {{v:llm_ctx}} tokens y
  {{v:llm_n_cpu_moe}} capas de expertos en la CPU para no pasar de 16 GB.
- Comparado en octubre de 2026: Gemma 4 26B-A4B es de la misma categoría (mezcla de expertos con imagen) y
  sería una alternativa a probar. Los modelos más grandes publicados después necesitan 100 GB o más.
:::
