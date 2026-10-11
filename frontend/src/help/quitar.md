---
titulo: Quitar un vídeo
seccion: Cada vídeo
orden: 14
claves: quitar, borrar, eliminar, recuperar, copia de recuperación, datos
---
**Quitar** saca el vídeo de la app. Una ventana muestra las rutas afectadas y te deja elegir qué se
borra del disco.

![La ventana de quitar](captura:quitar)

Siempre desaparecen de la app su análisis, sus hablantes y sus propuestas pendientes. Además, puedes
marcar:

| Opción | Qué hace |
|---|---|
| **Borrar los ficheros del análisis** | Transcripción, resumen, fotogramas y datos de trabajo. Solo se borran los ficheros que creó la app; la carpeta se elimina si queda vacía. Si la app copió el vídeo, la copia se va con la carpeta; si lo movió, vuelve a su ubicación original. |
| **Borrar el vídeo** | El archivo de vídeo que usa la app. No se puede deshacer. |
| **Borrar también el vídeo original** | Solo aparece si la app trabajó con una copia. |
| **Olvidar lo aprendido de este vídeo** | Retira el conocimiento aceptado que solo venía de este vídeo y las huellas de voz guardadas al confirmar sus hablantes. |

**Sin marcar nada**, el vídeo desaparece de la app pero todos sus ficheros se conservan, incluida la copia
de recuperación.

Si el vídeo está en algún [seguimiento](ayuda:seguimientos), la ventana pregunta además si se rehace su
estado sin él o se deja como está (desactualizado).

## Copia de recuperación

Cada carpeta publicada lleva una subcarpeta `datos/` con todo lo necesario para recuperar el análisis en
el futuro: el estado de los hablantes con sus huellas de voz, tus correcciones y los datos intermedios
del análisis. Por ahora la app no tiene una función para importarla; está pensada para poder hacerlo más
adelante sin volver a analizar.

:::tecnico Qué contiene `datos/`
`video.json` (versión de la app, metadatos, perfil, hablantes con persona, confirmación, huella y pistas,
y las correcciones) y copias de los JSON de trabajo: lectura de la pantalla (original y unificada),
nombres, transcripción, alineado, intervenciones, separación de voces, identidades, corrección, análisis y
propuestas. Se escribe al publicar y al quitar el vídeo sin borrar ficheros.
:::
