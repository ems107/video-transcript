---
titulo: Personas
seccion: Conocimiento
orden: 22
claves: persona, ficha, otros nombres, alias, apodo, voz, huella, duplicados, fusionar, tareas
---
Cada persona es **una sola en toda la app**, aunque aparezca en varios perfiles y vídeos. La app la
reconoce por su voz y por su nombre, y va completando su ficha con lo que aceptas.

![La ficha de una persona](captura:persona-ficha)

## La ficha

- **Datos manuales:** nombre, rol, **otros nombres** (apodos, cómo aparece en la videollamada) y notas.
  Son tuyos: la IA nunca los modifica. Los otros nombres ayudan a reconocerla en pantalla y llegan a la
  IA («también llamado…») y a Whisper.
- **Aprendido de los vídeos:** lo aceptado, por categorías.
- **Tareas asignadas:** las tareas de los resúmenes en las que es responsable, con su vídeo.
- **Vídeos:** en cuáles aparece, cuánto ha hablado y si está confirmada.
- Pestañas **Propuestas** e **[Historial](ayuda:historial)**.

## Voz

La lista de **Personas** muestra cuántas **muestras de voz** tiene cada una: se guarda una al confirmarla
como hablante en un vídeo. Con más muestras, la reconoce mejor. Si alguna se guardó por error (se
confirmó al hablante equivocado), **Olvidar voz** las borra.

## Duplicados y fusión

Si dos personas parecen la misma (nombres parecidos o voces muy similares), **Personas** muestra un
aviso con dos opciones:
- **Fusionar:** une las dos (voz, vídeos, perfiles, lo aprendido y sus nombres). Se conserva la que tiene
  más información y el otro nombre queda como «otro nombre».
- **No son la misma:** el aviso no vuelve a salir para esa pareja.

En la ficha también puedes **Fusionar con otra persona** en cualquier momento.

:::tecnico Cómo se detectan los duplicados
Por nombre: uno contenido en otro o muy parecido. Por voz: similitud alta entre las medias de sus huellas.
Al fusionar se conserva la persona con más muestras de voz, vídeos y datos aprendidos, y se reescriben los
documentos de los vídeos afectados con el nombre que queda. La fusión crea una versión en el historial de
la persona que se conserva.
:::
