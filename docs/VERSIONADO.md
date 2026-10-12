# Versionado y publicación de versiones

## Números de versión

El proyecto sigue el [versionado semántico](https://semver.org/lang/es/) con números `MAYOR.MENOR.PARCHE`:

| Sube… | Cuándo | Ejemplo |
|---|---|---|
| **MAYOR** (`2.0.0`) | Cambios incompatibles: la base de datos o la carpeta de resultados cambian de forma que hay que migrar o volver a procesar, se quita una función o cambian los requisitos (otro modelo, otra GPU) | Nuevo formato de `analisis.json` |
| **MENOR** (`1.1.0`) | Funciones nuevas compatibles con lo existente | Exportar a DOCX, un nuevo filtro en la biblioteca |
| **PARCHE** (`1.0.1`) | Correcciones de errores y ajustes menores sin funciones nuevas | Arreglar un fallo al publicar, mejorar un prompt |

La versión vive en un único sitio: el fichero [`VERSION`](../VERSION) de la raíz. El backend la lee al
arrancar, la expone en `/api/status` y la web la muestra en la barra lateral. El script de publicación
copia ese número a `backend/pyproject.toml`, `backend/uv.lock` y `frontend/package*.json`.

Cada versión publicada tiene un **tag anotado** `vX.Y.Z` en git y una **release** en GitHub con sus notas.

## Flujo de trabajo para una nueva función

1. Crea una rama desde `main`:

   ```powershell
   git switch -c feature/exportar-docx
   ```

2. Haz el desarrollo con commits pequeños y descriptivos.
3. Antes de terminar, añade una línea por cambio en la sección **`## [Sin publicar]`** de
   [`CHANGELOG.md`](../CHANGELOG.md). Usa el apartado que corresponda:

   | Apartado | Para |
   |---|---|
   | `### Añadido` | funciones nuevas |
   | `### Cambiado` | cambios en funciones existentes |
   | `### Obsoleto` | funciones que se quitarán pronto |
   | `### Eliminado` | funciones quitadas |
   | `### Corregido` | errores arreglados |
   | `### Seguridad` | vulnerabilidades |

   Escribe para quien usa la app (qué puede hacer ahora o qué ha cambiado), no para quien lee el código.

4. Comprueba que todo sigue funcionando:

   ```powershell
   cd backend;  uv run pytest
   cd ../frontend;  npm run build
   ```

5. Fusiona en `main`:

   ```powershell
   git switch main
   git merge --no-ff feature/exportar-docx
   ```

Si la versión cambia la interfaz, antes de publicar comprueba que la ayuda de la app
(`frontend/src/help/`) está al día y rehaz las capturas:

```powershell
cd backend;  uv run python ../scripts/help_screenshots.py
```

## Publicar una versión

Desde `main`, con el árbol de trabajo limpio:

```powershell
python scripts/release.py minor --dry-run   # muestra la versión resultante y sus notas
python scripts/release.py minor --push      # o patch / major / 1.2.0
```

El script:

1. Comprueba que estás en `main`, que no hay cambios pendientes y que «Sin publicar» tiene entradas.
2. Calcula la nueva versión y la escribe en todos los ficheros.
3. Convierte «Sin publicar» en `## [X.Y.Z] - AAAA-MM-DD` y actualiza los enlaces de comparación.
4. Crea el commit `Versión X.Y.Z` y el tag anotado `vX.Y.Z`.
5. Con `--push`, sube `main` y el tag, y crea la release de GitHub con `gh`.

Sin `--push` todo queda en local. Para subirlo después:
`git push origin main --follow-tags` y luego `gh release create vX.Y.Z --notes-from-tag`.

## Consultar versiones

```powershell
git tag -n                          # versiones con su título
git show v1.0.0                     # notas y commit de una versión
git log v1.0.0..v1.1.0 --oneline    # commits entre dos versiones
git switch --detach v1.0.0          # usar una versión anterior (git switch main para volver)
```

En GitHub: pestaña **Releases** del repositorio, o el enlace de comparación de cada versión en el
CHANGELOG.

## Dos versiones seguidas

Si preparas una versión de arreglos y otra con funciones (por ejemplo, 1.6.1 y 1.7.0), publica la primera
**antes** de fusionar la segunda en `main`:

1. Fusiona la rama de arreglos y ejecuta `release.py patch` (crea su commit «Versión X.Y.Z» y su tag).
2. Después, fusiona la rama de funciones y ejecuta `release.py minor`.

`release.py` publica siempre el estado actual de `main`. Si ya has fusionado las dos, la primera no puede
tener su propio commit de versión sin reescribir `main`, y eso no se hace. Así pasó con la 1.6.1: quedó
como un tag en su fusión (donde `VERSION` aún dice 1.6.0) y sus notas van dentro de la 1.7.0.
