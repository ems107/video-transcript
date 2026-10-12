---
titulo: Correcciones
seccion: Cada vídeo
orden: 12
claves: corregir, corrección, resumen mal, error, hecho, aplicada, pendiente
---
Las **correcciones** son para lo que el análisis ha **interpretado mal**: quién hace una tarea, a quién se
refiere un apodo, qué se decidió… Las escribes tú en la tarjeta **Correcciones** de la página del vídeo.

![La tarjeta de correcciones](captura:correcciones)

## Cómo funcionan

- Escribir una corrección **no cambia nada al momento**: se guarda con el vídeo. Aparece como
  **Pendiente** y la tarjeta avisa de que hay correcciones sin aplicar.
- Al [regenerar el análisis](ayuda:regenerar), la IA recibe todas las correcciones del vídeo como
  **hechos verificados que prevalecen** sobre lo que parezca decir la grabación. Pasan a **Aplicada**.
- **Se aplican en cada regeneración.** Mantenlas aunque el resumen ya salga bien: la IA vuelve a escribir
  el análisis desde cero y, sin la corrección, podría repetir el error.
- La IA nunca escribe ni modifica las correcciones.

## Cómo escribirlas

La IA **no ve el análisis anterior**: lo escribe de nuevo a partir de la grabación. Por eso cada
corrección tiene que ser un **hecho sobre lo que ocurre en el vídeo**, que se entienda por sí solo, y no
una referencia al texto del resumen.

| Funciona | No funciona |
|---|---|
| «El informe de costes lo prepara María, no Juan» | «La segunda tarea está mal asignada» |
| «"Selu" es el apodo de José Luis Pérez, no de Sandra» | «En el resumen pone mal quién es Selu» |
| «No se acordó ninguna fecha de entrega» | «Quita la fecha del punto 3» |

## Qué arreglan y qué no

| Lo que está mal | Dónde se arregla |
|---|---|
| Lo que la IA interpreta del contenido | **Correcciones** |
| Quién es un hablante | [Panel Hablantes](ayuda:hablantes#confirmar-y-cambiar) (así también se guarda su voz) |
| Quién dice una frase concreta | [Cambiar quién habla](ayuda:hablantes#cambiar-quien-habla) |
| Una palabra mal transcrita (por ejemplo, un nombre de producto) | [Glosario del perfil](ayuda:perfiles#glosario) |

Las correcciones afectan al resumen, a las tareas y a lo que se aprende del vídeo, **no al texto de la
transcripción**.

:::tecnico Cómo llegan a la IA
Se añaden como un bloque propio («Notas del usuario sobre este vídeo. Son hechos verificados y prevalecen
sobre lo que parezca decir la transcripción o la pantalla…») al contexto del resumen de cada bloque, del
informe final y del aprendizaje. El bloque aclara que no son parte de la grabación: la IA no debe
atribuírselas a nadie ni contarlas como algo que se dijo en la reunión. El análisis guarda con qué correcciones se generó (su
identificador y su fecha de modificación); así la web sabe cuáles están aplicadas. Se incluyen en la
[copia de recuperación](ayuda:quitar#copia-de-recuperacion).
:::
