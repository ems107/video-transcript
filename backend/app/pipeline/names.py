"""Fase 7: unificación de los nombres leídos en pantalla.

El modelo de visión lee cada fotograma por separado y, con texto pequeño, devuelve el mismo nombre
escrito de muchas formas («Iosu Urcelay», «Iker Urcelay», «Ione Urcelay»…). Esta fase agrupa las
variantes de cada persona y elige una sola forma, para que la identificación de hablantes, el resumen
y el aprendizaje usen siempre el mismo nombre.

Criterios (deterministas, sin LLM):
- dos nombres que aparecen a la vez entre los participantes de un mismo fotograma son personas
  distintas y nunca se agrupan;
- se agrupan los nombres parecidos (mismo nombre de pila, apellidos parecidos al oído, o el mismo
  nombre corto con alguna letra mal leída);
- la forma elegida se construye palabra a palabra: gana la palabra que se oye en la transcripción y,
  si no, la más leída. Las tildes se conservan si aparecen en una parte apreciable de las lecturas,
  porque al leer texto pequeño es mucho más fácil perder una tilde que inventarla.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from rapidfuzz import fuzz

from .base import JobContext
from .glossary import normalize, phonetic, strip_accents
from .voice import match_name

# Descripciones en lugar de nombres («Usuario con gafas», «Participante sin nombre visible»)
_PSEUDO = re.compile(
    r"\b(usuario|usuaria|participante|persona|hombre|mujer|invitado|invitada|desconocido|desconocida|"
    r"sin nombre|nombre visible|anonimo|anonima)\b"
)
_PARTICLES = {"de", "del", "la", "las", "los", "y", "i", "da", "do", "dos", "van", "von"}
ACCENT_SHARE = 0.25  # proporción mínima de lecturas con tilde para conservarla
SIMILAR = 80.0


def clean_name(raw: str) -> str:
    """Quita anotaciones entre paréntesis y descarta lo que no es un nombre."""
    name = re.sub(r"\(.*?\)", " ", raw or "")
    name = re.sub(r"\s+", " ", name).strip(" .,;:-")
    if name.count(",") == 1:  # «Apellidos, Nombre»
        last, first = (x.strip() for x in name.split(","))
        name = f"{first} {last}".strip()
    n = normalize(name)
    if len(n) < 2 or not re.search(r"[a-z]", n) or _PSEUDO.search(n):
        return ""
    return name


def _significant(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in _PARTICLES]


def similarity(a: str, b: str) -> float:
    """Parecido entre dos nombres (0-100), tolerante a letras mal leídas."""
    na, nb = normalize(a), normalize(b)
    if na == nb:
        return 100.0
    ta, tb = na.split(), nb.split()
    if len(ta) == 1 and len(tb) == 1:
        # Nombre corto: «Edge»/«Edgar», «Sandia»/«Sandra»
        s = fuzz.ratio(na, nb)
        return max(s, SIMILAR) if s >= 65 and na[:2] == nb[:2] else s * 0.8
    if len(ta) == 1 or len(tb) == 1:
        # «Javier» frente a «Javier Arce»: el nombre corto es el de pila del largo
        short, long_ = (ta, tb) if len(ta) == 1 else (tb, ta)
        return 85.0 if short[0] == long_[0] else fuzz.ratio(na, nb) * 0.8
    best = fuzz.token_sort_ratio(na, nb)
    ra, rb = _significant(ta[1:]), _significant(tb[1:])
    if ra and rb:
        # Mismos apellidos (o que suenan igual) con distinto nombre de pila: «Iker/Iosu Urcelay…»
        rest = max(fuzz.ratio(" ".join(ra), " ".join(rb)), fuzz.ratio(phonetic(" ".join(ra)), phonetic(" ".join(rb))))
        if rest >= 85:
            best = max(best, rest)
        if ta[0] == tb[0]:
            best = max(best, 85.0)  # mismo nombre de pila, apellido mal leído
    return best


def collect(vision: list[dict[str, Any]]) -> tuple[Counter, dict[str, set[int]], dict[str, str]]:
    """Lecturas limpias: cuántas veces sale cada forma, en qué fotogramas (como recuadro) y su limpieza."""
    counts: Counter = Counter()
    frames: dict[str, set[int]] = {}
    cleaned: dict[str, str] = {}
    for i, v in enumerate(vision):
        for raw in v.get("participantes") or []:
            name = clean_name(raw)
            cleaned[raw] = name
            if name:
                counts[name] += 1
                frames.setdefault(name, set()).add(i)
        raw = v.get("hablante_activo") or ""
        name = clean_name(raw)
        cleaned[raw] = name
        if name:
            counts[name] += 1
            frames.setdefault(name, set())
    return counts, frames, cleaned


def cluster(counts: Counter, frames: dict[str, set[int]]) -> list[list[str]]:
    """Agrupa las formas parecidas; nunca junta dos que coinciden en un mismo fotograma."""
    # Formas que solo difieren en tildes o mayúsculas: siempre la misma persona
    by_norm: dict[str, list[str]] = {}
    for name in counts:
        by_norm.setdefault(normalize(name), []).append(name)
    groups = sorted(by_norm.values(), key=lambda g: -sum(counts[n] for n in g))

    clusters: list[dict[str, Any]] = []
    for g in groups:
        g_frames = set().union(*(frames.get(n, set()) for n in g))
        best, best_s = None, 0.0
        for c in clusters:
            if c["frames"] & g_frames:
                continue
            s = max(similarity(g[0], m) for m in c["members"])
            if s > best_s:
                best, best_s = c, s
        if best is not None and best_s >= SIMILAR:
            best["members"].extend(g)
            best["frames"] |= g_frames
        else:
            clusters.append({"members": list(g), "frames": set(g_frames)})
    return [c["members"] for c in clusters]


def heard_counts(texts: list[str]) -> Counter:
    words: Counter = Counter()
    for t in texts:
        words.update(normalize(t).split())
    return words


def canonical(members: list[str], counts: Counter, heard: Counter) -> str:
    """Forma única del grupo, construida palabra a palabra."""
    lengths: Counter = Counter()
    for m in members:
        lengths[len(m.split())] += counts[m]
    size = max(lengths, key=lambda n: (lengths[n], n))
    tokens = []
    for pos in range(size):
        votes: Counter = Counter()
        spellings: dict[str, Counter] = {}
        for m in members:
            parts = m.split()
            if len(parts) != size:
                continue
            key = normalize(parts[pos])
            votes[key] += counts[m]
            spellings.setdefault(key, Counter())[parts[pos]] += counts[m]
        # Gana lo que se oye en la transcripción; después, lo más leído
        word = max(votes, key=lambda k: (heard[k] > 0 and len(k) > 2 and k not in _PARTICLES, votes[k]))
        tokens.append(_spelling(spellings[word]))
    return " ".join(tokens)


def _spelling(spellings: Counter) -> str:
    """Grafía de una palabra: con tilde si una parte apreciable de las lecturas la lleva."""
    total = sum(spellings.values())
    accented = {s: c for s, c in spellings.items() if strip_accents(s) != s}
    if accented and sum(accented.values()) / total >= ACCENT_SHARE:
        return max(accented, key=lambda s: accented[s])
    plain = {s: c for s, c in spellings.items() if strip_accents(s) == s} or spellings
    return max(plain, key=lambda s: plain[s])


def unify(vision: list[dict[str, Any]], texts: list[str], people: list[dict[str, Any]]) -> dict[str, Any]:
    """Grupos de nombres y correspondencia lectura → forma única."""
    counts, frames, cleaned = collect(vision)
    heard = heard_counts(texts)
    groups, mapping = [], {}
    for members in cluster(counts, frames):
        name = canonical(members, counts, heard)
        pid = match_name(name, people) if people else None
        if pid is None and people:
            pid = next((p for m in members if (p := match_name(m, people)) is not None), None)
        if pid is not None:
            name = next(p["name"] for p in people if p["id"] == pid)
        first = normalize(name).split()[0]
        groups.append({
            "canonical": name, "person_id": pid,
            "variants": dict(sorted(((m, counts[m]) for m in members), key=lambda x: -x[1])),
            "readings": sum(counts[m] for m in members),
            "frames": len(set().union(*(frames.get(m, set()) for m in members))),
            "heard": heard[first] if len(first) > 2 else 0,
        })
        for m in members:
            mapping[m] = name
    for raw, name in cleaned.items():
        mapping.setdefault(raw, "")
        if name:
            mapping[raw] = mapping[name]
    groups.sort(key=lambda g: -g["readings"])
    return {"groups": groups, "mapping": mapping}


def _first_name_map(groups: list[dict[str, Any]]) -> dict[str, str]:
    """Nombres de pila mal leídos que solo pueden ser de un grupo («Iker» → «Iosu»)."""
    owners: dict[str, set[str]] = {}
    for g in groups:
        for v in g["variants"]:
            owners.setdefault(v.split()[0], set()).add(g["canonical"].split()[0])
    return {w: next(iter(o)) for w, o in owners.items() if len(o) == 1 and w != next(iter(o)) and len(w) > 2}


def apply(vision: list[dict[str, Any]], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Reescribe los fotogramas con la forma única de cada nombre."""
    mapping = result["mapping"]
    variants = sorted(((raw, name) for raw, name in mapping.items() if raw and name and raw != name),
                      key=lambda x: -len(x[0]))
    firsts = _first_name_map(result["groups"])

    def rewrite(text: str) -> str:
        for raw, name in variants:
            text = re.sub(rf"(?<!\w){re.escape(raw)}(?!\w)", name, text)
        for raw, name in firsts.items():
            text = re.sub(rf"(?<!\w){re.escape(raw)}(?!\w)", name, text)
        return text

    out = []
    for v in vision:
        parts = []
        for raw in v.get("participantes") or []:
            name = mapping.get(raw, "")
            if name and name not in parts:
                parts.append(name)
        out.append({
            **v,
            "participantes": parts,
            "hablante_activo": mapping.get(v.get("hablante_activo") or "", ""),
            "descripcion": rewrite(v.get("descripcion") or ""),
            "texto_relevante": rewrite(v.get("texto_relevante") or ""),
        })
    return out


def screen_terms(vision: list[dict[str, Any]]) -> list[str]:
    """Términos vistos en pantalla, por frecuencia (para orientar a Whisper y al aprendizaje)."""
    terms: Counter = Counter()
    for r in vision:
        for t in [*r.get("terminos", []), *r.get("participantes", [])]:
            t = t.strip()
            if 2 < len(t) < 40:
                terms[t] += 1
    return [t for t, _ in terms.most_common(200)]


def run(ctx: JobContext) -> None:
    # Las lecturas originales se conservan; así la fase se puede repetir sin perder información
    raw = ctx.load("vision.raw.json")
    if raw is None:
        raw = ctx.load("vision.json", [])
        ctx.save("vision.raw.json", raw)
    texts = [u["text"] for u in ctx.load("utterances.json", [])]
    result = unify(raw, texts, ctx.people)
    vision = apply(raw, result)
    ctx.save("names.json", result["groups"])
    ctx.save("vision.json", vision)
    ctx.save("screen_terms.json", screen_terms(vision))
    ctx.report(1.0, f"{len(result['groups'])} nombres distintos en pantalla")
