---
titulo: Regenerar el análisis
seccion: Cada vídeo
orden: 13
claves: regenerar, volver a analizar, niveles, hablantes, pantalla, completo, estimación, tiempo
---
**Regenerar análisis** vuelve a hacer el análisis de un vídeo ya procesado con lo que la app sabe ahora:
el perfil, las personas, el glosario, tus correcciones y tus cambios de hablantes. Una ventana explica
qué se repite y qué se conserva antes de empezar.

![La ventana de regenerar](captura:regenerar)

## Niveles

Siempre se repite el **resumen** (título, participantes, tareas, decisiones, pendientes), la
**corrección de términos** con el glosario, las **propuestas de aprendizaje** del vídeo y los
**documentos** de su carpeta. Además, puedes marcar:

| Nivel | Qué añade | Cuándo usarlo |
|---|---|---|
| **Volver a identificar a los hablantes** | Comprueba de nuevo por la voz quién dice cada tramo y recalcula las propuestas de nombre. Necesita el archivo de vídeo. | Después de confirmar personas en otros vídeos, o en vídeos analizados con una versión anterior. |
| **Volver a analizar la pantalla** | Vuelve a elegir y leer los fotogramas y a unificar los nombres vistos. | Si ha mejorado el análisis de imagen en una versión nueva. |
| **Volver a transcribir y separar las voces** | Todo desde el audio: es el análisis completo, sin quitar el vídeo. Puedes indicar el número de hablantes. | Si faltan hablantes, sobran o la transcripción es mala. |

Cada nivel incluye los anteriores: al marcar uno, se marcan los de arriba.

## Qué se conserva

Los hablantes confirmados, las huellas de voz, lo que aceptaste o rechazaste, tus correcciones y tus
cambios manuales de hablantes.

La excepción es el nivel completo: al volver a separar las voces, los hablantes pueden cambiar de número
u orden, así que **hay que volver a confirmarlos**. La app los propondrá por su voz si ya la conoce (las
huellas guardadas se conservan) y **Aceptar propuestas** lo deja en un clic. Tus cambios manuales de
hablantes se mantienen.

## Si el vídeo está en un seguimiento

El análisis nuevo puede cambiar lo que el vídeo aporta a sus [seguimientos](ayuda:seguimientos), así que la
ventana pregunta qué hacer con cada uno:

- **Rehacer el estado**: la IA vuelve a aplicar este vídeo y los posteriores (la ventana dice cuánto
  añade). Lo que cambiaste tú en el seguimiento se conserva.
- **Dejarlo como está**: el estado no cambia y queda marcado como desactualizado, para rehacerlo cuando
  quieras.

## Estimaciones

El botón muestra cuánto tardará, por ejemplo «Regenerar (≈ 5 min)». La app mide lo que tarda cada fase
en tu equipo y lo usa para estimar; mientras no tenga historial, usa tiempos medidos con grabaciones
reales.

:::tecnico Cómo se estima
Cada fase guarda sus segundos y sus «unidades» (fotogramas en la lectura de la pantalla, minutos de
audio en las demás). La estimación divide el total de segundos entre el total de unidades de las últimas
{{v:estimacion_historial}} ejecuciones. Así, un vídeo corto, donde pesa mucho cargar el modelo, no
distorsiona la estimación de uno largo (en un vídeo de 1 min el resumen tarda 85 s por minuto; en uno de
37 min, unos 6). Ejemplo de precisión: en un vídeo de 37 min estimó 331 s para regenerar el resumen y
tardó 315 s.
:::
