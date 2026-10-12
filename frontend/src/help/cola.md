---
titulo: La cola
seccion: Empezar
orden: 3
claves: cola, progreso, cancelar, reintentar, error, reanudar, fases
---
La **Cola** muestra los vídeos en proceso y los terminados, con la fase en la que va cada uno y su
progreso. La barra lateral indica cuántos hay en marcha.

![La cola de procesamiento](captura:cola)

- Los vídeos se procesan **de uno en uno**: la tarjeta gráfica solo puede tener un modelo grande cargado a
  la vez.
- **Cancelar** detiene un análisis. **Reintentar** lo vuelve a lanzar desde la fase donde se quedó, sin
  repetir lo ya hecho.
- Si cierras la app a mitad de un análisis, al volver a abrirla **continúa donde se quedó**.
- Los trabajos cortos van **primero**: aplicar la revisión de un vídeo, rehacer un seguimiento o aprender de
  nuevo. Si en ese momento se está analizando otro vídeo, queda **en pausa** al terminar la fase en curso y
  sigue después.
- **En espera**: el vídeo ya hizo lo más pesado y espera a que [revises](ayuda:revision#los-videos-siguientes-esperan)
  otro vídeo del mismo perfil o seguimiento encolado antes. **Revisar el otro vídeo** te lleva a él.
- Si algo falla, el vídeo queda en «Error». Pulsa **Detalles** para ver el mensaje (útil si me lo tienes
  que contar) y **Reintentar** cuando lo hayas resuelto.

Las fases, en orden, se explican en [Cómo funciona](ayuda:como-funciona).

:::tecnico Reanudación y fases repetidas
Cada fase deja un fichero `<fase>.done` en `data/work/job_<n>/`. Al reanudar, las fases con su marca se
saltan, y las largas (pantalla, resumen, aprendizaje) guardan su progreso parcial. «Regenerar» borra las
marcas de las fases que hay que repetir (ver [Regenerar](ayuda:regenerar)). La fase de aprendizaje es «de
mejor esfuerzo»: si falla, el vídeo se publica igual.
:::
