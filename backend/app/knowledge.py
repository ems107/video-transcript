"""Lógica pura del conocimiento aprendido (perfiles y personas).

Sin base de datos ni modelos: deduplicación, verificación de propuestas, atribución de datos a
personas, versiones (fotos y restauración) y detección de personas duplicadas.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import numpy as np
from rapidfuzz import fuzz

from .pipeline.glossary import normalize
from .pipeline.transcript import fmt_ts
from .pipeline.voice import match_name

PROFILE_KINDS = ("termino", "contexto", "seccion")
PERSON_KINDS = ("dato", "alias")
PROFILE_CATEGORIES = ("proyecto", "cliente", "sistema", "proceso", "sigla", "otro")
PERSON_CATEGORIES = ("cargo", "organizacion", "equipo", "responsabilidad", "proyecto", "conocimiento", "relacion",
                     "personal", "otro")
# Categorías de persona con un único valor vigente: al aceptar uno nuevo se retira el anterior
SINGLE_VALUE = {"cargo", "organizacion", "equipo"}
CATEGORY_LABELS = {
    "proyecto": "Proyecto", "cliente": "Cliente", "sistema": "Sistema", "proceso": "Proceso", "sigla": "Sigla",
    "otro": "Otro", "cargo": "Cargo", "organizacion": "Organización", "equipo": "Equipo",
    "responsabilidad": "Responsabilidad", "conocimiento": "Conocimiento", "relacion": "Relación",
    "personal": "Personal",
}
MAX_EVIDENCE = 10
# Las etiquetas «Hablante N» solo valen para un hablante de ese vídeo, nunca como persona nueva
_GENERIC_NAME = re.compile(r"^(hablante|speaker|participante|usuario|alguien|yo)\b", re.IGNORECASE)


# --------------------------------------------------------------------------- textos y claves

def item_text(kind: str, data: dict[str, Any]) -> str:
    if kind == "termino":
        return data.get("term", "")
    if kind == "seccion":
        return data.get("title", "")
    if kind in ("alias", "nueva_persona"):
        return data.get("name", "")
    return data.get("text", "")


def item_key(kind: str, data: dict[str, Any]) -> str:
    return normalize(item_text(kind, data))


def find_match(kind: str, key: str, items: list[dict[str, Any]], threshold: float = 85.0) -> dict[str, Any] | None:
    """Elemento existente equivalente (mismo tipo). Términos y nombres: clave idéntica; frases: parecidas."""
    if not key:
        return None
    best, best_s = None, 0.0
    for it in items:
        if it["kind"] != kind or not it.get("key"):
            continue
        if kind in ("termino", "alias", "nueva_persona", "seccion"):
            s = 100.0 if it["key"] == key else 0.0
        else:
            s = fuzz.token_sort_ratio(key, it["key"])
        if s > best_s:
            best, best_s = it, s
    return best if best_s >= threshold else None


def add_evidence(evidence: list[dict[str, Any]], new: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """Añade una evidencia (una por vídeo). Devuelve la lista y si el vídeo es nuevo."""
    if any(e.get("video_id") == new.get("video_id") for e in evidence):
        return evidence, False
    return [*evidence, new][-MAX_EVIDENCE:], True


# --------------------------------------------------------------------------- verificación

def _contains(haystack: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in f" {haystack} "


def term_occurrences(term: str, utts: list[dict[str, Any]], vision: list[dict[str, Any]], limit: int = 3) -> list[float]:
    """Momentos en que un término aparece literalmente en la transcripción o en la pantalla."""
    n = normalize(term)
    out: list[float] = []
    for u in utts:
        if _contains(normalize(u["text"]), n):
            out.append(float(u["start"]))
    for v in vision:
        text = " ".join([v.get("texto_relevante", ""), *v.get("terminos", []), v.get("descripcion", "")])
        if _contains(normalize(text), n):
            out.append(float(v["t"]))
    return sorted(out)[:limit]


def heard(term: str, utts: list[dict[str, Any]]) -> bool:
    n = normalize(term)
    return any(_contains(normalize(u["text"]), n) for u in utts)


def screen_appearances(term: str, vision: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fotogramas donde se ve el término: en el contenido principal («texto relevante») o solo en lo demás
    (la lista de todo lo legible: barra de tareas, pestañas, otras ventanas)."""
    n = normalize(term)
    out = []
    for v in vision:
        main = _contains(normalize(v.get("texto_relevante", "")), n)
        other = _contains(normalize(" ".join([*v.get("terminos", []), v.get("descripcion", "")])), n)
        if main or other:
            out.append({"t": float(v["t"]), "escena": v.get("tipo_escena", ""), "contenido": main,
                        "descripcion": (v.get("descripcion") or "")[:220]})
    return out


