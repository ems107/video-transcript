# Historial de cambios

Todos los cambios relevantes de cada versión se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[versionado semántico](https://semver.org/lang/es/). Cómo añadir entradas y publicar una versión:
[docs/VERSIONADO.md](docs/VERSIONADO.md).

## [Sin publicar]

### Corregido

- Al añadir un vídeo ya analizado a un seguimiento, o al quitarlo, su `resumen.md` ahora muestra o quita
  la línea **Seguimientos** con el enlace.
- Si la IA se queda sin margen al buscar en un vídeo qué pasa con los puntos de un seguimiento, la app
  repite esa parte en dos mitades en vez de dejar el seguimiento desactualizado.
- El resumen ya no cuenta tus correcciones como algo que se dijo en la reunión («X aclara que…»).
- El análisis es más fiel a la grabación:
  - no inventa plazos que nadie dice;
  - no mete en el resumen datos de las fichas de las personas (edad, estudios…) que no se dicen en el
    vídeo;
  - no repite el mismo asunto como tarea y como pendiente.
- Una propuesta de conocimiento (o una nueva confirmación de algo ya sabido) solo vale si sus cifras se
  dicen de verdad cerca de su momento: «Tiene 27 años» ya no se confirma con un momento en que solo se
  habla de «años».
- Al cambiar quién habla, las líneas seguidas de la misma persona se unen en una sola, en vez de quedar
  partidas en trozos («esté bien y» / «que nos» / …).

## [1.5.0] - 2026-10-12

La app sigue un tema a lo largo de varios vídeos.

### Añadido

- **Seguimientos** (menú **Seguimientos**): reúnen los vídeos de un mismo tema y llevan su estado:
  - un resumen de cómo ha evolucionado;
  - las tareas, decisiones y dudas, cada una con su recorrido («aparece el día 4 → hecha el día 5») y
    enlaces al vídeo en cada momento;
  - lo que aportó cada vídeo.
- Al encolar un vídeo se pueden elegir sus seguimientos: el análisis tiene en cuenta lo anterior del tema
  y, al terminar, la IA actualiza el estado. Un vídeo ya analizado se añade desde su página.
- Cada avance o cierre lleva **la frase del vídeo que lo dice**, comprobada contra la transcripción. Si la IA
  cree que algo se cerró pero no encuentra la frase, lo muestra como «¿hecha?» con un botón **Confirmar**.
  Para encontrarlo usa el modo razonamiento del modelo: actualizar un seguimiento tarda unos 2 minutos más
  por cada 25 minutos de vídeo.
- Las tareas, decisiones y dudas nuevas del seguimiento son las del análisis del vídeo: no cambian de una
  ejecución a otra.
- Puedes cambiar el estado de cualquier punto, editarlo, borrarlo o añadir uno a mano, y editar el resumen:
  la IA ya no lo cambia. Cada cambio guarda una versión que se puede restaurar.
- Al quitar o regenerar un vídeo de un seguimiento, la app pregunta si rehace su estado. Si no, lo marca
  como desactualizado, con un botón para rehacerlo.
- Los seguimientos se pueden archivar y se publican en su propia carpeta `Seguimiento - Nombre/`.
- Nueva página de ayuda «Seguimientos».
- Los términos que solo se ven en pantalla ya no se filtran por una regla fija: la IA razona si tienen que
  ver con el vídeo (con lo que trata y con dónde, cuándo y cuánto aparecen). Si no está claro, se proponen
  marcados como **dudosos**, con el motivo, y «Aceptar todas» no los incluye.
- Los pendientes del resumen llevan su momento del vídeo, con enlace.

### Corregido

- El momento de las tareas y decisiones a veces salía con el texto de la tarea o con una fecha: ahora
  siempre es una marca de tiempo.
- El plazo de una tarea se escribe tal como se dice («el lunes»), sin convertirlo en una fecha.
- La corrección de términos cambiaba palabras que ya contenían el término bien escrito (por ejemplo,
  «onmicrosoft.com» por «onMicrosoft»).
- Los nombres de los participantes leídos en pantalla ya no se proponen como términos del perfil.

## [1.4.0] - 2026-10-11

La app explica cómo se usa y cómo funciona por dentro.

### Añadido

- **Ayuda integrada** en la propia app (menú **Ayuda**), como una wiki:
  - guía de cada pantalla: analizar, hablantes, correcciones, regenerar, perfiles, propuestas, personas…;
  - **cómo funciona** cada fase del análisis y **las decisiones de diseño**, con su motivo, sus
    consecuencias y si se pueden cambiar;
  - **detalles técnicos** aparte, plegados y con otro estilo, para quien quiera profundizar;
  - los umbrales y ajustes que se citan son los de tu app en ese momento;
  - buscador, capturas de pantalla, problemas frecuentes, glosario y novedades de cada versión.
- Enlaces «?» desde cada pantalla a su sección de la ayuda.

### Corregido

- El texto de Ajustes indicaba unos 8 s por fotograma; a 2560 px son unos 15 s.

## [1.3.0] - 2026-10-11

Hablantes bien asignados aunque la separación de voces se equivoque.

### Añadido

- **Comprobación de cada tramo por la voz.** Después de separar las voces, la app compara cada tramo de
  1,5 s con la voz de cada hablante:
  - si es claramente de otro, lo reasigna, aunque sea en mitad de una línea (por ejemplo, un saludo
    de otra persona);
  - si no está claro, lo marca como «dudoso» para que lo revises;
  - avisa si un hablante parece juntar dos voces distintas.

  En un vídeo de 37 min tarda unos 40 s.
- **Arreglar el hablante a mano**, de una línea, de varias o de parte de una línea. Se guarda por tiempo
  («de tal momento a tal momento habla esta persona»), se ve al momento en la transcripción y se
  mantiene en cualquier regeneración, también en la completa.
- Al regenerar el análisis completo se puede indicar el número mínimo y máximo de hablantes.

### Corregido

- **Términos del perfil sin ruido del escritorio.** Se proponían programas que solo se veían en la barra
  de tareas o en otras pestañas (Trello, Jira…). Ahora un término tiene que oírse en la conversación o
  formar parte del contenido de la pantalla.
- Las distintas formas de un mismo nombre («Bárymont», «Gestibarymont», «Grupo Bárymont») se proponen
  como un solo término con sus otras formas.
- Las secciones del resumen que se proponen para un perfil sirven para cualquier vídeo de ese tipo, no
  solo para el vídeo del que salen.
- Cuando un hablante recibe un nombre por el contexto, el resumen ya no lo sigue llamando «Hablante N».
- La IA podía entrar en un bucle repitiendo un elemento (por ejemplo, el mismo apodo decenas de veces)
  hasta cortarse la respuesta, y el resumen o el aprendizaje fallaban. Ahora todas sus listas tienen un
  máximo de elementos.

### Cambiado

- **La IA se usa con los ajustes que recomienda el fabricante del modelo** (Qwen): más variación y una
  penalización que evita repetir. Con los anteriores podía entrar en bucles repitiendo lo mismo. En un
  vídeo real, el aprendizaje pasó de 31 datos repetidos a ninguno. Se aplica también a quien ya tenía
  guardada la configuración anterior.
- Se proponen todos los datos que se encuentran de cada persona. Antes se quedaban en 8 por vídeo y se
  perdían datos buenos. Los demás límites por vídeo también suben.
- «Volver a identificar a los hablantes» también vuelve a comprobar las voces. Ahora necesita el archivo
  de vídeo, para volver a extraer el audio.
- Las propuestas de nombre por pantalla tienen en cuenta las reasignaciones por la voz. Un fotograma que
  cae justo en un cambio de turno se asigna a quien empieza a hablar.
- La huella de voz de cada hablante se calcula solo con sus intervenciones largas y claras, así que al
  confirmarlo se guarda una voz más limpia.

### Notas para actualizar

- Reinicia la app con `.
un.ps1 -Rebuild`. La base de datos se actualiza sola al arrancar: se crea la
  tabla de cambios manuales y se añade la marca de voz a la transcripción.
- La comprobación por la voz se aplica a los vídeos que se analicen a partir de ahora. Para uno ya
  analizado, usa «Regenerar análisis» → «Volver a identificar a los hablantes».

## [1.2.0] - 2026-10-11

Corregir y mejorar un vídeo ya analizado sin perder lo que ya has revisado.

### Añadido

- **Correcciones del vídeo.** En la página de cada vídeo puedes escribir lo que el análisis ha
  interpretado mal, como un hecho («X es quien presenta, no Y»). Al regenerar, la IA las recibe como hechos
  que prevalecen, en el resumen y en el aprendizaje, y nunca las modifica. Cada corrección indica si el
  análisis actual ya la tiene en cuenta («Aplicada») o se aplicará al regenerar («Pendiente»). Se guardan
  también en la copia de recuperación `datos/`.
- **«Regenerar análisis» con opciones.** Una ventana explica qué se repite y qué se conserva, con el
  tiempo estimado. Además del resumen, se puede elegir:
  - volver a identificar a los hablantes (los confirmados no cambian);
  - volver a analizar la pantalla;
  - el análisis completo desde el audio, sin quitar el vídeo. Hay que volver a confirmar a los hablantes,
    pero la app los propone por su voz.
- La app mide cuánto tarda cada fase del análisis en tu equipo, y lo usa para estimar los tiempos.

### Corregido

- Si la IA devuelve una respuesta cortada o no válida, se guarda en `data/llm_failures/` para poder
  diagnosticarla. Una respuesta cortada por el límite de longitud ya no se pide tres veces seguidas.
- La hora de inicio de un trabajo se reinicia al regenerar un vídeo. Antes conservaba la del primer
  análisis.

## [1.1.0] - 2026-10-11

Los perfiles y las personas aprenden de cada vídeo. La IA propone y tú decides.

### Añadido

- **Aprendizaje a partir de los vídeos.** Después de cada análisis, la IA propone:
  - para el perfil: términos del negocio, hechos duraderos (proyectos, clientes, sistemas, procesos,
    siglas) y secciones para el resumen;
  - para las personas: cargo, organización, equipo, responsabilidades, proyectos, conocimientos,
    relaciones y datos personales. Los aprende de lo que dice cada persona y de lo que otros dicen de
    ella.
- **Comprobación de cada propuesta.** Todas indican de qué vídeo y de qué momento salen, con las frases
  reales. Se descarta lo que no aparece en la transcripción o en la pantalla, las palabras comunes y
  los detalles puntuales de una reunión.
- **Página «Propuestas»** con un contador en la barra lateral:
  - cada propuesta se puede aceptar, editar y aceptar, o rechazar, también todas las de un vídeo a la
    vez;
  - lo rechazado no se vuelve a proponer;
  - lo repetido en varios vídeos se marca como «visto en N vídeos».
- **Atribución por hablante.** Lo que dice un hablante se atribuye a su persona cuando está confirmado
  o reconocido por voz con confianza alta. Si no, la propuesta espera a que lo confirmes. Si reasignas
  el hablante, sus datos pasan a la nueva persona.
- **Personas nuevas.** Se proponen las personas mencionadas que aún no existen. Al aceptarlas, se
  crean con sus datos y se añaden al perfil.
- **Crear un perfil a partir de un vídeo.** La IA propone su contenido. También se puede volver a
  aprender de un vídeo, de todos los vídeos de un perfil, u olvidar lo aprendido de un vídeo.
- **Historial de versiones** de perfiles y personas. Cada cambio, manual o aceptado, crea una versión
  con un resumen de lo cambiado, y cualquier versión se puede restaurar.
- **Ficha de persona:**
  - datos manuales;
  - lo aprendido por categorías;
  - tareas que se le han asignado en los vídeos;
  - vídeos en los que aparece, tiempo hablado y última aparición.
- **Personas duplicadas.** Aviso de posibles duplicados por nombre o voz. Se pueden fusionar (voz,
  vídeos, perfiles, lo aprendido y nombres) o marcar como distintas.
- **«Quitar» un vídeo con opciones.** Una ventana muestra las rutas afectadas y permite elegir:
  - borrar los ficheros del análisis (solo los que crea la app; la carpeta se elimina si queda vacía);
  - borrar el vídeo y, si la app trabajó con una copia, también el original;
  - olvidar lo aprendido de ese vídeo, incluidas las huellas de voz.

  Sin marcar nada, el vídeo desaparece de la app pero todos sus ficheros se conservan.
- **Copia de recuperación en cada carpeta publicada** (`datos/`): el estado de los hablantes con sus
  huellas de voz y los datos intermedios del análisis, para poder recuperarlo en el futuro.
- La variable de entorno `VT_DATA_DIR` permite usar otra carpeta de datos.
- Documentación para asistentes de IA: `CLAUDE.md`, guías por tema en `docs/ai/` y reglas por zona
  del código en `.claude/rules/`.

### Cambiado

- **Lo aprendido y aceptado se usa en los análisis siguientes.** Se añade al contexto del resumen y a
  las palabras que orientan a Whisper, siempre después de lo manual, que prevalece. Los términos
  aprendidos nunca corrigen la transcripción sin que el LLM valide cada cambio.
- Las notas de cada persona ahora se usan en el contexto de la IA.
- El contexto de la IA incluye solo las personas del perfil y las que hablan en el vídeo, como máximo
  30.
- Al confirmar a una persona como hablante de un vídeo con perfil, se añade a las personas del perfil.
- Al renombrar una persona, se reescriben los documentos de sus vídeos.
- «Regenerar análisis» también vuelve a proponer lo aprendido del vídeo.

### Corregido

- **La pantalla se analiza con más resolución** (2560 px de ancho como máximo, antes 1600). En una
  grabación 4K, los nombres pequeños se leían bien el 44 % de las veces y ahora el 100 %. El análisis de
  la pantalla tarda alrededor de 1,6 veces más.
- **Un solo nombre por persona en cada vídeo.** El análisis de la pantalla leía el mismo nombre de muchas
  formas («Iosu», «Iker», «Ione»…), y cada una se trataba como una persona distinta. Ahora se agrupan
  las variantes y se elige una sola forma: se tiene en cuenta lo que se oye en la transcripción y las
  personas que ya conoces, y nunca se juntan dos nombres que aparecen a la vez en pantalla.
- **El resumen sabe quién es quién.** Recibe los participantes vistos en pantalla y la identidad probable
  de cada hablante, y nombra a cada persona siempre de la misma forma. Un apodo o un nombre mal
  transcrito solo se atribuye a un participante si el contexto lo deja claro; si no, se escribe tal
  como se oye.
- **Propuesta de nombre por el contexto.** Si la conversación deja claro quién es un hablante (se
  presenta, o le llaman por su nombre y responde), se propone ese nombre con el motivo. Solo se acepta un
  nombre que aparezca en pantalla o se oiga, y nunca se confirma solo. Al confirmarlo, sus apodos se
  guardan como otros nombres de la persona.
- Los otros nombres de cada persona se usan en el contexto del resumen y en las palabras que orientan a
  Whisper.
- **Propuesta de nombre por pantalla más fiable.** Cada nombre se asigna a un solo hablante, el que más
  coincide con él. Un nombre resaltado mientras hablan varias voces (por ejemplo, quien presenta) ya no
  se propone para todas.
- Al quitar un vídeo, sus propuestas pendientes ya no se quedan huérfanas en «Propuestas».
- La web podía quedarse bloqueada («Cargando…») al navegar mucho o con varias pestañas abiertas. Las
  conexiones de eventos en tiempo real de páginas ocultas o ya abandonadas ocupaban el máximo de
  conexiones del navegador.
- Tras actualizar la app, el navegador podía mostrar una página en blanco por usar una versión
  antigua guardada en caché.
- Las duraciones de menos de un minuto se muestran como «<1 min», en lugar de «0 min».
- En pantallas estrechas, la cabecera del vídeo ya no aplasta el título.

### Notas para actualizar

- Solo se añaden tablas nuevas a la base de datos, así que basta con reiniciar la app (`.\run.ps1
  -Rebuild`).
- Los vídeos ya analizados no tienen propuestas. Para obtenerlas, usa «Aprender de nuevo» en el vídeo
  o «Aprender de todos sus vídeos» en el perfil.

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

[Sin publicar]: https://github.com/ems107/video-transcript/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/ems107/video-transcript/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/ems107/video-transcript/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/ems107/video-transcript/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/ems107/video-transcript/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ems107/video-transcript/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/ems107/video-transcript/releases/tag/v1.0.0
