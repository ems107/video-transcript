"""Fase 10: propuestas de conocimiento para el perfil y las personas.

El LLM lee la transcripción por bloques y propone términos, hechos del negocio y datos de personas.
Todo se comprueba aquí contra la transcripción y la pantalla antes de guardarse como propuesta: lo que
no aparece se descarta. El usuario acepta o rechaza cada propuesta en la web.
"""

from __future__ import annotations

import re
from typing import Any

from .. import knowledge as K
from ..llm import LLMServer, LLMTruncated
from ..prompts import (
    JUDGE_SCHEMA,
    JUDGE_SYSTEM,
    LEARN_SCHEMA,
    LEARN_SYSTEM,
    NOTES_SCHEMA,
    NOTES_SYSTEM,
    SCREEN_SCHEMA,
    SCREEN_SYSTEM,
    corrections_block,
    judge_user,
    learn_user,
    notes_user,
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
MAX_CORRECTIONS = 15
SCREEN_BATCH = 12  # términos por consulta al valorar los vistos solo en pantalla
JUDGE_BATCH = 20  # propuestas por consulta en la pasada de juicio (con razonamiento)


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


def known_items(profile: dict[str, Any] | None, people: list[dict[str, Any]]) -> dict[int, str]:
    """Lo mismo que `known_block`, por número: para saber qué repite una propuesta en la pasada de juicio."""
    out = {it["id"]: K.item_text(it["kind"], it["data"]) for it in (profile or {}).get("learned") or []
           if it["kind"] in ("termino", "contexto")}
    for p in K.prompt_people(people):
        out.update({f["id"]: f"{p['name']}: {f['text']}" for f in p.get("facts") or []})
    return out


def evidence_lines(t: float, utts: list[dict[str, Any]], vision: list[dict[str, Any]],
                   term: str = "", claim: str = "") -> list[dict[str, Any]]:
    """Transcripción alrededor de `t` (o de la frase que más se parece a `claim`, si se da); la pantalla solo
    si muestra el término (o si no hay habla)."""
    hit = None
    if claim:
        t = K.best_moment(claim, utts, t)
        hit = next((u for u in utts if float(u["start"]) == t), None)
    lines = K.excerpt_at(utts, t, max_lines=3)
    if hit and not any(ln["t"] == t for ln in lines):
        # Una intervención larga queda lejos por su punto medio: la que lo dice va siempre
        lines = [{"t": t, "label": hit.get("speaker", ""), "text": hit["text"][:400]}, *lines[:2]]
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
            lines = evidence_lines(t, utts, vision, claim=text)
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
            lines = evidence_lines(t, utts, vision, claim=text)
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
        if p["kind"] == "termino":
            p["seen"] = {"n": p.get("n", 1), "heard": not p.get("screen_only", False)}
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
    if profile:
        people = {n for p in ctx.people for n in [p["name"], *(p.get("aliases") or [])]} | set(names.values())
        notes = [c["text"] for c in ctx.corrections]
        proposals += collect_corrections(results, utts, vision, screen_terms, profile, notes, people,
                                         notes_corrections(ctx, llm, notes))
    proposals = judge_screen_terms(ctx, llm, proposals, vision)
    proposals = judge_proposals(ctx, llm, proposals, profile, names)
    ctx.save("proposals.json", proposals)
    return proposals


# Fuentes de una corrección, de más a menos fiable (ver `knowledge.correction_source`)
SOURCE_RANK = {"usuario": 0, "pantalla": 1, "glosario": 2, "ia": 3}
SOURCE_REASON = {
    "pantalla": "Se lee «{term}» en pantalla y en la transcripción aparece «{forms}».",
    "glosario": "La corrección de términos ya cambió «{forms}» por «{term}» en este vídeo.",
}


def collect_corrections(results: list[dict[str, Any]], utts: list[dict[str, Any]], vision: list[dict[str, Any]],
                        screen_terms: list[str], profile: dict[str, Any], user_notes: list[str],
                        people: set[str] = frozenset(), notes_pairs: list[dict[str, Any]] | None = None
                        ) -> list[dict[str, Any]]:
    """Formas mal transcritas de un término («Natur» por «Naturgy»): una propuesta por término con sus formas.

    Salen de la IA (que puede apoyarse en la pantalla), de tus notas (`notes_pairs`) y de lo que la fase de
    corrección ya cambió. Cada forma debe oírse tal cual en la transcripción. Lo que solo deduce la IA queda
    como dudoso. Buscar por sonido nombres de la pantalla en la transcripción se probó y se quitó: con un vídeo
    real salían 15 parejas sin sentido («Meta» por «está», «Chat» por «casa»). Los nombres de personas (`people`) no: cómo
    se oye a una persona son sus otros nombres, y la IA confundía con ellos frases normales («Juan, puedes…»)."""
    glossary = K.effective_glossary(profile)
    known = K.known_forms(profile)
    person_words = {w for n in people for w in normalize(n).split() if len(w) > 2}
    found: dict[str, dict[str, Any]] = {}

    def add(term: str, form: str, source: str, reason: str) -> None:
        term, form = term.strip(), form.strip()
        nt, nf = normalize(term), normalize(form)
        if not nt or not nf or nt == nf or (nt, nf) in known or f" {nt} " in f" {nf} ":
            return
        if set(nt.split()) & person_words:
            return  # es el nombre de una persona
        if not K.heard_at(form, utts, limit=1):
            return  # la forma oída debe aparecer de verdad en la transcripción
        source = K.correction_source(term, user_notes, vision, screen_terms, glossary) if source == "ia" else source
        g = found.setdefault(nt, {"term": term, "forms": {}, "source": source, "reason": reason})
        g["forms"].setdefault(nf, form)
        if SOURCE_RANK[source] < SOURCE_RANK[g["source"]]:
            g["source"], g["reason"] = source, reason

    for r in results:
        for x in r.get("correcciones") or []:
            add(x.get("correcto", ""), x.get("oido", ""), "ia", (x.get("motivo") or "").strip())
    for x in notes_pairs or []:
        add(x.get("correcto", ""), x.get("oido", ""), "usuario", "Según tus correcciones del vídeo.")
    for term, forms in K.corrections_from_correct_stage(utts).items():
        for f in forms:
            add(term, f, "glosario", "")

    out = []
    original = [{**u, "text": u.get("original_text") or u["text"]} for u in utts]
    for g in sorted(found.values(), key=lambda g: SOURCE_RANK[g["source"]])[:MAX_CORRECTIONS]:
        forms = sorted(g["forms"].values())
        t = min(t for f in forms for t in K.heard_at(f, utts, limit=1))
        reason = g["reason"] or SOURCE_REASON.get(g["source"], "").format(term=g["term"], forms="», «".join(forms))
        data: dict[str, Any] = {"term": g["term"], "variants": forms, "fuente": g["source"], "motivo": reason}
        if g["source"] == "ia":
            data["juicio"] = {"valor": "dudosa", "motivo": "Solo lo deduce la IA: escucha el momento para comprobarlo."}
        out.append({"kind": "correccion", "category": "", "owner": ("profile", None), "data": data, "t": t,
                    "lines": K.excerpt_at(original, t, max_lines=3), "replaces": 0})
    return out


def _owner_label(p: dict[str, Any], names: dict[str, str], people: list[dict[str, Any]]) -> str:
    kind, ref = p["owner"][0], p["owner"][1]
    if kind == "profile":
        return "perfil"
    if kind == "speaker":
        return names.get(ref, ref)
    if kind == "person":
        return next((x["name"] for x in people if x["id"] == ref), "persona")
    return f"persona nueva {ref}"


KIND_NAMES = {"termino": "término", "contexto": "hecho del negocio", "dato": "dato", "alias": "otro nombre",
              "correccion": "corrección de transcripción", "nueva_persona": "persona nueva", "seccion": "sección"}


def judge_lines(batch: list[tuple[int, dict[str, Any]]], names: dict[str, str], people: list[dict[str, Any]]) -> str:
    """Las propuestas para la pasada de juicio. Un término lleva cuántas veces aparece y si se oye: su frase
    de ejemplo suele ser cualquiera («Un segundito») y, con ella sola, la IA descartaba términos clave."""
    out = []
    for i, p in batch:
        cat = K.CATEGORY_LABELS.get(p.get("category", ""), "")
        text = K.item_text(p["kind"], p["data"]) if p["kind"] != "nueva_persona" else \
            f"{p['data']['name']}: " + "; ".join(d["text"] for d in p["data"].get("datos", []))
        if p["kind"] == "correccion" and p["data"].get("motivo"):
            text += f" — {p['data']['motivo']}"
        if p["kind"] == "termino":
            seen = p.get("seen") or {}
            where = "se oye en la conversación" if seen.get("heard", True) else "solo se ve en pantalla"
            text += f" (aparece {seen.get('n', 1)} {'vez' if seen.get('n', 1) == 1 else 'veces'}; {where})"
        lines = p.get("lines") or []
        if p["kind"] in ("dato", "contexto") and lines:
            # La línea que más respalda el dato y la siguiente (la respuesta a una pregunta suele venir justo
            # después): con las primeras del fragmento, la IA descartaba datos ciertos porque «la frase no lo dice»
            claim = p["data"].get("text", "")
            best = max(range(len(lines)), key=lambda j: K.claim_score(claim, lines[j]["text"]))
            lines = lines[best:best + 2]
        line = " / ".join(ln["text"][:180] for ln in lines[:2])
        out.append(f"{i}. [{_owner_label(p, names, people)} · {KIND_NAMES.get(p['kind'], p['kind'])}"
                   f"{' · ' + cat if cat else ''}] {text}" + (f" (frase: «{line}»)" if line else ""))
    return "\n".join(out)


def notes_corrections(ctx: JobContext, llm: LLMServer, notes: list[str]) -> list[dict[str, Any]]:
    """Pares «forma mal transcrita → forma correcta» que el usuario escribe en sus correcciones («ALTED es un
    error: es El Altet»). La extracción por fragmentos no los recogía: los veía como contexto."""
    if not notes:
        return []
    try:
        r = llm.chat_json(NOTES_SYSTEM, notes_user(notes), NOTES_SCHEMA, max_tokens=1500)
    except Exception:  # noqa: BLE001  (de mejor esfuerzo)
        return []
    return [x for x in r.get("pares") or [] if (x.get("oido") or "").strip() and (x.get("correcto") or "").strip()]


def apply_proposal_judgment(proposals: list[dict[str, Any]], answer: dict[str, Any],
                            known: dict[int, str] | None = None) -> list[dict[str, Any]]:
    """Aplica la pasada de juicio: lo descartado se guarda como `descartado_ia` (se puede recuperar), lo que
    repite otra propuesta o algo ya guardado (`known`: {número: texto}) también, y lo dudoso se marca. Lo que
    la IA no valora queda como estaba. Las alias y las secciones no se juzgan aquí."""
    verdicts = {x.get("id"): x for x in answer.get("propuestas") or []}
    out = []
    for i, p in enumerate(proposals):
        v = verdicts.get(i)
        # Lo que sale de las correcciones del usuario no se juzga: lo dijo él
        if not v or p["kind"] in ("alias", "seccion") or p["data"].get("fuente") == "usuario":
            out.append(p)
            continue
        valor, motivo = v.get("valor"), (v.get("motivo") or "").strip()
        same = v.get("igual_que") or 0
        data = dict(p["data"])
        if same and same != i and 0 <= same < len(proposals) and proposals[same]["kind"] == p["kind"] \
                and (verdicts.get(same) or {}).get("valor") != "descartar":
            other = K.item_text(proposals[same]["kind"], proposals[same]["data"])
            valor, motivo = "descartar", f"Repite otra propuesta: «{other}»."
        elif (v.get("ya_guardado") or 0) in (known or {}):
            valor, motivo = "descartar", f"Ya está guardado: «{known[v['ya_guardado']]}»."
        if valor == "descartar":
            data["juicio"] = {"valor": "descartar", "motivo": motivo}
            out.append({**p, "data": data, "status": "descartado_ia"})
            continue
        if valor == "dudosa" or (data.get("juicio") or {}).get("valor") == "dudosa":
            data["juicio"] = {"valor": "dudosa", "motivo": motivo if valor == "dudosa" else data["juicio"]["motivo"]}
        elif valor == "util" and motivo:
            data["juicio"] = {"valor": "util", "motivo": motivo}
        out.append({**p, "data": data})
    return out


def section_proposals(answer: dict[str, Any], learned: dict[int, str]) -> list[dict[str, Any]]:
    """Secciones nuevas si las actuales no encajan con este tipo de vídeo. Solo se sustituye una aprendida."""
    sec = answer.get("secciones") or {}
    if sec.get("encajan", True):
        return []
    out, seen = [], set()
    for x in (sec.get("propuestas") or [])[:2]:
        # La IA a veces copia el número de la lista delante del título («[#01] Acuerdos…»)
        title = re.sub(r"^\s*(\[#?\d+\]|#\d+[.:)]?)\s*", "", x.get("titulo") or "").strip()
        if not title or normalize(title) in seen or normalize(title) in {normalize(t) for t in learned.values()}:
            continue
        seen.add(normalize(title))
        replaces = x.get("reemplaza") if x.get("reemplaza") in learned else 0
        out.append({"kind": "seccion", "category": "", "owner": ("profile", None),
                    "data": {"title": title, "juicio": {"valor": "util", "motivo": sec.get("motivo", "")}},
                    "t": None, "lines": [], "replaces": replaces})
    return out


def judge_proposals(ctx: JobContext, llm: LLMServer, proposals: list[dict[str, Any]],
                    profile: dict[str, Any] | None, names: dict[str, str]) -> list[dict[str, Any]]:
    """Segunda pasada: la IA revisa todas las propuestas juntas (`apply_proposal_judgment`) y si las secciones
    del resumen encajan con el vídeo. Es de mejor esfuerzo: si falla, las propuestas quedan como estaban."""
    if not proposals and not profile:
        return proposals
    answer = ctx.load("judgment.raw.json")
    if answer is None:
        a = ctx.load("analysis.json", {}) or {}
        about = "\n".join(filter(None, [a.get("titulo", ""), a.get("resumen_breve", ""),
                                         ("Temas: " + "; ".join(a.get("temas") or [])) if a.get("temas") else ""]))
        learned_sections = {it["id"]: it["data"].get("title", "") for it in (profile or {}).get("learned") or []
                            if it["kind"] == "seccion"}
        sections = "\n".join([*(f"- {t}" for t in (profile or {}).get("summary_sections") or []),
                              *(f"- [#{i}] {t}" for i, t in learned_sections.items())])
        known = known_items(profile, ctx.people)
        known_text = known_block(profile, ctx.people)
        kind_name = (profile or {}).get("name", "") + (f": {profile['description']}" if (profile or {}).get("description") else "")
        answer = {"propuestas": [], "secciones": {"encajan": True, "motivo": "", "propuestas": []}}
        indexed = list(enumerate(proposals))
        # Juntas las del mismo dueño y tipo, para que vea los duplicados
        indexed.sort(key=lambda x: (str(x[1]["owner"]), x[1]["kind"]))
        def judge(batch: list[tuple[int, dict[str, Any]]], with_sections: bool) -> dict[str, Any]:
            # Con el modo razonamiento: sin él, el juicio cambiaba de una ejecución a otra (un código
            # promocional salía útil o descartado) y se fiaba demasiado de la frase de ejemplo
            try:
                return llm.chat_json(JUDGE_SYSTEM, judge_user(about or "(sin resumen)", kind_name,
                                                              sections if with_sections else "",
                                                              judge_lines(batch, names, ctx.people) or "(ninguna)",
                                                              known_text),
                                     JUDGE_SCHEMA, max_tokens=16000, thinking=True)
            except LLMTruncated:
                if len(batch) < 2:
                    raise
                a, b = judge(batch[:len(batch) // 2], with_sections), judge(batch[len(batch) // 2:], False)
                return {"propuestas": (a.get("propuestas") or []) + (b.get("propuestas") or []),
                        "secciones": a.get("secciones")}

        try:
            for b in range(0, max(1, len(indexed)), JUDGE_BATCH):
                ctx.check_cancel()
                batch = indexed[b:b + JUDGE_BATCH]
                ctx.report(0.97, f"Revisando las propuestas ({b + len(batch)}/{len(indexed)})")
                r = judge(batch, b == 0)
                answer["propuestas"] += r.get("propuestas") or []
                if b == 0:
                    answer["secciones"] = r.get("secciones") or answer["secciones"]
        except Exception as e:  # noqa: BLE001  (de mejor esfuerzo, como el resto del aprendizaje)
            ctx.save("judgment_error.json", {"error": str(e)})
            return proposals
        answer["learned_sections"] = learned_sections
        answer["known"] = known
        ctx.save("judgment.raw.json", answer)
    # Lo ya guardado tal como estaba al juzgar (en JSON, las claves son texto)
    out = apply_proposal_judgment(proposals, answer, {int(k): v for k, v in (answer.get("known") or {}).items()})
    learned = {int(k): v for k, v in (answer.get("learned_sections") or {}).items()}
    # Solo si el perfil ya tiene secciones: sin ninguna, las propone la extracción (`want_sections`)
    has_sections = bool(K.effective_sections(profile)) if profile else False
    return out + (section_proposals(answer, learned) if has_sections else [])


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
