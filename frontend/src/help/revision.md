---
titulo: Revisar un vídeo
seccion: Cada vídeo
orden: 15
claves: revisar, revisión, aplicar, continuar, pendiente, espera, en espera, dudoso, decidir
---
Cuando la app termina de analizar un vídeo, lo deja **pendiente de revisar**. Hasta que lo revisas, el vídeo
no cuenta para lo demás:
- no actualiza sus [seguimientos](ayuda:seguimientos);
- no propone nada para el perfil ni para las personas ([propuestas](ayuda:propuestas));
- no guarda las voces de sus hablantes.

Así, lo que se guarda sale de un vídeo que ya has comprobado: si un hablante estaba mal o el resumen
entendió algo al revés, se corrige antes de que llegue al perfil o al seguimiento.

La página del vídeo lo avisa con una franja arriba. **Paso a paso** abre la pantalla **Revisar este vídeo**,
con todo lo que hay que mirar en orden.

![La franja de un vídeo pendiente de revisar](captura:video-revision)

## Paso 1: comprueba el vídeo

1. **Hablantes**: confirma las propuestas correctas y cambia las que no ([Hablantes](ayuda:hablantes)).
2. **Transcripción**: si una frase es de otra persona, pulsa su nombre
   ([cambiar quién habla](ayuda:hablantes#cambiar-quien-habla)). Empieza por los tramos con **voz dudosa**.
3. **Resumen y tareas**: lo que esté mal, escríbelo en [Correcciones](ayuda:correcciones).

Después pulsa **Aplicar y continuar**. Si no has cambiado nada, el botón dice **Dar por revisado y
continuar**. Un trabajo en la [cola](ayuda:cola):
- rehace el resumen con tus correcciones y tus cambios de quién habla, si los hay;
- guarda la voz de cada persona confirmada;
- actualiza los seguimientos del vídeo;
- propone lo que se ha aprendido.

La franja dice qué cambios hay sin aplicar y cuánto tardará.

## Paso 2: decide lo dudoso

Al terminar, la pantalla muestra lo que la IA no ha podido decidir sola:

- **Puntos del seguimiento que parecen repetir otro.** Por ejemplo, «Enviar la documentación del seguro»
  cuando ya existe «Enviar la póliza de vida». **Sí, es lo mismo** lo borra (y la IA no lo vuelve a
  crear); **No, es distinto** lo deja.
- **Cambios de estado sin frase que los demuestre.** La IA cree que una tarea quedó hecha, pero no
  encuentra la frase que lo diga. **Sí, confirmar** o **No pasó**.
- **Propuestas para el perfil y las personas**, como en [Propuestas](ayuda:propuestas).

![La pantalla Revisar este vídeo, con lo que queda por decidir](captura:revision)

Cuando no queda nada por decidir, el vídeo queda **revisado**.

## Los vídeos siguientes esperan

Si encolas varios vídeos del mismo perfil o del mismo seguimiento, cada uno hace lo más pesado (la
pantalla, la transcripción y la separación de voces) y **espera** a que revises los anteriores antes de
identificar a los hablantes y resumir. En la cola aparece **En espera**, con un enlace al vídeo que falta
por revisar.

Así el vídeo siguiente ya reconoce las voces que confirmaste, escribe bien los términos que aceptaste y
continúa el seguimiento revisado. Un vídeo sin relación con los demás (otro perfil y ningún seguimiento
en común) no espera.

:::tecnico Por qué espera ahí y no antes
La espera va antes de identificar a los hablantes, porque ahí se usan las voces, y antes de corregir los
términos y resumir, porque ahí se usan el glosario, las personas y el estado del seguimiento. El análisis
de la pantalla y la transcripción usan el perfil tal como esté en ese momento: esperar también por ellas
añadiría unos 30–45 minutos por vídeo, y lo que se pierde es poco, porque la corrección de términos, que
va después de la espera, ya usa el glosario revisado.

Solo esperan los vídeos encolados después del que falta por revisar. No bloquea un vídeo que falló o se
canceló antes de analizarse.
:::

## Cambios después de revisar

Si cambias algo de un vídeo ya revisado (una corrección, quién habla o quién es un hablante), vuelve a
quedar **pendiente**: pulsa **Aplicar y continuar** para que el resumen, las voces, el seguimiento y lo
aprendido lo tengan en cuenta. Lo mismo pasa al [regenerar el análisis](ayuda:regenerar).

Los vídeos analizados antes de esta versión se dan por revisados.
