---
titulo: Hablantes
seccion: Cada vídeo
orden: 11
claves: hablante, voz, confirmar, cambiar, propuesta, pantalla, contexto, micrófono, dudosa, reasignada, dos voces, dividir, huella
---
La app separa las voces de la grabación en **hablantes** («Hablante 1», «Hablante 2»…) y propone quién
es cada uno. Tú confirmas o corriges.

![El panel de hablantes](captura:hablantes)

## Cómo se propone quién es cada hablante

Cada propuesta indica de dónde sale y con qué confianza:

| Origen | Cómo lo sabe | Confianza |
|---|---|---|
| **Micrófono** | Es la voz de tu pista de micrófono (si la indicaste al analizar). | Alta |
| **Voz** | Se parece a la voz de una persona que ya confirmaste en otro vídeo. | La que indica el porcentaje |
| **Pantalla** | Mientras habla, la videollamada resalta el recuadro con su nombre. | {{v:pantalla_confianza}} |
| **Contexto** | Se deduce de la conversación: se presenta, o le llaman por su nombre y responde. Debajo se muestra el motivo. | {{v:contexto_confianza}} |

**Nada se confirma solo.** Hasta que lo confirmas, el nombre aparece en la transcripción y en el
resumen, pero la app lo trata como una propuesta.

## Confirmar y cambiar

- **Confirmar** acepta la propuesta. **Aceptar propuestas** confirma todas las del vídeo de una vez.
- **Cambiar** permite elegir otra persona o escribir el nombre de una nueva.

Al confirmar, la app **guarda la huella de voz** de esa persona y la reconocerá en los vídeos siguientes.
Por eso conviene no confirmar un hablante que mezcla dos voces (ver más abajo): su huella sería de las dos
personas. Si una huella se guardó mal, en **Personas** está **Olvidar voz**.

Si un hablante aparecía como «Hablante N», al confirmarlo su nombre se sustituye al momento en la
transcripción y en el resumen.

:::tecnico Cómo se calcula cada propuesta
- **Voz:** se compara la huella del hablante con la media de las huellas guardadas de cada persona
  (similitud del coseno). Se propone desde {{v:voice_match_threshold}} y es de alta confianza desde
  {{v:voice_auto_threshold}}; ambos umbrales están en [Ajustes](ayuda:ajustes).
- **Pantalla:** primero se [unifican los nombres leídos](ayuda:decisiones#nombres-en-pantalla). Después,
  cada nombre se asigna a un solo hablante: el que más coincide con él, con al menos
  {{v:pantalla_minimo}} coincidencias, y siempre que esa voz tenga al menos {{v:pantalla_dominancia}}
  veces las lecturas de la siguiente. Así no se propone a quien solo está resaltado mientras otros hablan
  (por ejemplo, quien presenta).
- **Contexto:** lo propone la IA durante el resumen y se verifica en Python: el nombre debe verse en
  pantalla u oírse en la transcripción, y no puede repetirse en otro hablante.
:::

## Voz dudosa y reasignada

Después de separar las voces, la app **comprueba cada tramo por la voz**. La separación de voces se
equivoca a veces, sobre todo en saludos, cambios de turno y frases cortas:
- Si un tramo es **claramente** de otro hablante, lo reasigna, aunque sea en mitad de una línea. La línea
  aparece marcada como **reasignada por la voz**.
- Si **no está claro**, no cambia nada y la marca como **voz dudosa**. En la transcripción, **Solo
  dudosas** muestra únicamente esas líneas para revisarlas.

Las frases muy cortas (un «sí», un «vale») y los momentos en que hablan varias personas a la vez no se
pueden comprobar por la voz. Para eso está cambiar quién habla.

:::tecnico Cómo se comprueba por la voz
- La voz de cada hablante se calcula con sus intervenciones de {{v:voz_minimo_limpia}} s o más,
  descartando las que se parecen más a otro hablante.
- Cada intervención se recorre en ventanas de {{v:voz_ventana}} s cada {{v:voz_paso}} s. Para cada
  palabra se combinan las ventanas que la cubren, pesando más la centrada en ella.
- Se reasigna si la voz ganadora se parece al menos {{v:voz_parecido_minimo}} y supera a la segunda en
  {{v:voz_margen}} o más. Un tramo reasignado debe durar al menos {{v:voz_tramo_minimo}} s; si no, queda
  como dudoso.
- **Cómo se fijaron estos valores:** con un vídeo real de 37 minutos y 9 tramos que el usuario revisó
  escuchando. La comprobación acertó en todos los que tenían solución, incluido un saludo de medio
  segundo en mitad de una línea («Hola Edgar» de otra persona) y una línea partida justo donde cambiaba
  la voz. En ese vídeo reasignó 20 tramos y marcó 14 como dudosos, y tardó unos 40 s.
:::

## Cambiar quién habla

Si una frase está asignada a quien no es, **pulsa el nombre del hablante en esa línea de la
transcripción**. Puedes cambiarlo para:
- **Esta línea** entera;
- **Parte de la línea**: pulsas la primera y la última palabra que dice la otra persona;
- **Varias líneas** seguidas.

![Cambiar quién habla en parte de una línea](captura:cambiar-hablante)

Se guarda como «de tal momento a tal momento habla esta persona»: se ve al momento en la transcripción y
**se mantiene aunque regeneres el análisis**, también el completo. El panel de hablantes lista estos
cambios manuales y permite **Deshacer** cada uno. El resumen los tendrá en cuenta al
[regenerar](ayuda:regenerar); mientras tanto, la app avisa de que hay cambios sin aplicar.

Un cambio manual nunca modifica la huella de voz de nadie: un tramo corto no es fiable para eso.

## Dos voces en un hablante

A veces la separación junta a dos personas en un mismo hablante. Si las intervenciones de un hablante
forman dos grupos de voz claramente distintos, el panel avisa: **«Puede juntar dos voces distintas»**.
Pulsa **Revisar**: verás frases de cada grupo, con un botón para escucharlas, y podrás elegir quién es
cada grupo. Se guarda como cambios manuales.

Si faltan hablantes, también puedes [regenerar el análisis completo](ayuda:regenerar) indicando el número
de hablantes.

:::tecnico Cuándo se avisa de dos voces
Se agrupan en dos las intervenciones largas del hablante (2-medias sobre sus huellas). Se avisa si los
grupos están bien separados (silueta de {{v:voz_division_silueta}} o más), cada uno suma al menos
{{v:voz_division_segundos}} s y sus voces se parecen poco entre sí.
:::
