"""Fase 10: propuestas de conocimiento para el perfil y las personas.

El LLM lee la transcripción por bloques y propone términos, hechos del negocio y datos de personas.
Todo se comprueba aquí contra la transcripción y la pantalla antes de guardarse como propuesta: lo que
no aparece se descarta. El usuario acepta o rechaza cada propuesta en la web.
"""

from __future__ import annotations

from typing import Any

from .. import knowledge as K
from ..llm import LLMServer
from ..prompts import (
    LEARN_SCHEMA,
    LEARN_SYSTEM,
    SCREEN_SCHEMA,
    SCREEN_SYSTEM,
    corrections_block,
    learn_user,
    profile_block,
    screen_user,
)
from .analyze import chunk_lines, timeline
from .base import JobContext
from .glossary import normalize
from .transcript import fmt_ts

# Solo protegen frente a respuestas anómalas (un bucle de la IA): un vídeo normal no se acerca a ellos.
# Lo que limita el ruido son las comprobaciones de cada propuesta, no el número.
MAX_TERMS = 40
MAX_CONTEXT = 30
MAX_PER_PERSON = 40
MAX_NEW_PEOPLE = 15
MAX_SECTIONS = 8
SCREEN_BATCH = 12  # términos por consulta al valorar los vistos solo en pantalla


def known_block(profile: dict[str, Any] | None, people: list[dict[str, Any]]) -> str:
    """Lo ya aceptado, con su número, para que el LLM no lo repita y pueda proponer reemplazos."""
    lines = []
    for it in (profile or {}).get("learned") or []:
        if it["kind"] in ("termino", "contexto"):
            cat = K.CATEGORY_LABELS.get(it.get("category", ""), "")
            lines.append(f"- [#{it['id']}] {f'({cat}) ' if cat else ''}{K.item_text(it['kind'], it['data'])}")
    for p in K.prompt_people(people):
        facts = "; ".join(f"[#{f['id']}] ({K.CATEGORY_LABELS.get(f['category'], f['category'])}) {f['text']}"
                          for f in p.get("facts") or [])
        if facts:
            lines.append(f"- {p['name']}: {facts}")
    return "\n".join(lines)


def evidence_lines(t: float, utts: list[dict[str, Any]], vision: list[dict[str, Any]],
                   term: str = "") -> list[dict[str, Any]]:
    """Transcripción alrededor de `t`; la pantalla solo si muestra el término (o si no hay habla)."""
    lines = K.excerpt_at(utts, t, max_lines=3)
    frame = min(vision, key=lambda v: abs(v["t"] - t), default=None)
    text = (frame or {}).get("texto_relevante") or ""
    shows_term = bool(term) and f" {normalize(term)} " in f" {normalize(text)} "
    if frame and abs(frame["t"] - t) <= 5 and text.strip() and (shows_term or not lines):
        lines.append({"t": float(frame["t"]), "label": "(pantalla)", "text": text[:400]})
    return sorted(lines, key=lambda x: x["t"])


def looks_like_term(term: str, screen: set[str]) -> bool:
    """Un término del negocio lleva mayúsculas o cifras, o se ha visto escrito en pantalla."""
    return any(c.isupper() or c.isdigit() for c in term) or normalize(term) in screen


