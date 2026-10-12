---
paths:
  - "backend/app/prompts.py"
  - "backend/app/pipeline/glossary.py"
  - "backend/app/pipeline/correct.py"
  - "backend/app/pipeline/identify.py"
  - "backend/app/pipeline/voice.py"
  - "backend/app/pipeline/analyze.py"
  - "backend/app/pipeline/learn.py"
  - "backend/app/knowledge.py"
---

# Prompts, glosario e identificación

Lee `docs/ai/AI_PROMPTS.md` antes de editar.

- Prompts en español, genéricos: nunca menciones programas concretos, ni siquiera como ejemplo.
- No inventar: los prompts de análisis componen `ANALYSIS_RULES`. El LLM nunca reescribe la
  transcripción; solo acepta o rechaza sustituciones concretas.
- Si cambias claves de un `*_SCHEMA`, actualiza `export.py`, `services.py`, `frontend/src/api.ts` y
  `VideoDetail.tsx`.
- Los umbrales de voz, glosario y unificación de nombres tienen tests en `backend/tests/test_logic.py`;
  las identidades por contexto, en `test_identities.py`. El aprendizaje, en
  `test_knowledge.py` y `test_learn.py`.
- Aprendizaje: la IA solo propone. Toda propuesta se verifica en Python (evidencia real, no
  inventada ni puntual). Lo aprendido nunca corrige la transcripción sin validación del LLM
  (`trusted=False`), salvo las correcciones de transcripción aceptadas (`kind = correccion`): el usuario
  las aceptó viendo dónde se oyen, como una variante manual del glosario.