def screen_summary(term: str, vision: list[dict[str, Any]], examples: int = 3) -> str:
    """Dónde y cuánto se ve un término en pantalla, para que la IA valore si tiene que ver con el vídeo."""
    seen = screen_appearances(term, vision)
    if not seen:
        return f"- {term}: no se ve en pantalla"
    main = sum(1 for x in seen if x["contenido"])
    scenes = Counter(x["escena"] for x in seen if x["escena"])
    head = (f"- {term}: en {len(seen)} fotogramas, de {fmt_ts(seen[0]['t'])} a {fmt_ts(seen[-1]['t'])}; "
            f"en el contenido principal de {main}"
            + (f"; escenas: {', '.join(f'{k} ({c})' for k, c in scenes.most_common(3))}" if scenes else ""))
    # Ejemplos repartidos por el vídeo, prefiriendo los fotogramas donde es contenido principal
    pool = [x for x in seen if x["contenido"]] or seen
    step = max(1, len(pool) // examples)
    lines = [f"    [{fmt_ts(x['t'])}] {x['descripcion']}" for x in pool[::step][:examples] if x["descripcion"]]
    return "\n".join([head, *lines])


def group_forms(terms: list[str], min_len: int = 6) -> list[list[str]]:
    """Agrupa las formas de un mismo nombre: una contiene a la otra sin espacios ni signos
    («Bárymont», «Gestibarymont», «Grupo Bárymont», «BÄRYMONT ADVANCE, S.L.»). Conserva el orden."""
    compact = [normalize(t).replace(" ", "") for t in terms]
    parent = list(range(len(terms)))

    def root(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i

    for i in range(len(terms)):
        for j in range(i + 1, len(terms)):
            a, b = sorted((compact[i], compact[j]), key=len)
            if len(a) >= min_len and a in b:
                parent[root(j)] = root(i)
    groups: dict[int, list[str]] = {}
    for i, t in enumerate(terms):
        groups.setdefault(root(i), []).append(t)
    return list(groups.values())


def term_candidates(utts: list[dict[str, Any]], screen_terms: list[str], exclude: set[str],
                    min_count: int = 2, limit: int = 80) -> list[str]:
    """Posibles términos del negocio: lo visto en pantalla y, en la transcripción, siglas,
    CamelCase y palabras con mayúscula a media frase que se repiten."""
    counts: Counter[str] = Counter()
    for u in utts:
        tokens = u["text"].split()
        for i, raw in enumerate(tokens):
            w = raw.strip("¿¡\"'“”()[]{}«».,;:!?…")
            if len(w) < 2 or not w[0].isupper():
                continue
            acronym = w.isupper() and len(w) >= 2
            camel = bool(re.search(r"[a-záéíóúñ][A-ZÁÉÍÓÚÑ]", w))
            mid = i > 0 and not tokens[i - 1].endswith((".", "?", "!", "…", ":"))
            if acronym or camel or mid:
                counts[w] += 1
    out: list[str] = []
    seen = set(exclude)
    for t in [*screen_terms, *(w for w, c in counts.most_common() if c >= min_count)]:
        k = normalize(t)
        if k and k not in seen and len(k) > 1:
            seen.add(k)
            out.append(t.strip())
        if len(out) >= limit:
            break
    return out


# Palabras que el LLM añade al redactar y que no tienen por qué estar en la transcripción
_FILLER = set("""
para como con que los las del una uno unos unas esta este estos estas esto sobre entre cada desde hasta tambien
tiene tienen hace hacer esta estan ser son sus mas muy todo todos toda todas otro otra otros otras donde cuando
lleva llevar gestiona gestionar encargado encargada responsable coordina coordinar trabaja trabajar utiliza
utilizar existe existen proceso realiza realizar persona personas parte forma manera usa usar suele habitual
habitualmente principal principales equipo grupo area departamento
""".split())


def _content_words(text: str) -> list[str]:
    words = []
    for raw in text.split():
        w = normalize(raw)
        acronym = raw.strip("«».,;:()").isupper() and len(w) >= 2
        if w and w not in _FILLER and (len(w) >= 4 or acronym):
            words.append(w)
    return words


def supported(text: str, utts: list[dict[str, Any]], vision: list[dict[str, Any]], t: float,
              window: float = 60.0) -> bool:
    """Si la transcripción (o la pantalla) alrededor de `t` respalda la frase: comparten la mayoría de sus
    palabras con contenido. Evita que se cuelen datos inventados o copiados de otro sitio."""
    words = _content_words(text)
    if not words:
        return False
    near = [u["text"] for u in utts if u["end"] >= t - window and u["start"] <= t + window]
    near += [v.get("texto_relevante", "") for v in vision if abs(v["t"] - t) <= window]
    stems = {w[:5] for w in normalize(" ".join(near)).split()}
    hits = sum(1 for w in words if w[:5] in stems)
    return hits >= max(1, -(-len(words) * 6 // 10))  # al menos el 60 % (redondeando hacia arriba)


def excerpt_at(utts: list[dict[str, Any]], t: float, window: float = 20.0, max_lines: int = 4) -> list[dict[str, Any]]:
    """Líneas reales de la transcripción alrededor de `t` (evidencia de una propuesta)."""
    near = [u for u in utts if u["end"] >= t - window and u["start"] <= t + window]
    near.sort(key=lambda u: abs((u["start"] + u["end"]) / 2 - t))
    lines = sorted(near[:max_lines], key=lambda u: u["start"])
    return [{"t": float(u["start"]), "label": u.get("speaker", ""), "text": u["text"][:400]} for u in lines]


# --------------------------------------------------------------------------- atribución a personas

def resolve_name(name: str, speaker_names: dict[str, str], people: list[dict[str, Any]]) -> tuple[str, Any] | None:
    """A quién se refiere un nombre devuelto por el LLM.

    ("speaker", etiqueta) si es un hablante del vídeo; ("person", id) si es una persona conocida;
    ("new", nombre) si parece una persona nueva; None si no es un nombre utilizable.
    """
    name = (name or "").strip()
    if not name:
        return None
    if _GENERIC_NAME.match(name):
        # «Hablante 3» se parece mucho a «Hablante 2»: solo vale la coincidencia exacta
        label = next((lb for lb, shown in speaker_names.items() if normalize(shown) == normalize(name)), None)
        return ("speaker", label) if label else None
    speakers = [{"id": label, "name": shown, "aliases": []} for label, shown in speaker_names.items()]
    label = match_name(name, speakers)
    if label is not None:
        return ("speaker", label)
    pid = match_name(name, people)
    if pid is not None:
        return ("person", pid)
    if not name[0].isupper() or len(name) < 2:
        return None
    return ("new", name)


def speaker_person(speaker: dict[str, Any] | None, auto_threshold: float) -> int | None:
    """Persona a la que se atribuye lo que dice un hablante: confirmada, o reconocida con confianza alta."""
    if not speaker:
        return None
    if speaker.get("confirmed") and speaker.get("person_id"):
        return speaker["person_id"]
    pid = speaker.get("suggested_person_id")
    if pid and (speaker.get("source") == "micrófono"
                or (speaker.get("source") == "voz" and speaker.get("confidence", 0) >= auto_threshold)):
        return pid
    return None


def single_value_conflicts(item: dict[str, Any], accepted: list[dict[str, Any]]) -> list[int]:
    """Elementos que deja obsoletos aceptar `item` (cargo, organización o equipo anteriores)."""
    if item["kind"] != "dato" or item.get("category") not in SINGLE_VALUE:
        return []
    return [a["id"] for a in accepted
            if a["id"] != item.get("id") and a["kind"] == "dato" and a.get("category") == item["category"]]


# --------------------------------------------------------------------------- versiones

def _snap_item(it: dict[str, Any]) -> dict[str, Any]:
    return {"id": it["id"], "kind": it["kind"], "category": it.get("category", ""), "data": it.get("data", {})}


def make_snapshot(manual: dict[str, Any], accepted: list[dict[str, Any]], person_ids: list[int] | None = None) -> dict:
    snap: dict[str, Any] = {"manual": manual, "items": [_snap_item(i) for i in accepted]}
    if person_ids is not None:
        snap["person_ids"] = sorted(person_ids)
    return snap


def restore_plan(snapshot: dict[str, Any], current: list[dict[str, Any]]) -> dict[str, Any]:
    """Qué hay que cambiar en los elementos actuales para volver a la foto `snapshot`."""
    target = {i["id"]: i for i in snapshot.get("items", [])}
    by_id = {i["id"]: i for i in current}
    plan: dict[str, Any] = {"accept": [], "retire": [], "update": {}, "create": []}
    for it in current:
        if it["status"] == "aceptado" and it["id"] not in target:
            plan["retire"].append(it["id"])
    for iid, t in target.items():
        cur = by_id.get(iid)
        if cur is None:
            plan["create"].append(t)
            continue
        if cur["status"] != "aceptado":
            plan["accept"].append(iid)
        if cur.get("data") != t["data"] or cur.get("category", "") != t.get("category", ""):
            plan["update"][iid] = {"data": t["data"], "category": t.get("category", "")}
    return plan


def version_diff(prev: dict[str, Any] | None, cur: dict[str, Any]) -> dict[str, Any]:
    """Resumen de qué cambió entre dos fotos: elementos añadidos y quitados, campos manuales tocados."""
    prev = prev or {"manual": {}, "items": []}
    p_items = {i["id"]: i for i in prev.get("items", [])}
    c_items = {i["id"]: i for i in cur.get("items", [])}
    label = lambda i: item_text(i["kind"], i["data"])
    added = [label(i) for k, i in c_items.items() if k not in p_items]
    removed = [label(i) for k, i in p_items.items() if k not in c_items]
    changed = [label(i) for k, i in c_items.items() if k in p_items and p_items[k]["data"] != i["data"]]
    manual = [k for k in set(prev.get("manual", {})) | set(cur.get("manual", {}))
              if prev.get("manual", {}).get(k) != cur.get("manual", {}).get(k)]
    if prev.get("person_ids") != cur.get("person_ids") and "person_ids" in cur:
        manual.append("personas")
    return {"added": added, "removed": removed, "changed": changed, "manual": sorted(manual)}


# --------------------------------------------------------------------------- personas duplicadas

def _tokens(name: str) -> set[str]:
    return set(normalize(name).split())


def duplicate_candidates(people: list[dict[str, Any]], centroids: dict[int, np.ndarray] | None = None,
                         voice_threshold: float = 0.75) -> list[dict[str, Any]]:
    """Parejas de personas que podrían ser la misma: nombre contenido o muy parecido, o voz parecida."""
    centroids = centroids or {}
    out = []
    for i, a in enumerate(people):
        for b in people[i + 1:]:
            reasons = []
            names_a = [a["name"], *(a.get("aliases") or [])]
            names_b = [b["name"], *(b.get("aliases") or [])]
            for na in names_a:
                ta = _tokens(na)
                for nb in names_b:
                    tb = _tokens(nb)
                    if ta and tb and (ta <= tb or tb <= ta or fuzz.token_sort_ratio(normalize(na), normalize(nb)) >= 90):
                        reasons.append("nombre")
                        break
                if reasons:
                    break
            if a["id"] in centroids and b["id"] in centroids:
                sim = float(np.dot(centroids[a["id"]], centroids[b["id"]]))
                if sim >= voice_threshold:
                    reasons.append("voz")
            if reasons:
                out.append({"a": a["id"], "b": b["id"], "reasons": reasons})
    return out


def merged_aliases(target: dict[str, Any], source: dict[str, Any]) -> list[str]:
    """Otros nombres de la persona resultante al fusionar `source` en `target`."""
    out: list[str] = []
    seen = {normalize(target["name"])}
    for n in [*(target.get("aliases") or []), source["name"], *(source.get("aliases") or [])]:
        k = normalize(n)
        if k and k not in seen:
            seen.add(k)
            out.append(n.strip())
    return out


# --------------------------------------------------------------------------- uso en los prompts

def effective_glossary(profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Glosario manual seguido de los términos aprendidos (marcados como no fiables para corregir)."""
    profile = profile or {}
    out = [{**g, "trusted": True} for g in profile.get("glossary") or [] if g.get("term")]
    seen = {normalize(g["term"]) for g in out}
    for it in profile.get("learned") or []:
        if it["kind"] != "termino":
            continue
        term = it["data"].get("term", "").strip()
        if term and normalize(term) not in seen:
            seen.add(normalize(term))
            out.append({"term": term, "variants": [], "definition": it["data"].get("definition", ""), "trusted": False})
            # Otras formas del mismo nombre vistas en el vídeo: también orientan a Whisper
            for form in it["data"].get("forms") or []:
                if normalize(form) not in seen:
                    seen.add(normalize(form))
                    out.append({"term": form, "variants": [], "definition": "", "trusted": False})
    return out


def effective_sections(profile: dict[str, Any] | None) -> list[str]:
    profile = profile or {}
    out = list(profile.get("summary_sections") or [])
    seen = {normalize(s) for s in out}
    for it in profile.get("learned") or []:
        title = it["data"].get("title", "").strip() if it["kind"] == "seccion" else ""
        if title and normalize(title) not in seen:
            seen.add(normalize(title))
            out.append(title)
    return out


def learned_block(profile: dict[str, Any] | None, max_chars: int = 6000) -> str:
    """Contexto y términos aprendidos, de más a menos confirmados, dentro de un límite de tamaño."""
    lines: list[str] = []
    size = 0
    manual_terms = {normalize(g.get("term", "")) for g in (profile or {}).get("glossary") or []}
    for it in (profile or {}).get("learned") or []:
        if it["kind"] == "contexto":
            cat = CATEGORY_LABELS.get(it.get("category", ""), "")
            line = f"- {f'[{cat}] ' if cat else ''}{it['data'].get('text', '')}"
        elif it["kind"] == "termino" and normalize(it["data"].get("term", "")) not in manual_terms:
            d = it["data"].get("definition", "")
            forms = it["data"].get("forms") or []
            line = (f"- Término «{it['data'].get('term', '')}»" + (f" (también {', '.join(forms)})" if forms else "")
                    + (f": {d}" if d else ""))
        else:
            continue
        if size + len(line) > max_chars:
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(lines)


def person_line(p: dict[str, Any], max_facts: int = 5) -> str:
    """«- María López (Jefa de proyecto; Organización: Acme): lleva Atlas; …» para los prompts."""
    facts = p.get("facts") or []
    tags = []
    role = p.get("role") or next((f["text"] for f in facts if f["category"] == "cargo"), "")
    if role:
        tags.append(role)
    for cat in ("organizacion", "equipo"):
        val = next((f["text"] for f in facts if f["category"] == cat), "")
        if val:
            tags.append(f"{CATEGORY_LABELS[cat]}: {val}")
    rest = [f["text"] for f in facts if f["category"] not in SINGLE_VALUE][:max_facts]
    aliases = [a for a in p.get("aliases") or [] if a and normalize(a) != normalize(p["name"])]
    if aliases:
        tags.insert(0, "también llamado " + ", ".join(aliases[:4]))
    line = f"- {p['name']}" + (f" ({'; '.join(tags)})" if tags else "")
    if p.get("notes"):
        rest.insert(0, p["notes"])
    return line + (": " + "; ".join(rest) if rest else "")


def prompt_people(people: list[dict[str, Any]], limit: int = 30) -> list[dict[str, Any]]:
    """Personas que se incluyen en los prompts: las del vídeo y las del perfil (o cualquiera, si no hay)."""
    relevant = [p for p in people if p.get("in_video") or p.get("in_profile")]
    relevant.sort(key=lambda p: (not p.get("in_video"), not p.get("in_profile")))
    return (relevant or people)[:limit]


_EPHEMERAL = re.compile(
    r"\b(ayer|hoy|mañana|anoche|esta (semana|mañana|tarde)|la semana (pasada|que viene)|el (lunes|martes|miércoles|"
    r"jueves|viernes|sábado|domingo)|próxim[oa]s? (semana|reunión|lunes)|a las \d|tard[óo]|ha (revisado|propuesto))\b",
    re.IGNORECASE,
)


def is_ephemeral(text: str) -> bool:
    """Frases con marcas temporales o de un momento concreto: no son conocimiento duradero."""
    return bool(_EPHEMERAL.search(text))


def parse_ts(ts: str) -> float | None:
    """«hh:mm:ss», «mm:ss» o «[hh:mm:ss]» a segundos."""
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", ts or "")
    if not m:
        return None
    a, b, c = m.groups()
    return int(a) * 3600 + int(b) * 60 + int(c) if c is not None else int(a) * 60 + int(b)
