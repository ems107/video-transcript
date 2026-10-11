---
titulo: Problemas frecuentes
seccion: Ayuda
orden: 50
claves: problemas, errores, preguntas, mal, no funciona, faq
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
