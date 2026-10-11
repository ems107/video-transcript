---
titulo: Primeros pasos
seccion: Empezar
orden: 1
claves: inicio, introducción, qué hace, flujo, empezar
---
Video Transcript analiza grabaciones de tu escritorio (videollamadas, demostraciones, sesiones de
trabajo) **sin enviar nada fuera de tu equipo**. Todo funciona con modelos de IA locales y gratuitos.

De cada vídeo obtienes:
- **la transcripción**, con quién dice cada cosa;
- **lo que se vio en pantalla**, fotograma a fotograma;
- **un resumen** con título, participantes, temas, tareas, decisiones y pendientes, con enlaces a cada
  momento del vídeo;
- **una carpeta** con el vídeo y sus documentos (`resumen.md`, `transcripcion.md`…).

Además, la app **aprende** de cada vídeo: reconoce a las personas por su voz, recuerda los términos de
tu trabajo y va completando una ficha de cada persona. Nunca usa lo aprendido sin que lo aceptes tú.

![La biblioteca con los vídeos analizados](captura:biblioteca)

## Flujo recomendado

1. **[Analiza un vídeo](ayuda:analizar)**: pega su ruta y elige un perfil si ya tienes uno.
2. **Revisa los hablantes** en la página del vídeo: confirma las propuestas correctas y cambia las que
   no. Al confirmar, la app guarda la voz y reconocerá a esa persona en los vídeos siguientes. Ver
   [Hablantes](ayuda:hablantes).
3. **Corrige lo que esté mal**: quién dice una frase ([cambiar quién habla](ayuda:hablantes#cambiar-quien-habla)),
   una palabra mal transcrita ([glosario del perfil](ayuda:perfiles#glosario)) o algo que la IA ha
   interpretado mal ([correcciones](ayuda:correcciones)). Después, [regenera el análisis](ayuda:regenerar).
4. **Crea un perfil** a partir del primer vídeo de un tipo (por ejemplo, «Reuniones de equipo») y revisa
   lo que propone. Ver [Perfiles](ayuda:perfiles).
5. **Revisa las [propuestas](ayuda:propuestas)** de cada vídeo nuevo: acepta lo útil y rechaza lo demás.
   Con cada vídeo, la app sabe más del perfil y de las personas.

## Principios de la app

- **Todo es local.** Ni el audio, ni las imágenes, ni el texto salen de tu equipo.
- **La IA propone y tú decides.** Lo que escribes tú (perfiles, personas, correcciones) nunca lo cambia
  la IA. Lo que aprende solo se usa después de aceptarlo, y todo cambio se puede deshacer
  ([historial](ayuda:historial)).
- **No inventa.** El resumen y lo aprendido se comprueban contra la transcripción y la pantalla. Lo que
  no está claro se marca como dudoso en vez de adivinarse.

:::tecnico Cómo está hecha
Es una aplicación web local: un servidor en Python (FastAPI) en `http://127.0.0.1:8770` y una web en
React. Los modelos son Whisper large-v3 (transcripción), wav2vec2 (alineado de palabras), pyannote
community-1 (separación de voces y huellas) y Qwen3.6-35B-A3B a través de llama.cpp (análisis de la
pantalla, resumen y aprendizaje). Los datos se guardan en una base SQLite en `data/`. Más detalles en
[Cómo funciona](ayuda:como-funciona) y [Modelos y equipo](ayuda:modelos).
:::
