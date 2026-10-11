"""Detección conservadora de términos del glosario mal transcritos.

Nunca reescribe libremente: solo propone sustituciones concretas de fragmentos que
suenan como un término del glosario. Las variantes que el usuario declara en el perfil
(«así se suele oír mal») y los cambios de mayúsculas se aplican directamente; el resto
de candidatos los valida el modelo de lenguaje.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

_TOKEN_RE = re.compile(r"\S+")
_EDGE_PUNCT = "¿¡\"'“”‘’()[]{}«».,;:!?…-"


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize(s: str) -> str:
    s = strip_accents(s.lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def phonetic(s: str) -> str:
    """Clave fonética aproximada para español (y anglicismos tal y como se pronuncian)."""
    s = normalize(s).replace(" ", "")
    rules = [
        ("ph", "f"),
        ("sh", "x"),
        ("ch", "x"),
        ("ll", "y"),
        ("qu", "k"),
        ("gue", "ge"),
        ("gui", "gi"),
        ("ce", "se"),
        ("ci", "si"),
        ("ge", "je"),
        ("gi", "ji"),
        ("c", "k"),
        ("z", "s"),
        ("v", "b"),
        ("w", "u"),
        ("h", ""),
        ("x", "ks"),
    ]
    for a, b in rules:
        s = s.replace(a, b)
    s = re.sub(r"y$", "i", s)
    s = re.sub(r"(.)\1+", r"\1", s)  # letras dobles
    return s


@dataclass
class Token:
    text: str  # sin puntuación en los bordes
    start: int  # posición en el texto del segmento
    end: int


def tokenize(text: str) -> list[Token]:
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        raw = m.group()
        lstrip = len(raw) - len(raw.lstrip(_EDGE_PUNCT))
        rstrip = len(raw) - len(raw.rstrip(_EDGE_PUNCT))
        core = raw[lstrip : len(raw) - rstrip] if rstrip else raw[lstrip:]
        if core:
            tokens.append(Token(core, m.start() + lstrip, m.end() - rstrip))
    return tokens


@dataclass
class Candidate:
    segment: int
    start: int
    end: int
    original: str
    suggestion: str
    score: float
    kind: str  # "variante" | "mayusculas" | "fonetica"
    context: str = ""
    # False para términos aprendidos por la IA: nunca se aplican sin validación del LLM
    trusted: bool = True
    accepted: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _context(text: str, start: int, end: int, width: int = 80) -> str:
    return text[max(0, start - width) : start] + "[[" + text[start:end] + "]]" + text[end : end + width]


def find_candidates(
    segments: list[str], glossary: list[dict[str, Any]], threshold: float = 86.0
) -> list[Candidate]:
    entries = []
    for g in glossary:
        term = (g.get("term") or "").strip()
        if not term:
            continue
        variants = [v.strip() for v in g.get("variants") or [] if v.strip()]
        entries.append((term, variants, g.get("trusted", True)))

    out: list[Candidate] = []
    for si, text in enumerate(segments):
        tokens = tokenize(text)
        taken: list[tuple[int, int]] = []

        def free(a: int, b: int) -> bool:
            return all(b <= x or a >= y for x, y in taken)

        def windows(n: int):
            for i in range(0, len(tokens) - n + 1):
                a, b = tokens[i].start, tokens[i + n - 1].end
                yield a, b, text[a:b], normalize(text[a:b])

        # 1) Coincidencias exactas (texto normalizado) y variantes declaradas: deterministas.
        #    Las apariciones ya correctas quedan protegidas frente a la búsqueda fonética.
        for term, variants, trusted in entries:
            n_term = normalize(term)
            n_vars = {normalize(v) for v in variants}
            for n in {len(n_term.split()), *(len(v.split()) for v in n_vars)}:
                for a, b, frag, n_frag in windows(n):
                    if not free(a, b):
                        continue
                    if n_frag == n_term:
                        if frag != term:
                            out.append(Candidate(si, a, b, frag, term, 100.0, "mayusculas", _context(text, a, b), trusted))
                        taken.append((a, b))
                    elif n_frag in n_vars:
                        out.append(Candidate(si, a, b, frag, term, 100.0, "variante", _context(text, a, b), trusted))
                        taken.append((a, b))

        # 2) Parecido fonético: se recogen todos los fragmentos y se eligen los mejores sin solaparse.
        fuzzy: list[Candidate] = []
        for term, variants, trusted in entries:
            n_term = normalize(term)
            if len(n_term.replace(" ", "")) < 4:
                continue  # términos muy cortos: demasiados falsos positivos
            keys = [phonetic(term), *(phonetic(v) for v in variants)]
            nw = len(n_term.split())
            for n in {nw - 1, nw, nw + 1} - {0}:
                for a, b, frag, n_frag in windows(n):
                    if not n_frag or not free(a, b):
                        continue
                    if n_term.replace(" ", "") in n_frag.replace(" ", ""):
                        continue  # ya contiene el término escrito bien («onmicrosoft.com» con «onMicrosoft»)
                    ph = phonetic(frag)
                    score = max(fuzz.ratio(ph, k) for k in keys)
                    if score >= threshold:
                        fuzzy.append(Candidate(si, a, b, frag, term, float(score), "fonetica", _context(text, a, b), trusted))
        for c in sorted(fuzzy, key=lambda c: (-c.score, c.end - c.start)):
            if free(c.start, c.end):
                out.append(c)
                taken.append((c.start, c.end))
    return out


def apply_candidates(text: str, candidates: list[Candidate]) -> str:
    for c in sorted(candidates, key=lambda c: c.start, reverse=True):
        text = text[: c.start] + c.suggestion + text[c.end :]
    return text
