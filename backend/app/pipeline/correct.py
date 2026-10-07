"""Fase 8: corrección conservadora de términos del glosario.

- Variantes declaradas en el perfil y cambios de mayúsculas: se aplican directamente.
- Parecidos fonéticos: los valida el modelo de lenguaje uno a uno (ante la duda, no se cambia).
Se guarda el texto original de cada intervención modificada para poder revisarlo.
"""

from __future__ import annotations

from dataclasses import asdict

from ..knowledge import effective_glossary
from ..llm import LLMServer
from ..prompts import CORRECT_SCHEMA, CORRECT_SYSTEM
from .base import JobContext
from .glossary import apply_candidates, find_candidates

BATCH = 25


def run(ctx: JobContext, llm: LLMServer) -> None:
    utts = ctx.load("utterances.json")
    glossary = effective_glossary(ctx.profile)
    if not glossary:
        ctx.save("corrected.json", [{**u, "original_text": "", "corrections": []} for u in utts])
        return

    cands = find_candidates([u["text"] for u in utts], glossary)
    # Lo declarado por el usuario se aplica directamente; lo aprendido y lo fonético lo valida el LLM
    for c in cands:
        if c.kind in ("variante", "mayusculas") and c.trusted:
            c.accepted = True
    fuzzy = [c for c in cands if c.accepted is None]
    if fuzzy:
        ctx.report(0.1, f"Validando {len(fuzzy)} posibles términos mal transcritos")
        llm.start()
        definitions = {g["term"]: g.get("definition", "") for g in glossary}
        for b in range(0, len(fuzzy), BATCH):
            ctx.check_cancel()
            batch = fuzzy[b : b + BATCH]
            lines = []
            for i, c in enumerate(batch):
                d = definitions.get(c.suggestion) or ""
                lines.append(f'{i}. Término: "{c.suggestion}"{f" ({d})" if d else ""}\n   Texto: {c.context}')
            r = llm.chat_json(CORRECT_SYSTEM, "Propuestas:\n\n" + "\n\n".join(lines), CORRECT_SCHEMA, max_tokens=2000,
                              temperature=0.0)
            for dec in r.get("decisiones", []):
                if 0 <= dec.get("id", -1) < len(batch):
                    batch[dec["id"]].accepted = bool(dec.get("aceptar"))
            ctx.report(0.1 + 0.9 * min(1, (b + BATCH) / len(fuzzy)), "Validando términos")

    out = []
    for i, u in enumerate(utts):
        mine = [c for c in cands if c.segment == i and c.accepted]
        if mine:
            out.append({**u, "text": apply_candidates(u["text"], mine), "original_text": u["text"],
                        "corrections": [{k: v for k, v in asdict(c).items() if k in ("original", "suggestion", "kind", "score")}
                                        for c in mine]})
        else:
            out.append({**u, "original_text": "", "corrections": []})
    ctx.save("corrected.json", out)
    n = sum(len(u["corrections"]) for u in out)
    ctx.report(1.0, f"{n} términos corregidos")
