# Frontend

React 19, Vite, TypeScript, react-router-dom, react-markdown y remark-gfm. No se usa ninguna librería
de componentes ni de estado: solo `useState`/`useEffect` y CSS propio.

## Estructura

| Fichero | Contenido |
|---|---|
| `src/App.tsx` | barra lateral, rutas, aviso de componentes que faltan (`CHECK_LABELS`) y la versión |
| `src/api.ts` | **tipos de todas las respuestas** y el cliente `api.get/post/put/del` (lanza `Error(detail)`) |
| `src/util.ts` | `fmtTs`, `fmtDuration`, `fmtDate` (es-ES), `parseTs`, `useJobs()` (SSE), `STATUS_LABEL`, `speakerColor`, `notifyKnowledge()`, `plural`, y de los hablantes con dos voces `currentPerson` y `splitOthers` |
| `src/knowledge.tsx` | componentes del conocimiento aprendido: `ProposalList`/`ProposalCard` (con evidencia), `KnowledgeList` (aceptado, editar y retirar) y `VersionHistory` (restaurar) |
| `src/help/*.md`, `src/help/index.ts` | páginas de la ayuda (cabecera `titulo/seccion/orden/claves`) y su carga con `import.meta.glob` |
| `src/HelpMarkdown.tsx` | visor de la ayuda: bloques `:::tecnico Título` … `:::` (plegables, estilo propio), valores `{{v:clave}}`, enlaces `ayuda:pagina#ancla`, imágenes `captura:nombre`; y `HelpLink` (el «?» de cada pantalla) |
| `src/pages/Help.tsx` | `/ayuda/:pagina`: índice por secciones, buscador, índice de la página, interruptor de detalles técnicos (en `localStorage`), anterior/siguiente; «Novedades» añade el CHANGELOG |
| `src/RegenerateDialog.tsx` | ventana «Regenerar el análisis»: qué se repite y qué se conserva, una casilla por nivel (encadenadas) y la estimación |
| `src/SpeakerFix.tsx` | `SpeakerFixDialog` (cambiar quién habla en una línea, en parte de ella eligiendo palabras, o en varias líneas), `SplitDialog` (asignar cada grupo de un hablante con dos voces; trae elegida la persona que propone la voz, `suggested`) y `OverridesList` (cambios manuales con Deshacer) |
| `src/CorrectionsPanel.tsx` | tarjeta «Correcciones» del vídeo: añadir, editar y borrar; estado «Aplicada/Pendiente» por corrección (`applied`) y aviso de las que faltan por aplicar. El texto de ayuda explica que el análisis se reescribe de cero: cada corrección debe entenderse sola |
| `src/followup.ts` | constantes de los seguimientos: estados por tipo de punto (iguales que `backend/app/followups.py`), títulos y nombres de los eventos |
| `src/FollowupsPanel.tsx` | tarjeta «Seguimientos» del vídeo con sus ventanas (añadir, `DetachDialog` para quitar), `FollowupChoice` (la pregunta «rehacer el estado / dejarlo como está», también en regenerar y quitar) y `EventChip` (un hito del recorrido, con enlace al vídeo en ese momento) |
| `src/RemoveDialog.tsx` | ventana «Quitar el vídeo» (`<dialog>` con casillas; pide `videos/{id}/removal` para mostrar las rutas) |
| `src/index.css` | variables de diseño en `:root`, modo oscuro con `prefers-color-scheme` y clases de utilidad |
| `src/pages/Review.tsx` | pantalla «Revisar este vídeo» (pasos 1 y 2) y, exportados para `VideoDetail`, `ApplyButton` («Aplicar y continuar» con su estimación) y `ReviewBanner` (la franja del estado de la revisión) |
| `src/pages/*.tsx` | una página por ruta (ver abajo); `PersonDetail` incluye `VoiceCard` (huellas, dudosas y muestras de voz) |

Rutas: `/` Biblioteca, `/nuevo`, `/cola`, `/videos/:id` (`?t=segundos&tab=resumen\|transcripcion\|tareas\|pantalla`),
`/videos/:id/revisar`,
`/propuestas` (`?video=id`), `/buscar`, `/perfiles`, `/perfiles/:id` (`?tab=manual\|aprendido\|propuestas\|historial`),
`/personas`, `/personas/:id` (`?tab=ficha\|propuestas\|historial`), `/seguimientos`, `/seguimientos/:id`
(`?tab=estado\|videos\|historial`), `/ajustes`, `/ayuda[/:pagina]`. Las rutas de la interfaz
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
- **No abras más conexiones largas** (SSE o similares). El navegador solo permite 6 conexiones por
  servidor (HTTP/1.1). `useJobs` cierra el SSE al ocultar o abandonar la página (`visibilitychange` y
  `pagehide`); sin eso, las páginas en segundo plano bloqueaban la web.
