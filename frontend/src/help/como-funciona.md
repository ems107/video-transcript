---
titulo: Cómo funciona
seccion: Por dentro
orden: 40
claves: fases, pipeline, proceso, cómo funciona, transcripción, pantalla, voces, resumen
---
Cada vídeo pasa por estas fases, en orden. La [cola](ayuda:cola) muestra en cuál está. La tarjeta gráfica
solo tiene un modelo grande cargado a la vez, así que las fases se turnan.

## 1. Preparar el audio
Extrae el audio del vídeo y, si la grabación tiene varias pistas, la que elegiste (y la de tu micrófono,
si la indicaste).

## 2. Elegir fotogramas
Recorre el vídeo buscando **cambios en la pantalla** y se queda con un fotograma de cada momento distinto,
más uno cada cierto tiempo aunque no cambie nada.

:::tecnico Selección de fotogramas
Toma una muestra cada {{v:frame_sample_every}} s y compara su «huella» visual (hash perceptual). Guarda un
fotograma cuando cambia lo suficiente (distancia mayor que {{v:frame_hash_distance}}), con al menos
{{v:frame_min_interval}} s entre uno y otro y como mucho {{v:frame_max_interval}} s. Si salen más de
{{v:max_frames}}, sube la exigencia hasta caber.
:::

## 3. Leer la pantalla
La IA mira cada fotograma y anota: qué tipo de escena es (videollamada, presentación, código…), qué
programa se ve, una descripción, el texto importante, los participantes visibles y quién aparece resaltado
como hablando.

## 4. Transcribir
**Whisper** convierte la voz en texto. Antes recibe una pista con los términos del perfil, las personas y lo
leído en pantalla, para escribir bien los nombres propios.

## 5. Alinear palabras
Calcula en qué momento exacto se dice cada palabra. Sirve para saber quién dice cada palabra y para los
enlaces a momentos del vídeo.

## 6. Separar voces
**pyannote** distingue las voces de la grabación y reparte el tiempo entre hablantes («Hablante 1»,
«Hablante 2»…). Si indicaste cuántos hablantes hay, lo tiene en cuenta.

## 7. Comprobar las voces
Comprueba tramo a tramo que cada frase esté asignada a la voz correcta, reasigna lo que está claro y marca
lo dudoso. Ver [Hablantes](ayuda:hablantes#voz-dudosa-y-reasignada).

## 8. Unificar nombres
Junta las distintas lecturas de un mismo nombre en pantalla («Iosu», «Iker», «Ione»… cuando es la misma
persona) y elige una sola forma. Ver [Decisiones](ayuda:decisiones#nombres-en-pantalla).

## 9. Identificar personas
Propone quién es cada hablante: por tu micrófono, por la voz (si ya la conoce) o por el nombre resaltado en
pantalla. Ver [Hablantes](ayuda:hablantes).

## 10. Corregir términos
Aplica el [glosario del perfil](ayuda:perfiles#glosario) a la transcripción.

## 11. Resumir
La IA lee la transcripción con lo que se vio en pantalla, por bloques de {{v:chunk_minutes}} minutos, y
después redacta el informe final: título, resumen, participantes, temas, tareas, decisiones y pendientes.
Recibe el contexto del perfil, quién es quién y tus [correcciones](ayuda:correcciones). Aquí también puede
deducir quién es un hablante por la conversación.

Si el vídeo está en algún [seguimiento](ayuda:seguimientos), también recibe el estado del tema según los
vídeos anteriores, solo para entender a qué se refiere lo que se dice y relacionarlo.

## 12. Actualizar los seguimientos
Si el vídeo está en algún [seguimiento](ayuda:seguimientos), la IA aplica lo que dice a su estado: tareas
que avanzan o se cierran, decisiones que cambian, dudas que se resuelven y lo nuevo. Si esta fase falla, el
seguimiento queda desactualizado y el vídeo se publica igual.

## 13. Aprender
Propone lo que ha aprendido del vídeo para el perfil y las personas. Ver [Propuestas](ayuda:propuestas). Si
esta fase falla, el vídeo se publica igual.

## 14. Publicar
Crea la carpeta del vídeo con sus documentos, lo mueve o copia, y lo añade a la biblioteca y a la búsqueda.

:::tecnico Ficheros de trabajo
Cada fase escribe sus resultados en `data/work/job_<n>/` (por ejemplo, `vision.json`, `asr.json`,
`diarization.json`, `words.json`, `utterances.json`, `analysis.json`). Gracias a ellos, un análisis
interrumpido continúa donde se quedó, y [regenerar](ayuda:regenerar) solo repite lo necesario. Los
modelos se describen en [Modelos y equipo](ayuda:modelos).
:::