def collect_proposals(
    results: list[dict[str, Any]],
    ranges: list[tuple[float, float]],
    utts: list[dict[str, Any]],
    vision: list[dict[str, Any]],
    speaker_names: dict[str, str],
    people: list[dict[str, Any]],
    profile: dict[str, Any] | None,
    screen_names: list[dict[str, Any]],
    want_sections: bool,
    screen_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Convierte las respuestas del LLM en propuestas verificadas, con su dueño y su evidencia."""
    out: list[dict[str, Any]] = []
    known_terms = {normalize(g["term"]) for g in K.effective_glossary(profile)}
    person_names = {normalize(n) for p in people for n in [p["name"], *(p.get("aliases") or [])]}
    person_names |= {normalize(n) for n in speaker_names.values()}
    # Los participantes leídos en pantalla (con todas sus lecturas) son personas, no términos
    person_names |= {normalize(n) for g in screen_names for n in [g.get("canonical", ""), *(g.get("variants") or {})]}
    screen = {normalize(s) for s in screen_terms or []}

    def stamp(ts: str, rng: tuple[float, float]) -> float | None:
        t = K.parse_ts(ts)
        return t if t is not None and rng[0] - 5 <= t <= rng[1] + 5 else None

    # Términos: deben aparecer literalmente; se ordenan por número de apariciones
    terms: dict[str, dict[str, Any]] = {}
    for r in results:
        for x in r.get("terminos", []):
            term = x.get("termino", "").strip()
            k = normalize(term)
            if not k or k in known_terms or k in person_names or k in terms or not looks_like_term(term, screen):
                continue
            occ = K.term_occurrences(term, utts, vision, limit=50)
            if occ:
                terms[k] = {"kind": "termino", "category": "", "owner": ("profile", None), "n": len(occ),
                            "data": {"term": term, "definition": x.get("definicion", "").strip()},
                            "t": occ[0], "lines": evidence_lines(occ[0], utts, vision, term), "replaces": 0,
                            "screen_only": not K.heard(term, utts)}
    # Formas de un mismo nombre: una sola propuesta con la más vista y las demás como otras formas
    merged = []
    for group in K.group_forms([p["data"]["term"] for p in terms.values()]):
        items = sorted((terms[normalize(t)] for t in group), key=lambda p: -p["n"])
        main = items[0]
        if len(items) > 1:
            main["data"]["forms"] = [p["data"]["term"] for p in items[1:]]
            main["data"]["definition"] = main["data"]["definition"] or next(
                (p["data"]["definition"] for p in items[1:] if p["data"]["definition"]), "")
            main["n"] = sum(p["n"] for p in items)
        merged.append(main)
    out += sorted(merged, key=lambda p: -p["n"])[:MAX_TERMS]

    n_ctx = 0
    per_owner: dict[Any, int] = {}
    new_people: set[str] = set()
    seen: set[tuple[Any, str]] = set()
    for r, rng in zip(results, ranges):
        for x in r.get("contexto", []):
            text, t = x.get("texto", "").strip(), stamp(x.get("t", ""), rng)
            k = normalize(text)
            if not k or t is None or n_ctx >= MAX_CONTEXT or (("profile", None), k) in seen or K.is_ephemeral(text):
                continue
            lines = evidence_lines(t, utts, vision)
            if not lines or not K.supported(text, utts, vision, t):
                continue
            seen.add((("profile", None), k))
            n_ctx += 1
            out.append({"kind": "contexto", "category": x.get("categoria", "otro"), "owner": ("profile", None),
                        "data": {"text": text}, "t": t, "lines": lines, "replaces": x.get("reemplaza") or 0})
        for x in r.get("personas", []):
            text, t = x.get("dato", "").strip(), stamp(x.get("t", ""), rng)
            owner = K.resolve_name(x.get("nombre", ""), speaker_names, people)
            k = normalize(text)
            if not k or t is None or owner is None or (owner, k) in seen or K.is_ephemeral(text):
                continue
            if owner[0] == "new":
                owner = ("new", owner[1].strip())
                if normalize(owner[1]) not in new_people and len(new_people) >= MAX_NEW_PEOPLE:
                    continue
            if per_owner.get(owner, 0) >= MAX_PER_PERSON:
                continue
            lines = evidence_lines(t, utts, vision)
            if not lines or not K.supported(text, utts, vision, t):
                continue
            if owner[0] == "new":
                new_people.add(normalize(owner[1]))
            seen.add((owner, k))
            per_owner[owner] = per_owner.get(owner, 0) + 1
            out.append({"kind": "dato", "category": x.get("categoria", "otro"), "owner": owner,
                        "data": {"text": text}, "t": t, "lines": lines, "replaces": x.get("reemplaza") or 0})

    # Otros nombres: cómo aparece en pantalla una persona conocida, si no lo tiene ya. Las variantes de
    # lectura ya están unificadas (fase «names»), y el hablante activo no es fiable para esto
    by_id = {p["id"]: p for p in people}
    for g in screen_names:
        p = by_id.get(g.get("person_id"))
        screen = g.get("screen") or ""
        if p and g.get("readings", 0) >= 2 and normalize(screen) not in {
                normalize(n) for n in [p["name"], *(p.get("aliases") or [])]}:
            out.append({"kind": "alias", "category": "", "owner": ("person", p["id"]), "data": {"name": screen},
                        "t": None, "lines": [], "replaces": 0})

    if want_sections:
        titles: list[str] = []
        for r in results:
            for s in r.get("secciones", []):
                if s.strip() and normalize(s) not in {normalize(x) for x in titles}:
                    titles.append(s.strip())
        out += [{"kind": "seccion", "category": "", "owner": ("profile", None), "data": {"title": s}, "t": None,
                 "lines": [], "replaces": 0} for s in titles[:MAX_SECTIONS]]

    for p in out:
        p.pop("n", None)
        if p["kind"] in ("termino", "contexto", "seccion") and not profile:
            p["drop"] = True
    return [p for p in out if not p.get("drop")]


def run(ctx: JobContext, llm: LLMServer, rejected: list[str], pending: list[str] | None = None,
        sections_pending: bool = False) -> list[dict[str, Any]]:
    utts = ctx.load("corrected.json")
    vision = ctx.load("vision.json", [])
    names = ctx.speaker_names
    profile = ctx.profile
    context = "\n\n".join(filter(None, [profile_block(profile, ctx.people),
                                         corrections_block([c["text"] for c in ctx.corrections])]))
    known = known_block(profile, ctx.people)
    # Secciones solo para un perfil sin ninguna (ni aceptada ni pendiente de revisar)
    want_sections = bool(profile) and not K.effective_sections(profile) and not sections_pending
    exclude = {normalize(g["term"]) for g in K.effective_glossary(profile)}
    exclude |= {normalize(n) for p in ctx.people for n in [p["name"], *(p.get("aliases") or [])]}
    screen_terms = ctx.load("screen_terms.json", [])
    candidates = K.term_candidates(utts, screen_terms, exclude)

    chunks = chunk_lines(timeline(utts, vision, names), ctx.settings.chunk_minutes)
    state = ctx.load("learn.partial.json", {})
    llm.start()
    results, ranges = [], []
    for i, ch in enumerate(chunks):
        ctx.check_cancel()
        start, end = ch[0][0], ch[-1][0]
        if str(i) not in state:
            ctx.report(0.05 + 0.85 * i / len(chunks), f"Aprendiendo del fragmento {i + 1}/{len(chunks)}")
            body = "\n".join(line for _, line in ch)
            state[str(i)] = llm.chat_json(
                LEARN_SYSTEM,
                learn_user(context, known, rejected, candidates, i + 1, len(chunks), fmt_ts(start), fmt_ts(end), body,
                           with_profile=bool(profile), want_sections=want_sections and i == 0, pending=pending),
                LEARN_SCHEMA, max_tokens=4000,
            )
            ctx.save("learn.partial.json", state)
        results.append(state[str(i)])
        ranges.append((start, end))

    proposals = collect_proposals(results, ranges, utts, vision, names, ctx.people, profile,
                                  ctx.load("names.json", []), want_sections, screen_terms)
    proposals = judge_screen_terms(ctx, llm, proposals, vision)
    ctx.save("proposals.json", proposals)
    return proposals


def apply_judgment(proposals: list[dict[str, Any]], answer: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Aplica la valoración de la IA a los términos vistos solo en pantalla.

    «sin_relacion» se descarta (queda en la lista devuelta, que se guarda con el vídeo); «dudoso» se propone
    marcado como dudoso, con su motivo; «relacionado», como siempre, con su motivo. Un término que la IA no
    valora se trata como dudoso: siempre lo decide el usuario."""
    verdicts = {normalize(x.get("termino", "")): x for x in answer.get("terminos") or []}
    kept, judged = [], []
    for p in proposals:
        if not p.pop("screen_only", False):
            kept.append(p)
            continue
        term = p["data"]["term"]
        v = verdicts.get(normalize(term)) or {"relacion": "dudoso", "motivo": "La IA no lo valoró."}
        relacion = v.get("relacion") if v.get("relacion") in ("relacionado", "dudoso", "sin_relacion") else "dudoso"
        judged.append({"termino": term, "relacion": relacion, "motivo": v.get("motivo", "")})
        if relacion != "sin_relacion":
            p["data"]["pantalla"] = {"relacion": relacion, "motivo": v.get("motivo", "")}
            kept.append(p)
    return kept, judged


def judge_screen_terms(ctx: JobContext, llm: LLMServer, proposals: list[dict[str, Any]],
                       vision: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """La IA razona si cada término que solo se ve en pantalla tiene que ver con el vídeo (ver `apply_judgment`)."""
    screen = [p for p in proposals if p.get("screen_only")]
    if not screen:
        return proposals
    answer = ctx.load("screen_judgment.raw.json")
    if answer is None:
        a = ctx.load("analysis.json", {}) or {}
        about = "\n".join(filter(None, [a.get("titulo", ""), a.get("resumen_breve", ""),
                                         ("Temas: " + "; ".join(a.get("temas") or [])) if a.get("temas") else ""]))
        answer = {"terminos": []}
        # En tandas: con 40 términos de una vez, la IA dejaba los últimos sin valorar
        for i in range(0, len(screen), SCREEN_BATCH):
            ctx.check_cancel()
            batch = screen[i:i + SCREEN_BATCH]
            ctx.report(0.95, f"Valorando términos vistos solo en pantalla ({i + len(batch)}/{len(screen)})")
            terms = "\n".join(K.screen_summary(p["data"]["term"], vision) for p in batch)
            r = llm.chat_json(SCREEN_SYSTEM, screen_user(about or "(sin resumen)", terms), SCREEN_SCHEMA, max_tokens=3000)
            answer["terminos"] += r.get("terminos") or []
        ctx.save("screen_judgment.raw.json", answer)
    kept, judged = apply_judgment(proposals, answer)
    ctx.save("screen_judgment.json", judged)
    return kept
