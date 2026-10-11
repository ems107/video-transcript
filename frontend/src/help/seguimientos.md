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
  ya tiene en cuenta lo anterior del tema y, al terminar, el estado se actualiza solo.
- **Con un vídeo ya analizado**: en la página del vídeo, tarjeta **Seguimientos** → **Añadir a un
  seguimiento**, o desde la pestaña **Vídeos** del seguimiento. La IA aplica el vídeo al estado sin
  volver a transcribirlo. Si marcas **Regenerar también el resumen del vídeo**, además se rehace su
  resumen con el contexto del seguimiento.

![La tarjeta Seguimientos de un vídeo](captura:video-seguimientos)

La app no sugiere por su cuenta a qué seguimiento pertenece un vídeo: lo decides tú.

## El estado

- **Resumen de la evolución**: dónde está el tema y cómo ha llegado ahí.
- **Tareas**: abiertas, hechas o descartadas, con su responsable y su plazo.
- **Decisiones**: vigentes, cambiadas por otra posterior o anuladas.
- **Dudas y pendientes**: abiertas o resueltas.

Cada punto muestra su **recorrido**: una fila de hitos como «4 oct · 0:12:30 aparece → 5 oct · 0:03:10
hecha». Cada hito enlaza con el vídeo en ese momento. Por defecto se ven solo los puntos abiertos;
**Ver todas** muestra también los cerrados.

Cuando la IA da algo por hecho, resuelto o cambiado, el hito muestra **la frase del vídeo que lo dice**.
Si cree que ha pasado pero no encuentra esa frase, no cambia el estado: el hito aparece como **«¿hecha?»**
(o «¿resuelta?»…) con un botón **Confirmar**. Compruébalo en el vídeo con el enlace del hito y confírmalo
si es así; queda como cambio tuyo.

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
- al [regenerar](ayuda:regenerar) un vídeo que ya estaba aplicado.

**Rehacer el estado** quita lo que aportaron ese vídeo y los posteriores y vuelve a aplicarlos en orden,
a partir de sus análisis, sin transcribir de nuevo. Lo que cambiaste tú se conserva. **Dejarlo como está**
no cambia nada, pero el seguimiento queda marcado como **desactualizado**, con el motivo y un botón
**Rehacer el estado** con el tiempo estimado.

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
El trabajo se reparte en dos pasos, para que cada uno haga lo que mejor sabe hacer:

1. **Al resumir el vídeo**, la IA lee la transcripción con el estado anterior del tema, donde cada punto
   tiene un identificador ([T3] para una tarea, [D2] para una decisión, [P1] para una duda). Además del
   resumen, señala de qué puntos se habla y qué pasa con ellos, **copiando la frase que lo dice**. La app
   comprueba que esa frase se dice de verdad (parecido de {{v:seguimiento_cita_parecido}} sobre 100 con lo
   dicho {{v:seguimiento_cita_ventana}} s antes o después de su momento) y descarta las demás.
2. **La fase «Actualizando seguimientos»** (unos {{v:ritmo_follow}} s por minuto de vídeo) recibe esas
   señales, los puntos del vídeo y su resumen, y decide los hitos y el resumen de la evolución. Un cambio
   de estado (hecha, resuelta, cambiada…) solo se aplica si trae una cita que se dice en ese momento (una
   cita troceada con «…» vale si cada trozo se dice ahí); sin ella, queda como **posible** y lo confirmas
   tú.

Los **puntos nuevos** son las tareas, decisiones y pendientes del análisis del vídeo, los mismos que ves en
su pestaña «Tareas». La IA solo indica cuáles son el mismo asunto que uno anterior, para no duplicarlo.
Así el estado no cambia de una ejecución a otra, y corregir el análisis de un vídeo también corrige lo que
aporta al seguimiento.

Además, la app:
- descarta las referencias a puntos que no existen y los momentos que no están en el vídeo;
- descarta los cambios que no valen para el tipo de punto (resolver una tarea, por ejemplo);
- no vuelve a crear un punto que repite uno existente o uno que borraste (parecido de
  {{v:seguimiento_parecido}} sobre 100 o más);
- acepta como mucho {{v:seguimiento_max_senales}} señales por fragmento y {{v:seguimiento_max_eventos}}
  hitos por vídeo.

El estado de un punto sale siempre de su último hito. Para el contexto se envía el resumen, lo abierto y lo
cerrado en los últimos {{v:seguimiento_recientes}} vídeos, hasta {{v:seguimiento_contexto}} caracteres; si
no cabe, se recorta primero lo cerrado.
:::
