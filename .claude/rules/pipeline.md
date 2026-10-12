---
paths:
  - "backend/app/pipeline/**"
  - "backend/app/worker.py"
  - "backend/app/llm.py"
  - "backend/app/media.py"
---

# Pipeline y worker

Antes de cambiar nada aquí, lee `docs/ai/AI_PIPELINE.md` (fases, ficheros de trabajo y reanudación) y
`docs/ai/AI_MODELS_GPU.md` (VRAM y modelos).

- Nunca debe haber dos modelos grandes en la GPU a la vez: `llm.stop()` antes de cargar torch, y
  `del modelo` + `free_gpu()` al terminar.
- Lee y escribe con `ctx.load`/`ctx.save`, informa del progreso con `ctx.report(0..1, msg)` y llama
  a `ctx.check_cancel()` en los bucles.
- Si cambia el formato de un JSON intermedio, ten en cuenta los trabajos a medias en `data/work/`.
- Las pruebas de punta a punta van en una instancia aislada (`:8771`, `llm_port` 8092), con
  «Aplicar y continuar» para llegar a `follow` y `learn`, y al terminar se para también su llama-server
  (ver «Prueba de punta a punta» en `docs/ai/AI_PIPELINE.md`).
