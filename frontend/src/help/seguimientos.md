---
titulo: Seguimientos
seccion: Conocimiento
orden: 24
claves: seguimiento, continuidad, tema, serie, sesiones, tareas, decisiones, dudas, estado, rehacer, desactualizado, archivar
---
Un **seguimiento** reúne los vídeos de un mismo tema (las sesiones de un curso, las reuniones de un
proyecto, las visitas a un cliente…) y lleva su **estado**: qué se pidió, qué está hecho, qué se decidió,
qué sigue pendiente y cómo ha evolucionado. Cada punto dice en qué vídeo y en qué momento se habló de él.

![Un seguimiento con su estado](captura:seguimiento)

## Seguimiento o perfil

Son cosas distintas y se complementan:

| | Perfil | Seguimiento |
|---|---|---|
| **Qué guarda** | Lo común a un tipo de vídeos: vocabulario, personas, contexto general. | La historia de un tema concreto: sus tareas, decisiones y dudas, y un resumen de su evolución. |
| **Para qué sirve** | Transcribir y resumir mejor cualquier vídeo de ese tipo. | Saber en qué punto está el tema sin volver a ver los vídeos, y que cada vídeo nuevo se entienda como continuación de los anteriores. |
| **Cuántos por vídeo** | Uno. | Ninguno, uno o varios (una reunión puede tratar dos temas). |

Lo normal es que todos los vídeos de un seguimiento tengan el mismo perfil, y por eso, al elegir un
seguimiento en **Nuevo análisis**, se elige también el perfil que usan sus vídeos. Pero no es obligatorio.
El seguimiento no alimenta el aprendizaje del perfil: las tareas de un tema no son conocimiento general.

## Crear un seguimiento

En **Seguimientos** → **Nuevo seguimiento**, o desde la página de un vídeo con **Añadir a un seguimiento**
→ «Nuevo seguimiento…». Solo hace falta un nombre.

## Añadir vídeos

Hay dos formas:

- **Al encolar un vídeo nuevo**: en [Nuevo análisis](ayuda:analizar), marca sus seguimientos. El análisis
  ya tiene en cuenta lo anterior del tema, y el estado se actualiza cuando [revisas el vídeo](ayuda:revision)
  y pulsas **Aplicar y continuar**. Las dudas de la IA (un punto que parece repetir otro, un cambio sin
  frase que lo demuestre) te las pregunta en la revisión.
- **Con un vídeo ya analizado**: en la página del vídeo, tarjeta **Seguimientos** → **Añadir a un
  seguimiento**, o desde la pestaña **Vídeos** del seguimiento. La IA aplica el vídeo al estado sin
  volver a transcribirlo. Si marcas **Regenerar también el resumen del vídeo**, además se rehace su
  resumen con el contexto del seguimiento.

![La tarjeta Seguimientos de un vídeo](captura:video-seguimientos)

La app no sugiere por su cuenta a qué seguimiento pertenece un vídeo: lo decides tú.

## El estado

- **Resumen de la evolución**: de dónde partió el tema, qué aportó cada vídeo y dónde está ahora. Los
  momentos que cita llevan la fecha de su vídeo («8 sep · 0:24:00») y enlazan con él.
- **Tareas**: abiertas, hechas o descartadas, con su responsable y su plazo. El responsable se escribe con
  el nombre de las personas que conoce la app («Iosu/Selu» pasa a «Iosu Urcelay, José Luis Pérez», por su
  nombre o su apodo); lo que no es una persona conocida se queda como lo dijo la IA. En los puntos creados
  antes de la versión 1.6.1, se arregla con **Rehacer el estado**.
- **Decisiones**: vigentes, cambiadas por otra posterior o anuladas.
- **Dudas y pendientes**: abiertas o resueltas.

Cada punto muestra su **recorrido**: una fila de hitos como «4 oct · 0:12:30 aparece → 5 oct · 0:03:10
hecha». Cada hito enlaza con el vídeo en ese momento. Por defecto se ven solo los puntos abiertos;
**Ver todas** muestra también los cerrados.

Cuando la IA da algo por hecho, resuelto o cambiado, el hito muestra **la frase del vídeo que lo dice**.
Si cree que ha pasado pero no encuentra esa frase, no cambia el estado: el hito aparece como **«¿hecha?»**
(o «¿resuelta?»…) con los botones **Confirmar** y **No pasó**. Compruébalo en el vídeo con el enlace del
hito; lo que decidas queda como cambio tuyo.

Un vídeo que es el propio asunto de un punto lo cierra: si quedaba pendiente «Realizar la sesión de
diagnóstico» y el vídeo es esa sesión, el punto queda hecho, con la frase en que empieza.

Cada tarea, decisión o duda de un vídeo nuevo se compara con las anteriores, también con las que
borraste. Si es la misma (aunque esté escrita de otra forma), no se repite. Si la IA no lo tiene claro, la
crea con la pregunta **«¿Es lo mismo que…?»**: **Sí, borrar este** o **No, es distinto**. Estas dudas
aparecen también al [revisar el vídeo](ayuda:revision).

La pestaña **Vídeos** lista los vídeos en orden de fecha de grabación, con lo que aportó cada uno.

## Lo que haces tú

Puedes cambiar el estado de un punto (por ejemplo, marcar una tarea como hecha), editar su texto,
borrarlo o **añadir uno a mano**. Lo que cambias queda marcado como **tuyo** y la IA ya no lo toca: puede
anotar en su recorrido que un vídeo posterior habla de él, pero no cambia su texto ni su estado. Un punto
que borras no vuelve a aparecer aunque se rehaga el estado.

