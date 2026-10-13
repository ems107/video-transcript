---
titulo: Ajustes
seccion: Otros
orden: 31
claves: ajustes, configuración, carpeta, mover, copiar, umbral, voz, fotogramas, memoria, gpu, registros, logs
---
**Ajustes** reúne la configuración de la app. Los valores que ves en esta ayuda son los de tu app.

![Los ajustes](captura:ajustes)

| Ajuste | Para qué sirve | Valor actual |
|---|---|---|
| **Carpeta de vídeos analizados** | Dónde se publica cada vídeo, en una subcarpeta «AAAA-MM-DD - Título». | {{v:analyzed_dir}} |
| **Vídeo original** | Moverlo a su carpeta de resultados o copiarlo (el original no se toca). | {{v:file_mode}} |
| **Tu nombre** | Se usa para identificarte cuando hay una pista separada de tu micrófono. | {{v:owner_name}} |
| **Umbral para proponer persona por voz** | Desde qué parecido de voz (de 0 a 1) se propone a una persona conocida. Más bajo, más propuestas y más errores. | {{v:voice_match_threshold}} |
| **Umbral de alta confianza por voz** | Desde qué parecido se considera reconocida con seguridad: lo que dice se le atribuye sin esperar a que confirmes. | {{v:voice_auto_threshold}} |
| **Máximo de fotogramas analizados por vídeo** | Límite de fotogramas que lee la IA en un vídeo. Cada uno tarda unos {{v:ritmo_vision}} s. | {{v:max_frames}} |
| **Analizar al menos un fotograma cada (s)** | Aunque la pantalla no cambie, se toma un fotograma cada este tiempo. | {{v:frame_max_interval}} |
| **Minutos por bloque de resumen** | Los vídeos largos se resumen por bloques de esta duración y luego se unen. | {{v:chunk_minutes}} |
| **Lote de Whisper** | Bájalo si la transcripción falla por falta de memoria de la tarjeta gráfica. | {{v:whisper_batch_size}} |
| **Capas MoE del LLM en CPU** | Cuánto del modelo de IA va a la memoria del ordenador en vez de la tarjeta gráfica. Súbelo si falla por falta de memoria; bájalo para ir más rápido. | {{v:llm_n_cpu_moe}} |
| **Contexto del LLM (tokens)** | Cuánto texto puede leer la IA a la vez. | {{v:llm_ctx}} |
| **Detalle de los registros** | Normal registra lo que pasa en la app; Detallado añade cada consulta de la web y el progreso de las fases, para buscar un fallo. Se aplica al guardar. Ver [Registros](ayuda:problemas#registros-logs). | {{v:log_level}} |
| **Días que se guardan los registros** | Los registros más antiguos se borran solos. | {{v:log_keep_days}} |

**Abrir carpeta de registros** abre la carpeta con un fichero por día ([Registros](ayuda:problemas#registros-logs)).

Las rutas de los modelos solo hay que tocarlas si los mueves de sitio.

:::tecnico Ajustes que no están en la pantalla
Se guardan en `data/settings.json` y se pueden cambiar a mano con la app cerrada:
- `frame_max_width` ({{v:frame_max_width}} px): ancho al que se leen los fotogramas. Ver
  [Decisiones](ayuda:decisiones#resolucion-de-la-pantalla).
- `llm_temperature` ({{v:llm_temperature}}), `llm_top_p` ({{v:llm_top_p}}), `llm_top_k` ({{v:llm_top_k}}),
  `llm_min_p` ({{v:llm_min_p}}) y `llm_presence_penalty` ({{v:llm_presence_penalty}}): cómo elige las
  palabras la IA. Ver [Decisiones](ayuda:decisiones#ajustes-de-la-ia).
- `llm_image_min_tokens` y `llm_image_max_tokens` ({{v:llm_image_min_tokens}} y
  {{v:llm_image_max_tokens}}; 0 significa «lo que indique el modelo»).
- `frame_sample_every`, `frame_min_interval` y `frame_hash_distance`: cómo se detectan los cambios de
  escena para elegir fotogramas.
:::
