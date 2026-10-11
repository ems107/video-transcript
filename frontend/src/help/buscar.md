---
titulo: Buscar
seccion: Otros
orden: 30
claves: buscar, búsqueda, encontrar, frase exacta, filtrar
---
**Buscar** encuentra palabras en todos los vídeos a la vez: transcripciones, resúmenes, títulos y lo que
se vio en pantalla. Cada resultado enlaza al momento exacto del vídeo.

![La búsqueda](captura:buscar)

- No distingue mayúsculas ni tildes: «reunion» encuentra «Reunión».
- Entre comillas busca la frase exacta: `"plan de pruebas"`.
- Puedes filtrar por perfil y por persona.

:::tecnico Cómo funciona
Es un índice de texto completo de SQLite (FTS5) con eliminación de tildes. Se actualiza al publicar un
vídeo y cada vez que cambian sus nombres o su transcripción (al confirmar hablantes, cambiar quién habla
o fusionar personas).
:::