El **resumen** también se puede editar. Desde ese momento la IA no lo reescribe; cuando tenga uno nuevo,
verás «Hay un resumen nuevo de la IA» con las opciones **Ver** y **Usar el de la IA**.

## Desactualizado y Rehacer

El estado se construye vídeo a vídeo en orden de fecha. Cuando algo cambia en medio, la app te pregunta si
lo rehace:

- al **quitar un vídeo** del seguimiento (o [quitarlo de la app](ayuda:quitar));
- al [regenerar](ayuda:regenerar) un vídeo que ya estaba aplicado: el estado se rehace desde él cuando
  vuelves a aplicar su revisión.

**Rehacer el estado** quita lo que aportaron ese vídeo y los posteriores y vuelve a aplicarlos en orden,
a partir de sus análisis, sin transcribir de nuevo. Lo que cambiaste tú se conserva, y lo que borraste no
vuelve. **Dejarlo como está** no cambia nada, pero el seguimiento queda marcado como **desactualizado**,
con el motivo y un botón **Rehacer el estado** con el tiempo estimado.

También puedes rehacerlo cuando quieras con el botón **Rehacer el estado…** de arriba: eliges desde qué
vídeo y ves cuánto tardará. Un vídeo pendiente de [revisar](ayuda:revision) no se aplica hasta que lo
revisas.

También queda desactualizado, sin preguntar, cuando se analiza en la cola un vídeo **anterior** a otros
del seguimiento (se grabó antes pero se analiza después): para incluirlo en su sitio hay que rehacer desde
él.

## Historial, archivar y la carpeta

- **Historial**: antes de cada cambio, tuyo o de la IA, se guarda una copia del estado. **Restaurar**
  vuelve a cualquiera de ellas (y guarda antes la actual).
- **Archivar**: cuando el tema termina. Deja de aparecer al encolar y no admite vídeos nuevos, pero se
  puede consultar y **reabrir**.
- **Carpeta**: junto a las de los vídeos se crea `Seguimiento - Nombre/` con `seguimiento.md`, el estado
  completo con enlaces al resumen de cada vídeo. Se actualiza con cada cambio. **Abrir carpeta** la
  muestra en el Explorador.

:::tecnico Cómo se actualiza el estado
La fase «Actualizando seguimientos» hace, por cada seguimiento del vídeo, dos consultas a la IA:

1. **Qué dice el vídeo de cada punto del estado.** La IA lee la transcripción (por bloques de
   {{v:chunk_minutes}} minutos) con la lista de puntos y sus identificadores ([T3] para una tarea, [D2]
   para una decisión, [P1] para una duda), y devuelve de cuáles se habla, qué pasa con ellos y **la frase
   que lo dice**. Esta consulta usa el **modo razonamiento** del modelo, que piensa antes de responder: sin
   él, no encontraba los cierres dichos de pasada («lo que ayer fallaba ya ha funcionado») e inventaba
   momentos y frases. La app comprueba cada frase (parecido de {{v:seguimiento_cita_parecido}} sobre 100 con
   lo dicho {{v:seguimiento_cita_ventana}} s antes o después de su momento; una frase troceada con «…» vale
   si cada trozo se dice ahí). Un cambio de estado con la frase comprobada se aplica; sin ella queda como
   **posible**, para que lo confirmes tú. A veces el modelo piensa tanto que llega a su límite sin
   responder: entonces la app repite ese bloque partido en dos mitades. Si tampoco así responde, el
   seguimiento queda **desactualizado** con el motivo, y se arregla con **Rehacer el estado**.
   La IA recibe también de qué trata el vídeo (su título y su resumen breve), para dar por hecho un punto
   que consiste en hacer esa misma reunión.
2. **Qué puntos del vídeo son el mismo asunto que uno anterior y el resumen de la evolución.** Sin modo
   razonamiento. La IA clasifica cada punto del vídeo como «mismo», «nuevo» o «dudoso» frente a los del
   estado, los que borraste y los demás del mismo vídeo. Para el resumen recibe lo que aportó cada vídeo
   anterior, en orden: así no se queda solo con el último.

Los **puntos nuevos** son las tareas, decisiones y pendientes del análisis del vídeo, los mismos que ves en
su pestaña «Tareas»: no los inventa la IA. Así el estado no cambia de una ejecución a otra, y corregir el
análisis de un vídeo también corrige lo que aporta al seguimiento.

Además, la app descarta las menciones de puntos que no existen, los momentos que no están en el vídeo y los
cambios que no valen para el tipo de punto. Como red de seguridad, no crea un punto cuyo texto casi repite
el de uno existente o uno que borraste (parecido de {{v:seguimiento_parecido}} sobre 100 o más), aunque la
IA lo dé por nuevo. Acepta como mucho {{v:seguimiento_max_menciones}} menciones por bloque.

Tarda unos {{v:ritmo_follow}} s por minuto de vídeo, sobre todo por el modo razonamiento. El primer vídeo
de un seguimiento apenas tarda, porque aún no hay puntos que buscar: por eso no cuenta ni para medir el
ritmo ni para estimar lo que tarda **Rehacer el estado**. El estado de un
punto sale siempre de su último hito. Para el contexto se envía el resumen, lo abierto y lo cerrado en los
últimos {{v:seguimiento_recientes}} vídeos, hasta {{v:seguimiento_contexto}} caracteres; si no cabe, se
recorta primero lo cerrado.
:::
