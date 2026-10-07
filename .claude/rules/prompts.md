---
paths:
  - "backend/app/prompts.py"
  - "backend/app/pipeline/glossary.py"
  - "backend/app/pipeline/correct.py"
  - "backend/app/pipeline/identify.py"
  - "backend/app/pipeline/voice.py"
  - "backend/app/pipeline/analyze.py"
---

# Prompts, glosario e identificación

Lee `docs/ai/AI_PROMPTS.md` antes de editar.

- Prompts en español, genéricos: nunca menciones programas concretos, ni siquiera como ejemplo.
- No inventar: los prompts de análisis componen `ANALYSIS_RULES`. El LLM nunca reescribe la
  transcripción; solo acepta o rechaza sustituciones concretas.
- Si cambias claves de un `*_SCHEMA`, actualiza `export.py`, `services.py`, `frontend/src/api.ts` y
  `VideoDetail.tsx`.
- Los umbrales de voz y glosario tienen tests en `backend/tests/test_logic.py`.
