---
titulo: Propuestas y aprendizaje
seccion: Conocimiento
orden: 21
claves: propuestas, aprender, aceptar, rechazar, evidencia, conocimiento, esperando
---
Después de analizar cada vídeo, la IA **propone** lo que ha aprendido: términos y contexto para el perfil,
datos de las personas y personas nuevas que se mencionan. **Nada se usa hasta que lo aceptas.** La página
**Propuestas** (con un contador en la barra lateral) las reúne todas.

![La página de propuestas](captura:propuestas)

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
  60 % de sus palabras con contenido deben aparecer en la transcripción en un margen de un minuto.
- Se descarta lo puntual de esa reunión («ayer», «la semana que viene», tareas concretas).
- Lo rechazado no se vuelve a proponer, y lo pendiente de otros vídeos se le indica a la IA para que no lo
  repita con otras palabras.
- Límites por vídeo: {{v:aprender_max_terminos}} términos, {{v:aprender_max_contexto}} hechos de contexto,
  {{v:aprender_max_por_persona}} datos por persona, {{v:aprender_max_personas_nuevas}} personas nuevas y
  {{v:aprender_max_secciones}} secciones. Son solo una protección ante respuestas anómalas: lo que filtra
  el ruido son las comprobaciones. Antes eran 15, 10, 8, 5 y 5, y se perdían datos buenos por llegar
  tarde en la lista.
:::
