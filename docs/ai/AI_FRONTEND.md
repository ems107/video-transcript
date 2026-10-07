# Frontend

React 19, Vite, TypeScript, react-router-dom, react-markdown y remark-gfm. No se usa ninguna librería
de componentes ni de estado: solo `useState`/`useEffect` y CSS propio.

## Estructura

| Fichero | Contenido |
|---|---|
| `src/App.tsx` | barra lateral, rutas, aviso de componentes que faltan (`CHECK_LABELS`) y la versión |
| `src/api.ts` | **tipos de todas las respuestas** y el cliente `api.get/post/put/del` (lanza `Error(detail)`) |
| `src/util.ts` | `fmtTs`, `fmtDuration`, `fmtDate` (es-ES), `parseTs`, `useJobs()` (SSE), `STATUS_LABEL`, `speakerColor`, `notifyKnowledge()` |
| `src/knowledge.tsx` | componentes del conocimiento aprendido: `ProposalList`/`ProposalCard` (con evidencia), `KnowledgeList` (aceptado, editar y retirar) y `VersionHistory` (restaurar) |
| `src/index.css` | variables de diseño en `:root`, modo oscuro con `prefers-color-scheme` y clases de utilidad |
| `src/pages/*.tsx` | una página por ruta (ver abajo) |

Rutas: `/` Biblioteca, `/nuevo`, `/cola`, `/videos/:id` (`?t=segundos&tab=resumen\|transcripcion\|tareas\|pantalla`),
`/propuestas` (`?video=id`), `/buscar`, `/perfiles`, `/perfiles/:id` (`?tab=manual\|aprendido\|propuestas\|historial`),
`/personas`, `/personas/:id` (`?tab=ficha\|propuestas\|historial`), `/ajustes`. Las rutas de la interfaz
están en español.

## Reglas

- **Los tipos de `api.ts` deben reflejar lo que devuelve el backend.** Si cambias una respuesta en
  `main.py`, actualiza aquí su tipo. `npm run build` ejecuta `tsc -b` y detecta los usos rotos.
- `Analysis` y sus listas pueden venir incompletos en vídeos antiguos. Usa siempre `?.` y `?? []`.
- Todos los textos visibles van en español y no mencionan programas concretos.
- **Estilos:** usa las variables (`var(--accent)`, `--surface`, `--text-2`…) y nunca colores fijos,
  porque el modo oscuro se basa en ellas. Clases que ya existen: `card pad stack`, `row`, `spread`,
  `grid2`, `field`, `check`, `muted small`, `pill`/`pill warn`, `error-box`, `notice`, `tbl`,
  `tabs`, y en botones `primary`, `sm` y `danger`. Reutilízalas antes de crear otras nuevas. Los
  colores de cada hablante salen de `speakerColor(order)`.
- **Marcas de tiempo:** en el Markdown del resumen, `linkTimestamps()` convierte `[hh:mm:ss]` en enlaces
  `#t=<s>`, y `seek(t)` mueve el reproductor. Usa `TsLink` para mostrar una marca suelta.
- El progreso de los trabajos llega solo por SSE (`useJobs`, en `App.tsx`, pasado como prop). No
  hagas polling.
- Después de cualquier acción que cambie el conocimiento (decidir, editar, retirar, confirmar
  hablantes, fusionar o restaurar), llama a `notifyKnowledge()`. Así se recargan el contador de la
  barra lateral y las listas abiertas, que escuchan el evento `knowledge-changed`.
- `knowledge.tsx` solo exporta componentes. Las funciones compartidas van en `util.ts`, porque oxlint
  avisa con `only-export-components`.
- Formularios: al hacer clic, `setBusy(true)`, y los errores se muestran en `<div className="error-box">`.
  Las confirmaciones destructivas usan `confirm(...)`.

## Desarrollo y build

- `npm run dev` arranca en :5173 y redirige `/api` al backend en :8770 (`vite.config.ts`). Hace falta
  tener el backend arrancado.
- `npm run build` genera `frontend/dist`, que FastAPI sirve en :8770. `run.ps1` solo recompila si
  falta `dist` o si se pasa `-Rebuild`. Tras cambiar el frontend, avisa al usuario de que ejecute
  `.\run.ps1 -Rebuild`.
- `npm run lint` (oxlint) avisa de `set-state-in-effect` en `Search.tsx`. Es un aviso conocido, no un
  error.