- Después de cualquier acción que cambie el conocimiento (decidir, editar, retirar, confirmar
  hablantes, fusionar o restaurar), llama a `notifyKnowledge()`. Así se recargan el contador de la
  barra lateral y las listas abiertas, que escuchan el evento `knowledge-changed`.
- Un `.tsx` solo exporta componentes (`knowledge.tsx`, `SpeakerFix.tsx`…). Las funciones compartidas van
  en `util.ts`, porque oxlint avisa con `only-export-components`.
- Formularios: al hacer clic, `setBusy(true)`, y los errores se muestran en `<div className="error-box">`.
  Las confirmaciones destructivas usan `confirm(...)`.

## Desarrollo y build

- `npm run dev` arranca en :5173 y redirige `/api` al backend en :8770 (`vite.config.ts`). Hace falta
  tener el backend arrancado.
- `npm run build` genera `frontend/dist`, que FastAPI sirve en :8770. `run.ps1` solo recompila si
  falta `dist` o si se pasa `-Rebuild`. Tras cambiar el frontend, avisa al usuario de que ejecute
  `.\run.ps1 -Rebuild`.
- **`frontend/dist` es el que sirve la instancia del usuario.** Compilar en una rama con `npm run build`
  cambia su web aunque su backend sea otro. Para comprobar una rama: `npx tsc -b` y
  `npx vite build --outDir <scratchpad>\dist-check --emptyOutDir`, y para verla, la instancia de prueba con
  `VT_FRONTEND_DIST=<scratchpad>\dist-check`. Si `dist` ya se sobrescribió, rehazlo
  desde `main` (un `git worktree` de `main` con `node_modules` enlazado y `vite build --outDir` al `dist`
  del repositorio).
- Los errores de JavaScript se mandan al registro del servidor (`main.tsx`, `POST /api/client-log`). Un
  error de la API se lanza como `ApiError` (`api.ts`) y no se reenvía.
- `npm run lint` (oxlint) avisa de `set-state-in-effect` en `Search.tsx`. Es un aviso conocido, no un
  error.

## Revisión visual (Chrome headless + CDP)

`npm run build` no detecta fallos visuales ni bloqueos. Para cambios de interfaz:
1. Usa una instancia aislada (`VT_DATA_DIR`, puerto 8771; ver `AI_PIPELINE.md`).
2. Reutiliza los ayudantes de `scripts/help_screenshots.py` desde un script propio (`import
   help_screenshots as H` con `scripts/` en `sys.path`): `H.start_chrome`, `H.CDP`, `H.go`, `H.click_text` y
   `H.shoot` (captura de la página o de un elemento). Cambia `H.OUT` a una carpeta del scratchpad.
3. Si lo haces a mano: `chrome.exe --headless=new --remote-debugging-port=<puerto> --user-data-dir=<scratchpad>\chrome-cdp`
   y, desde Python (`websockets`, en el venv del backend), `Page.navigate` y `Page.captureScreenshot`.
4. Recoge los errores con `Runtime.exceptionThrown` y `Log.entryAdded`.
5. Prueba también el modo claro y el oscuro (`Emulation.setEmulatedMedia`) y un ancho de unos 420 px.
6. Navega muchas veces seguidas para detectar bloqueos.
7. Limpia la caché del navegador (`Network.clearBrowserCache`) después de recompilar.

## Ayuda de la app

- **Contenido:** una página Markdown por tema en `frontend/src/help/`, escrita para el usuario. Lo
  técnico va en bloques `:::tecnico Título` … `:::` y nunca es necesario para usar la app.
- **Valores en vivo:** `{{v:clave}}` se sustituye por el valor de `GET /api/help/values`
  (`backend/app/help_values.py`, que lee ajustes y constantes de su sitio). Si añades una clave, regístrala
  allí.
- **Anclas:** `slugify` del encabezado (sin tildes, minúsculas, guiones), igual en `help/index.ts` y en
  `tests/test_help.py`.
- **react-markdown** descarta por seguridad los esquemas desconocidos: `HelpMarkdown` usa
  `urlTransform={(url) => url}` para dejar pasar `ayuda:` y `captura:` (el contenido es nuestro).
- **Capturas:** `frontend/public/capturas/*.png`, generadas por `scripts/help_screenshots.py` (instancia
  aislada, vídeos de muestra, Chrome por CDP; sustituye las rutas reales por `C:\Usuarios\Ana\…` antes de
  capturar, porque se publican en el repositorio). Necesita la GPU libre y unos 10 minutos.
- **Tests (`test_help.py`):** cabeceras, `{{v:…}}` existentes, enlaces y anclas, bloques técnicos
  cerrados y capturas presentes.
