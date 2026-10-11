---
titulo: Perfiles
seccion: Conocimiento
orden: 20
claves: perfil, tipo de vídeo, glosario, contexto, secciones, instrucciones, crear desde vídeo, aprender
---
Un **perfil** es un **tipo de vídeo**: «Reuniones de equipo», «Tutorías», «Revisiones con cliente»…
Reúne lo que tienen en común: el vocabulario, las personas habituales y el contexto del negocio. Cada
vídeo con ese perfil se analiza con esa información, y cada vídeo nuevo puede enriquecerlo.

Un perfil no sirve para seguir un mismo tema a lo largo de varios vídeos: sirve para lo común a todos los
vídeos de ese tipo, aunque cada uno trate de una cosa distinta.

![Un perfil y sus pestañas](captura:perfil)

## Pestañas del perfil

- **Manual:** lo que escribes tú. La IA nunca lo modifica.
- **Aprendido:** lo que has aceptado de las propuestas de sus vídeos. Puedes editarlo o retirarlo.
- **Propuestas:** lo que la IA propone para este perfil y aún no has revisado.
- **[Historial](ayuda:historial):** todas sus versiones; cualquiera se puede restaurar.

## Parte manual

| Campo | Para qué sirve |
|---|---|
| **Contexto y lógica de negocio** | Explica de qué va este tipo de vídeo, quién es quién, cómo funciona tu trabajo. La IA lo usa para entender y redactar mejor. |
| **Glosario** | Términos que deben escribirse bien. Una línea por término: `Término \| variantes mal oídas \| definición`. |
| **Personas habituales** | Las personas que suelen aparecer. Ayudan a reconocer nombres y a orientar la transcripción. |
| **Instrucciones adicionales** | Indicaciones para el resumen de todos los vídeos del perfil. |
| **Secciones del resumen** | Si las indicas, el informe detallado se organiza con esos apartados. |

### Glosario

El glosario corrige la transcripción de forma conservadora:
- las **variantes** que declares («Selu \| Setu, Xelu») se sustituyen directamente por el término;
- si solo cambian las mayúsculas o las tildes, también se corrige directamente;
- si algo **se parece** al término al oído, la IA decide si es un error; ante la duda, no se cambia.

Además, los términos del glosario orientan a Whisper, que los escribirá mejor en los vídeos siguientes.

:::tecnico Corrección con el glosario
La búsqueda de parecidos usa una clave fonética del español y una similitud mínima de 86 sobre 100, en
ventanas de una palabra más o menos que el término. Los términos de menos de 4 letras solo se corrigen por
variante o mayúsculas. Cada línea corregida guarda su texto original. Los términos **aprendidos** nunca
corrigen solos: la IA valida cada cambio, incluso si solo cambian las mayúsculas.
:::

## Crear un perfil a partir de un vídeo

En la página de un vídeo sin perfil, **Crear perfil a partir de este vídeo** crea un perfil vacío,
asigna el vídeo, añade sus personas confirmadas y pide a la IA que proponga el contenido: términos,
contexto del negocio, secciones del resumen y datos de las personas. Lo revisas en
[Propuestas](ayuda:propuestas).

**Aprender de todos sus vídeos**, en el perfil, repite el aprendizaje con todos los vídeos ya analizados
de ese perfil.

## Qué propone la IA para un perfil

- **Términos** que se oyen en la conversación o forman parte del contenido de la pantalla. Las distintas
  formas de un mismo nombre («Bárymont», «Gestibarymont», «Grupo Bárymont») se proponen juntas.
- **Contexto duradero**: proyectos, clientes, sistemas, procesos y siglas. No lo puntual de esa reunión.
- **Secciones del resumen**, solo si el perfil aún no tiene: títulos que sirvan para cualquier vídeo de
  ese tipo.

:::tecnico Filtros de los términos
Un término debe aparecer literalmente en la transcripción o en la pantalla, parecer un término (con
mayúsculas, cifras o visto escrito) y ser relevante: oírse, o estar en el contenido principal de la
pantalla en al menos {{v:termino_fotogramas}} fotogramas. La lectura de la pantalla devuelve también todo
lo legible (barra de tareas, pestañas); en una grabación real, la mitad de los términos propuestos eran
programas del escritorio que nadie mencionaba. Las otras formas de un nombre no son «variantes» del
glosario (esas se sustituyen en el texto): se guardan aparte, se muestran en la propuesta y orientan a
Whisper.
:::
