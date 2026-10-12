---
titulo: Decisiones, límites y umbrales
seccion: Por dentro
orden: 41
claves: decisiones, límites, umbrales, por qué, resolución, temperatura, bucle, voz, nombres, aprendizaje, ajustes de la IA
---
Aquí se explican las decisiones de diseño que más afectan al resultado: **qué se decidió, por qué, qué
consecuencias tiene y si se puede cambiar**. Los valores son los de tu app en este momento.

## Resolución de la pantalla

**Qué:** los fotogramas se leen a {{v:frame_max_width}} píxeles de ancho como máximo.

**Por qué:** con menos resolución, la IA no lee bien el texto pequeño, como los nombres bajo cada
participante de una videollamada: inventaba letras y el mismo nombre salía de muchas formas.

**Consecuencia:** leer la pantalla es la fase más lenta (unos {{v:ritmo_vision}} s por fotograma).

**¿Se puede cambiar?** Sí, con `frame_max_width` en `data/settings.json` (ver [Ajustes](ayuda:ajustes)). Bajarlo
acelera el análisis pero empeora la lectura de texto pequeño.

:::tecnico Medición
Con fotogramas de una grabación 4K: nombres leídos exactamente, el 44 % a 1600 px, el 56 % a 1920 px y el
100 % a 2560 px; el tiempo por fotograma, unos 9, 10,5 y 14,5 s. Forzar más «tokens» de imagen en el
modelo no mejoró nada.
:::

## Nombres en pantalla

**Qué:** en cada vídeo, todas las lecturas parecidas de un nombre se juntan y se elige una sola forma.

**Por qué:** la IA lee cada fotograma por separado y, con texto pequeño, el mismo nombre salía de decenas de
formas («Iosu Urcelay», «Iker Urcelay», «Ione Urcelay»…), y el resumen trataba cada una como una persona
distinta.

**Cómo se elige la forma:** gana lo que se **oye** en la conversación (si alguien dice «Iosu», gana «Iosu»
aunque se haya leído más veces «Iker»); después, lo más leído. Una tilde se conserva si aparece en al menos
el {{v:nombres_tildes_pct}} % de las lecturas, porque al leer texto pequeño es más fácil
perderla que inventarla. Si coincide con una persona que ya conoces, se usa su nombre. **Nunca se juntan
dos nombres que aparecen a la vez en pantalla**: son dos recuadros, dos personas.

**¿Se puede cambiar?** No desde la app. Si un nombre sale mal, añádelo como persona o como «otro nombre»
de una persona.

:::tecnico Agrupación
Similitud de nombres (rapidfuzz y una clave fonética) de {{v:nombres_parecido}} o más sobre 100: el mismo
nombre de pila con un apellido mal leído, los mismos apellidos con distinto nombre de pila, o un nombre
corto con alguna letra cambiada («Edge» y «Edgar»). La forma final se construye palabra a palabra. En un
vídeo real se pasó de unas 60 variantes a los 4 nombres reales.
:::

## Quién está resaltado en pantalla

**Qué:** el nombre que se ve resaltado mientras alguien habla solo se propone si se concentra claramente
en una voz, y cada nombre se asigna a un solo hablante.

**Por qué:** la IA no detecta bien quién está resaltado. En una prueba dijo que hablaba la misma persona
en 4 fotogramas de 4, y solo era así en 2. Además, quien presenta suele salir resaltado mientras hablan
otros.

**Consecuencia:** a veces un hablante se queda sin propuesta por pantalla aunque su nombre aparezca. Lo
cubren la voz y el contexto, o lo confirmas tú.

:::tecnico Criterio
Al menos {{v:pantalla_minimo}} coincidencias, que sea el nombre más leído de ese hablante sin empate, y que
esa voz tenga al menos {{v:pantalla_dominancia}} veces las lecturas del nombre que la siguiente. Un
fotograma a menos de {{v:borde_turno}} s de un cambio de turno se asigna a quien empieza a hablar, porque
el fotograma se toma justo al cambiar el resaltado; uno que cae en un silencio no cuenta.
:::

## Comprobación por la voz

**Qué:** se reasigna un tramo a otro hablante solo cuando la voz lo deja claro; si no, se marca como dudoso.

**Por qué:** es preferible avisarte de lo dudoso a cambiar algo bien por algo mal.

