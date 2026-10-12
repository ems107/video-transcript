---
titulo: Problemas frecuentes
seccion: Ayuda
orden: 50
claves: problemas, errores, preguntas, mal, no funciona, faq, registros, logs, consola
---
## Un hablante tiene el nombre equivocado
En el panel **Hablantes**, pulsa **Cambiar** y elige la persona correcta. Si el resumen ya usaba el nombre
equivocado, [regenera el análisis](ayuda:regenerar). Ver [Hablantes](ayuda:hablantes#confirmar-y-cambiar).

## Una frase está asignada a quien no es
Pulsa el nombre del hablante en esa línea de la transcripción y elige quién habla, en la línea entera o en
parte de ella. Ver [Cambiar quién habla](ayuda:hablantes#cambiar-quien-habla).

## Faltan hablantes o hay dos personas juntas
Si la app avisa de **dos voces** en un hablante, pulsa **Revisar**. Si no, [regenera el análisis
completo](ayuda:regenerar) indicando el número mínimo y máximo de hablantes.

## Una persona aparece dos veces
En **Personas** aparecerá el aviso de posibles duplicados: pulsa **Fusionar**. También puedes hacerlo desde
la ficha con **Fusionar con otra persona**. Ver [Personas](ayuda:personas#duplicados-y-fusion).

## Una palabra se transcribe mal siempre (un nombre, un producto)
Añádela al [glosario del perfil](ayuda:perfiles#glosario), con las formas mal oídas como variantes, y
regenera el análisis.

## El resumen dice algo que no es cierto
Escribe una [corrección](ayuda:correcciones) como un hecho sobre el vídeo y regenera.

## El resumen o el aprendizaje fallan
Si el análisis queda en «Error», mira el mensaje en **Detalles** de la [cola](ayuda:cola). Si la IA
devolvió una respuesta no válida, se guarda en `data/llm_failures/`: es lo que hace falta para
diagnosticarlo. Si falla solo el aprendizaje, el vídeo se publica igual.

## Error de memoria de la tarjeta gráfica
Cierra otros programas que usen la tarjeta (juegos, editores de vídeo) y vuelve a intentarlo. Si sigue
fallando, en [Ajustes](ayuda:ajustes) baja el **Lote de Whisper** (si falla al transcribir) o sube las
**Capas MoE del LLM en CPU** (si falla al leer la pantalla o al resumir).

## La web se queda en «Cargando…» o en blanco
Recarga la página. Si acabas de actualizar la app, reiníciala con `.\run.ps1 -Rebuild`: la web y el
servidor tienen que ser de la misma versión.

## La app reconoce mal a alguien por la voz
Probablemente se confirmó una vez al hablante equivocado y su huella quedó mal. En **Personas**, pulsa
**Olvidar voz** en esa persona y vuelve a confirmarla en un vídeo donde hable claramente.

## Registros (logs)
La app guarda lo que pasa en un fichero por día, en la carpeta `logs` de sus datos (`data/logs/2026-10-13.log`).
Lo abres con **Abrir carpeta de registros** en [Ajustes](ayuda:ajustes). Es lo mismo que sale en la
consola de `run.ps1`, con la fecha y la hora de cada línea, así que no hace falta copiar la consola.

- Cada línea dice cuándo pasó, si fue normal (INFO), un fallo del que la app se recuperó (WARNING) o un
  error (ERROR), qué parte de la app lo registró y, si es de un análisis, de qué trabajo, vídeo y fase.
  Busca «vídeo 3» para ver todo lo que pasó con ese vídeo.
- **No contiene lo que se dice en tus vídeos** ni tus notas, correcciones o datos de personas: solo
  números de vídeo y de persona, fases, tiempos y recuentos. Puedes pasárselo a quien te ayude a encontrar
  un fallo.
- Se guardan los últimos {{v:log_keep_days}} días; los más antiguos se borran solos.
- Para buscar un fallo concreto, pon **Detalle de los registros** en **Detallado**, repite lo que falla y
  vuelve a Normal: el detallado añade cada consulta de la web y crece deprisa.
- El modelo de IA escribe su propio registro en `data/llama-server.log`, útil si falla al arrancar.
