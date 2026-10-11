"""Comparación de huellas de voz y propuesta de identidades para los hablantes."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
from rapidfuzz import fuzz

from .glossary import normalize


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def person_centroids(embeddings: dict[int, list[list[float]]]) -> dict[int, np.ndarray]:
    """Centroide normalizado de las huellas de cada persona."""
    out = {}
    for pid, vecs in embeddings.items():
        if vecs:
            out[pid] = _unit(np.mean([_unit(np.asarray(v, dtype=np.float32)) for v in vecs], axis=0))
    return out


def similarity_matrix(speakers: dict[str, list[float]], centroids: dict[int, np.ndarray]) -> dict[str, dict[int, float]]:
    sims: dict[str, dict[int, float]] = {}
    for label, vec in speakers.items():
        u = _unit(np.asarray(vec, dtype=np.float32))
        sims[label] = {pid: float(np.dot(u, c)) for pid, c in centroids.items()}
    return sims


def greedy_assign(sims: dict[str, dict[int, float]], threshold: float) -> dict[str, tuple[int, float]]:
    """Empareja hablantes con personas (una persona como mucho por hablante y viceversa)."""
    pairs = sorted(
        ((s, label, pid) for label, row in sims.items() for pid, s in row.items() if s >= threshold),
        reverse=True,
    )
    used_l, used_p, out = set(), set(), {}
    for s, label, pid in pairs:
        if label in used_l or pid in used_p:
            continue
        out[label] = (pid, s)
        used_l.add(label)
        used_p.add(pid)
    return out


def match_name(name: str, people: list[dict[str, Any]], threshold: float = 85.0) -> int | None:
    """Busca una persona por nombre o alias (tolerante a mayúsculas, tildes y orden)."""
    n = normalize(name)
    if not n:
        return None
    best, best_s = None, 0.0
    for p in people:
        for cand in [p["name"], *(p.get("aliases") or [])]:
            s = fuzz.token_set_ratio(n, normalize(cand))
            if s > best_s:
                best, best_s = p["id"], s
    return best if best_s >= threshold else None


def assign_visual_names(
    hints: dict[str, dict[str, int]], min_count: int = 2, min_purity: float = 0.5
) -> dict[str, str]:
    """Nombre en pantalla de cada hablante: cada nombre a un solo hablante, por número de coincidencias.

    - el nombre debe ser el más leído del hablante, sin empate con otro;
    - `min_purity`: y ese hablante debe concentrar esa parte de las lecturas del nombre. Un nombre
      repartido entre varias voces no es fiable (p. ej. quien presenta queda resaltado mientras
      hablan otros).
    """
    clean = {lab: {n: c for n, c in h.items() if n and not n.startswith("_")} for lab, h in hints.items()}
    per_name: Counter = Counter()
    for h in clean.values():
        per_name.update(h)
    pairs = sorted(((c, lab, n) for lab, h in clean.items() for n, c in h.items()), reverse=True)
    out: dict[str, str] = {}
    used: set[str] = set()
    for c, lab, n in pairs:
        if lab in out or n in used or c < min_count:
            continue
        rivals = [x for m, x in clean[lab].items() if m != n]
        if c > max(rivals, default=0) and c / per_name[n] >= min_purity:
            out[lab] = n
            used.add(n)
    return out
