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

## Su voz

Al aplicar la [revisión de un vídeo](ayuda:revision), la app guarda la voz de cada persona confirmada en
él: una **huella** para reconocerla (una lista de números que describe cómo suena, no un audio) y una
**muestra**, sus mejores tramos unidos en un audio corto. La lista de **Personas** muestra cuántas huellas
tiene cada una; con más vídeos, la reconoce mejor.

- La huella se calcula con las frases de esa persona **tal como quedan después de tus arreglos** de quién
  habla. Si una persona estaba mezclada con otra, ninguna de las dos se queda con la voz de la otra.
- Si habla menos de {{v:voz_huella_minimo}} s limpios en el vídeo, no se guarda nada: sería poco fiable.
- Si la huella no se parece a la de sus otros vídeos (menos de {{v:voice_match_threshold}}), queda como
  **dudosa** y no se usa hasta que decidas en la revisión: **Es su voz: guardarla** o **Descartarla**.
  Suele significar que el hablante estaba mal asignado.

La tarjeta **Su voz** de la ficha tiene sus 3 mejores muestras para **escucharla** y comprobar de oído que
es ella. Cada muestra dura entre {{v:voz_huella_minimo}} y {{v:voz_muestra_maximo}} s (se buscan unos
{{v:voz_muestra_objetivo}}), con los tramos que más se parecen a su huella, sacados del vídeo original a su
calidad. Se guardan solo en tu equipo, en los datos de la app (`data/voces/`), no en la carpeta del vídeo:
son datos biométricos de otras personas.

Si alguna voz se guardó por error, **Olvidar voz** borra sus huellas y sus muestras. **Recalcular las
voces** (arriba en **Personas**) vuelve a calcular las de todos los vídeos revisados que conservan su
archivo de vídeo: útil para los vídeos de antes de esta versión, cuyas huellas se guardaban al confirmar,
sin tener en cuenta tus arreglos.

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