**Consecuencia:** las frases muy cortas y los momentos en que hablan varios a la vez no se resuelven solos.
Para eso está [cambiar quién habla](ayuda:hablantes#cambiar-quien-habla).

Los valores y cómo se midieron están en [Hablantes](ayuda:hablantes#voz-dudosa-y-reasignada).

## Ajustes de la IA

**Qué:** la IA se usa con los ajustes que recomienda su fabricante (Qwen) para este modelo: temperatura
{{v:llm_temperature}} y una penalización por repetir de {{v:llm_presence_penalty}}.

**Por qué:** la IA escribe palabra a palabra, y cada palabra se elige según lo ya escrito. Con poca
variación y sin penalización, a veces entraba en un **bucle**: copiaba el elemento anterior de una lista una
y otra vez (el mismo apodo decenas de veces, o el mismo dato alternando entre dos personas) hasta agotar la
respuesta. La temperatura controla cuánto varía; la penalización castiga repetir lo ya escrito.

**Consecuencia:** al regenerar, el resultado varía un poco (otro título, alguna propuesta más o menos),
aunque el fondo es el mismo.

**¿Se puede cambiar?** Sí, en `data/settings.json`, pero no conviene sin volver a medir.

:::tecnico Medición y protecciones
Antes se usaba temperatura 0,2 sin penalización. Con el mismo vídeo de 37 minutos, el aprendizaje pasó de
31 datos repetidos por bucle a ninguno en dos ejecuciones, sin respuestas cortadas ni mezcla de idiomas (la
ficha del modelo avisa de que una penalización alta puede provocarla). Ajustes completos: temperatura
{{v:llm_temperature}}, top_p {{v:llm_top_p}}, top_k {{v:llm_top_k}}, min_p {{v:llm_min_p}} y
presence_penalty {{v:llm_presence_penalty}}, sin «modo razonamiento» salvo en un caso medido: buscar qué
dice un vídeo de los puntos de un [seguimiento](ayuda:seguimientos), donde sin razonar el modelo no
encontraba los cierres dichos de pasada e inventaba momentos. Además, todas las listas que devuelve
la IA tienen un máximo de elementos, y si una respuesta llega cortada o no es válida se guarda en
`data/llm_failures/` para poder diagnosticarla.
:::

## Límites del aprendizaje

**Qué:** como mucho, {{v:aprender_max_por_persona}} datos por persona y vídeo, {{v:aprender_max_terminos}}
términos, {{v:aprender_max_contexto}} hechos de contexto, {{v:aprender_max_personas_nuevas}} personas
nuevas y {{v:aprender_max_secciones}} secciones.

**Por qué:** son solo una protección ante una respuesta anómala. Lo que evita el ruido son las
comprobaciones de cada propuesta (ver [Propuestas](ayuda:propuestas)).

**Antes:** eran 8 datos por persona, 15 términos, 10 hechos y 5 personas nuevas, y se perdían datos buenos
solo por llegar tarde en la lista.

## Términos que se proponen para un perfil

**Qué:** un término que se oye en la conversación se propone como siempre. Uno que **solo se ve en
pantalla** también se analiza, pero la IA razona si tiene relación con el vídeo: con lo que trata la
grabación y con dónde, cuándo y cuánto aparece. Según su respuesta:
- **relacionado**: se propone, con el motivo;
- **dudoso**: se propone marcado como **dudoso**, con el motivo, para que decidas tú;
- **sin relación**: no se propone (queda anotado en los datos del vídeo).

**Por qué:** la pantalla puede mostrar contenido de la reunión, pero también el escritorio, pestañas o
programas ajenos a ella, y lo que es ruido en un vídeo es lo importante en otro: la pestaña de un gestor de
tareas no pinta nada en una llamada de soporte, pero es el centro de una reunión de planificación. Una regla
fija (un mínimo de fotogramas, aparecer en varios momentos) no lo distingue: medido con vídeos reales,
dejaba pasar pestañas del navegador y, a la vez, quitaba términos reales del contenido.

**Consecuencia:** a veces verás propuestas **dudosas**. «Aceptar todas» no las incluye.

## Identidades y apodos deducidos por el contexto

**Qué:** la IA puede deducir quién es un hablante por la conversación, o que un apodo es de alguien, pero
solo se acepta si se puede comprobar.

**Por qué:** una versión anterior le pedía relacionar los apodos con los participantes «si correspondían»,
y adivinaba: atribuyó a una persona el apodo de otra. Ahora un nombre deducido debe verse en pantalla u
oírse; un apodo debe oírse y parecerse al nombre de la persona (por ejemplo, «Selu» está dentro de
«JoSELUis»). Si no está claro, se deja tal como se oye.

**Consecuencia:** a veces un apodo no se relaciona con nadie. Lo arreglas con una
[corrección](ayuda:correcciones).

:::tecnico Parecido de apodos
Coincidencia parcial de {{v:apodo_parecido}} o más sobre 100 entre el apodo y el nombre completo sin
espacios. Una identidad deducida por el contexto tiene confianza {{v:contexto_confianza}} y nunca se
confirma sola.
:::

## Seguimientos

**Qué:**
- el vídeo se añade a un seguimiento solo si tú lo eliges; la app no lo sugiere;
- el estado de un seguimiento lo actualiza la IA sin pedirte confirmación, pero cada cambio guarda antes
  una versión y lo que cambias tú no lo toca;
- cada vídeo recibe solo el estado de los vídeos **anteriores** en fecha;
- el seguimiento no alimenta el aprendizaje del perfil.

**Por qué:**
- Las sugerencias costarían una llamada a la IA por vídeo y, con pocos seguimientos, aportan poco frente
  a marcarlo tú al encolar.
- Confirmar cada hito (tarea hecha, decisión cambiada…) sería lento. A cambio, cada hito lleva su vídeo y su
  momento para comprobarlo, la app descarta los que no puede comprobar y siempre puedes restaurar una
  versión anterior.
- Un vídeo no puede «saber» lo que se dijo después: si analizas uno antiguo, ve el tema como estaba
  entonces.
- Las tareas de un tema concreto no son conocimiento general: llenarían el perfil de asuntos que no
  sirven para otros vídeos.

**Consecuencia:** si se analiza un vídeo anterior a otros del seguimiento, o se cambia uno del medio, el
estado queda desactualizado hasta que lo rehaces. Ver [Seguimientos](ayuda:seguimientos#desactualizado-y-rehacer).

## Revisar antes de que un vídeo cuente

**Qué:** hasta que revisas un vídeo y pulsas **Aplicar y continuar**, no actualiza sus seguimientos, no
propone nada y no guarda voces. Los vídeos del mismo perfil o seguimiento encolados después hacen lo más
pesado y **esperan** a esa revisión antes de identificar a los hablantes y resumir.

**Por qué:** en la prueba con tres vídeos de una tutoría, cada vídeo pedía entre 30 y 60 decisiones,
sobre todo por duplicados y ruido creados antes de que pudieras corregir el vídeo: al corregir y
regenerar, el seguimiento y lo aprendido se rehacían y volvían a aparecer. Con la revisión antes, se
calculan una sola vez y con la información buena; y el vídeo siguiente ya usa las voces, el glosario y el
seguimiento revisados.

**Consecuencia:** un vídeo sin revisar frena a los relacionados que encoles después (no a los demás).
Esperar desde el principio costaría unos 30–45 minutos más por vídeo: por eso la pantalla y la
transcripción se adelantan. Ver [Revisar un vídeo](ayuda:revision).

## Voz mínima y voces dudosas

**Qué:** la voz de una persona en un vídeo se guarda solo si suma al menos {{v:voz_huella_minimo}} s
limpios, y queda **dudosa** (sin usar hasta que decidas) si no se parece a la de sus otros vídeos (menos
de {{v:voice_match_threshold}}).

**Por qué:** una huella hecha con muy poca voz, o con la de otra persona, haría que la app la reconociera
mal en los vídeos siguientes. Con 5 s se reconoce una voz de oído y bastan para una muestra.

**Consecuencia:** quien apenas habla en un vídeo no gana voz de ese vídeo. Ver
[Su voz](ayuda:personas#su-voz).

## Revisión de las propuestas por la IA

**Qué:** antes de enseñártelas, la IA revisa todas las propuestas de un vídeo juntas y descarta lo que es
contenido de esa reunión o repite otra propuesta. Lo descartado no se pierde: queda en **Descartadas por la
IA**, con su motivo y **Recuperar**.

**Por qué:** la extracción, fragmento a fragmento, proponía lo que se explicaba en la reunión como datos
de quien lo explicaba («Sabe que la regla del 72…») y términos sin valor para el perfil. Pedírselo con más
fuerza en el mismo prompt no bastaba, y una regla fija por palabras («Sabe que…») quitaría también datos
buenos.

**Consecuencia:** la IA revisa con su **modo razonamiento**, que tarda unos 3 minutos por cada
{{v:aprender_juicio_tanda}} propuestas (de 3 a 7 minutos por vídeo en una tutoría de 40–50 minutos). Sin
razonar era más rápido, pero el resultado cambiaba de una vez a otra. Aun así no es perfecta: a veces
descarta algo cierto (por eso puedes **recuperarlo**) o deja pasar algo dudoso. Lo que sale de tus
correcciones no lo juzga. Si la revisión falla, se enseñan todas.

## Nada se confirma solo

**Qué:** ni los hablantes, ni lo aprendido, ni las identidades deducidas se dan por buenos sin que los
confirmes.

**Por qué:** un error confirmado se refuerza: una huella de voz equivocada haría que la app reconociera mal
a esa persona en todos los vídeos siguientes.
