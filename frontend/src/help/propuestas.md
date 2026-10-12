---
titulo: Propuestas y aprendizaje
seccion: Conocimiento
orden: 21
claves: propuestas, aprender, aceptar, rechazar, evidencia, conocimiento, esperando, corrección de transcripción, mal transcrito, descartadas, dudosa
---
Cuando aplicas la [revisión de un vídeo](ayuda:revision), la IA **propone** lo que ha aprendido de él:
cómo se oyen mal los términos, términos y contexto para el perfil, datos de las personas y personas nuevas
que se mencionan. **Nada se usa hasta que lo aceptas.** La página **Propuestas** (con un contador en la
barra lateral) las reúne todas, y la pantalla **Revisar este vídeo**, las de cada vídeo.

Van ordenadas por lo que más ayuda en los vídeos siguientes: primero las correcciones de transcripción,
después lo que identifica a cada persona (otros nombres, cargo, organización, relación), luego el contexto
y los términos, y al final lo dudoso.

![La página de propuestas](captura:propuestas)

## Cómo se oyen mal los términos

Whisper a veces escribe mal un nombre: «Natur» por «Naturgy», «MAFRE» por «Mapfre». La IA lo detecta y
propone una **corrección de transcripción**: el término y las formas en que se oye mal, con las frases
donde aparecen (para escucharlas). Al aceptarla, esas formas se corrigen solas en los vídeos siguientes y
el término orienta a Whisper. Es lo mismo que añadir una variante en el [glosario del perfil](ayuda:perfiles#glosario).

Cada corrección dice en qué se apoya, de más a menos fiable:
- **según tus correcciones**: lo escribiste tú en las [correcciones](ayuda:correcciones) del vídeo;
- **se lee así en pantalla**: el nombre bien escrito se ve en pantalla y suena como lo transcrito;
- **ya lo corrigió el glosario**: la corrección de términos ya lo cambió en este vídeo; aceptarla lo hace
  automático;
- **lo deduce la IA**: sin otra prueba. Va marcada como **dudosa**: escucha el momento antes de aceptarla.

## Propuestas dudosas y descartadas

Antes de enseñarte las propuestas, la IA las revisa todas juntas y se pregunta, de cada una, si ayudará a
reconocer a una persona o a entender y transcribir los vídeos siguientes, o si es contenido de esa reunión
(lo que se explicó o se enseñó en ella, una tarea, algo puntual).
- Lo que no sirve lo **descarta**: no te lo enseña como propuesta, pero queda en **Descartadas por la IA**,
  plegado al final de las propuestas del vídeo, con su motivo y el botón **Recuperar**.
- Lo que repite otra propuesta también se descarta.
- Lo que no tiene claro lo marca como **dudoso**, con el motivo.

Un término que solo se ha visto en pantalla, sin que nadie lo mencione, puede tener que ver con la reunión
o no (una pestaña abierta, un programa del escritorio): también puede salir dudoso. Decide tú: **Aceptar
todas** no incluye las dudosas.

## Revisar una propuesta

Cada propuesta indica:
- **a quién va**: al perfil, a una persona, o es una persona nueva;
- **qué es** (término, contexto, cargo, responsabilidad, dato personal…);
- **de dónde sale**: el vídeo, el momento y las frases reales, con enlace a ese momento;
- si se ha visto **en varios vídeos** («visto en N vídeos»).

Puedes **Aceptar**, **Editar y aceptar** o **Rechazar**, una a una o todas las de un vídeo. Lo rechazado
no se vuelve a proponer.

## Qué aprende de las personas

Cargo, organización, equipo, responsabilidades, proyectos, conocimientos, relaciones y datos personales.
Lo aprende de lo que dice cada persona y de lo que otros dicen de ella.

- Lo que dice un hablante se atribuye a su persona **solo si está confirmado** o reconocido con mucha
  confianza (por tu micrófono o por la voz). Si no, la propuesta queda en **Esperando confirmación de
  hablantes** hasta que lo confirmes.
- Las personas que se mencionan y no existen en la app se proponen como **personas nuevas**. Al aceptarlas
  se crean con sus datos y se añaden al perfil del vídeo.
- Cargo, organización y equipo tienen un solo valor: al aceptar uno nuevo, el anterior se retira.

## Cómo se usa lo aceptado

Lo aceptado entra en el contexto que recibe la IA en los vídeos siguientes (después de lo manual, que
prevalece) y orienta a Whisper con los términos. Se ve en la pestaña **Aprendido** del perfil y en la ficha
de cada persona.

:::tecnico Cómo se comprueba cada propuesta
La IA no se cree: cada propuesta se verifica en Python antes de mostrarse.
- Un dato necesita una marca de tiempo dentro del tramo analizado y frases reales alrededor; al menos el
  60 % de sus palabras con contenido deben aparecer en la transcripción en un margen de un minuto. Sus
  cifras deben aparecer todas, en cifra o en palabra («27» o «veintisiete»): si no, «Tiene 27 años» valdría
  con cualquier frase cercana que dijera «años». Esto vale también cuando un vídeo vuelve a confirmar algo
  ya conocido.
- Se descarta lo puntual de esa reunión («ayer», «la semana que viene», tareas concretas).
- Lo rechazado no se vuelve a proponer, y lo pendiente de otros vídeos se le indica a la IA para que no lo
  repita con otras palabras.
- Límites por vídeo: {{v:aprender_max_terminos}} términos, {{v:aprender_max_contexto}} hechos de contexto,
  {{v:aprender_max_por_persona}} datos por persona, {{v:aprender_max_personas_nuevas}} personas nuevas y
  {{v:aprender_max_secciones}} secciones. Son solo una protección ante respuestas anómalas: lo que filtra
  el ruido son las comprobaciones. Antes eran 15, 10, 8, 5 y 5, y se perdían datos buenos por llegar
  tarde en la lista.
- Una corrección de transcripción necesita que la forma mal oída aparezca tal cual en la transcripción (en el
  texto de Whisper, antes del glosario). Las de la pantalla salen de la misma búsqueda por sonido que la
  [corrección con el glosario](ayuda:perfiles#glosario), con un parecido mínimo de
  {{v:aprender_parecido_pantalla}} sobre 100 (más bajo, porque aquí solo se propone): «Auradirect» frente a
  «Ahorro Directo» da 76. Como mucho {{v:aprender_max_correcciones}} por vídeo.
- La revisión conjunta va en tandas de {{v:aprender_juicio_tanda}} propuestas. Si falla, las propuestas se
  quedan como estaban.
:::
