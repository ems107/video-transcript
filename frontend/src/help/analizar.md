---
titulo: Analizar un vídeo
seccion: Empezar
orden: 2
claves: nuevo análisis, ruta, pista, micrófono, mover, copiar, hablantes, perfil, seguimiento
---
En **Nuevo análisis** indicas el vídeo y cómo quieres analizarlo. Se añade a la [cola](ayuda:cola) y se
procesa solo; puedes seguir usando la app mientras tanto.

![La pantalla «Nuevo análisis»](captura:nuevo-analisis)

## Opciones

| Opción | Para qué sirve |
|---|---|
| **Ruta del vídeo** | El archivo a analizar. En el Explorador de Windows: Mayús + clic derecho → «Copiar como ruta». Pulsa **Comprobar** para ver su duración y sus pistas de audio. |
| **Perfil** | El tipo de vídeo (por ejemplo, «Reuniones de equipo»). Aporta el vocabulario, las personas habituales y el contexto. Puedes dejarlo **Sin perfil** y crear uno después a partir del vídeo. |
| **Seguimientos** | Solo aparece si tienes [seguimientos](ayuda:seguimientos) abiertos. Marca los temas que continúa este vídeo: el análisis tiene en cuenta lo anterior y, al terminar, se actualiza su estado. Al marcar uno, si no has elegido perfil, se elige el que usan sus vídeos. |
| **Mínimo y máximo de hablantes** | Opcional (por defecto, «Automático»). Si sabes cuántas personas hablan, ayuda a separar bien las voces. |
| **Audio para transcribir** y **Pista de tu micrófono** | Solo aparecen si el vídeo tiene varias pistas de audio. Lo normal es **Mezclar todas las pistas**. Si grabas tu micrófono en una pista aparte, indícala: la app te identificará a ti automáticamente, con el nombre de [Ajustes](ayuda:ajustes). |
| **Al terminar** | **Mover** el vídeo a su carpeta de resultados o **Copiar** (el original no se toca). |
| **No analizar la imagen** | Más rápido: solo se usa el audio. Se pierde lo que se ve en pantalla (descripciones, nombres de los participantes y términos visibles). |

## Qué tarda

Depende sobre todo de la duración y de cuántos cambios hay en pantalla. Con una RTX 5070 Ti, una
videollamada de 37 minutos tarda unos 40 minutos: la mayor parte es leer la pantalla. La
[cola](ayuda:cola) muestra en qué fase va cada vídeo.

:::tecnico Tiempos por fase
Medidos con grabaciones reales (segundos por minuto de audio, salvo la pantalla, que es por
fotograma): seleccionar fotogramas {{v:ritmo_frames}} s/min, leer la pantalla {{v:ritmo_vision}}
s/fotograma, transcribir {{v:ritmo_asr}} s/min, separar voces {{v:ritmo_diarize}} s/min, resumir
{{v:ritmo_analyze}} s/min y aprender {{v:ritmo_learn}} s/min. La app guarda lo que tarda cada fase en
tu equipo y usa esos tiempos para las estimaciones (ver [Regenerar](ayuda:regenerar#estimaciones)).
:::

## Qué obtienes

Al terminar, el vídeo aparece en la **Biblioteca** y se publica en
`<carpeta de analizados>/AAAA-MM-DD - Título/` con:
- `resumen.md` y `transcripcion.md` (para leer), `transcripcion.txt` (texto plano) y `analisis.json`
  (todo en datos);
- `miniatura.jpg` y la carpeta `fotogramas/`;
- el vídeo (movido o copiado);
- la carpeta `datos/`, una [copia de recuperación](ayuda:quitar#copia-de-recuperacion).
