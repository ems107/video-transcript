"""Fase «voices»: comprueba por la voz a quién pertenece cada tramo de la transcripción.

La separación de hablantes (pyannote) se equivoca en cambios de turno, saludos y frases cortas, y puede
juntar dos voces en un mismo hablante. Esta fase:
1. calcula la voz de cada hablante con sus intervenciones largas y claras;
2. compara ventanas de 1,5 s de cada intervención con esas voces y decide, palabra a palabra, si el
   tramo es de otro hablante (se reasigna), si no está claro (se marca «dudosa») o si está bien;
3. detecta hablantes cuyas intervenciones forman dos grupos de voz distintos (dos personas juntas).
Los arreglos manuales del usuario (`SpeakerOverride`) se aplican siempre después y mandan.

Umbrales medidos con un vídeo real de 37 min y 9 tramos revisados por el usuario: en los aciertos, la
ventana se parecía 0,6–0,86 a su voz y sacaba más de 0,3 al segundo hablante; en cambios de voz cortos
(un saludo) el parecido bajaba a ~0,4 con margen ~0,25.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import JobContext, free_gpu
from .transcript import assign_speakers, build_utterances, flatten_words

WINDOW, HOP, TRIM = 1.5, 0.5, 0.2
CLEAN_MIN = 3.0  # duración mínima de una intervención para calcular la voz de su hablante
MIN_SIM = 0.35  # parecido mínimo con la voz ganadora para reasignar
MARGIN = 0.2  # ventaja mínima sobre el segundo hablante para reasignar
DOUBT_MARGIN = 0.1  # por debajo, si apunta a otro hablante, la palabra queda «dudosa»
MIN_RUN = 0.4  # un tramo reasignado debe durar al menos esto (evita saltos de una palabra suelta)
SPLIT_SILHOUETTE, SPLIT_SECONDS, SPLIT_MAX_SIM = 0.45, 15.0, 0.5


def unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def clean_centroids(items: list[tuple[str, np.ndarray, float]]) -> dict[str, np.ndarray]:
    """Voz de cada hablante con sus intervenciones largas, quitando las que se parecen más a otro."""
    long_ = [(lab, unit(v)) for lab, v, d in items if d >= CLEAN_MIN]
    labels = sorted({lab for lab, _ in long_})
    cents = {lab: unit(np.mean([v for x, v in long_ if x == lab], axis=0)) for lab in labels}
    if len(cents) < 2:
        return cents
    keep = [(lab, v) for lab, v in long_ if max(cents, key=lambda c: float(v @ cents[c])) == lab]
    out = {}
    for lab in labels:
        vecs = [v for x, v in keep if x == lab] or [v for x, v in long_ if x == lab]
        out[lab] = unit(np.mean(vecs, axis=0))
    return out


def decide_words(words: list[dict[str, Any]], windows: list[tuple[float, float, np.ndarray]],
                 cents: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    """Hablante de cada palabra según las ventanas que la cubren. Añade `diar` (el de pyannote) y `doubt`."""
    labels = list(cents)
    if len(labels) < 2:
        return [{**w, "diar": w.get("speaker", ""), "doubt": False} for w in words]
    C = np.stack([cents[lab] for lab in labels])
    starts = np.array([a for a, _, _ in windows]) if windows else np.array([])
    sims = np.stack([C @ unit(v) for _, _, v in windows]) if windows else np.zeros((0, len(labels)))
    out = []
    for w in words:
        own = w.get("speaker", "")
        mid = (w["start"] + w["end"]) / 2
        cover = np.where((starts <= mid) & (starts + WINDOW >= mid))[0] if len(starts) else []
        new, doubt = own, False
        if len(cover):
            # Pesa más la ventana centrada en la palabra: las de los lados recogen ya la voz vecina
            weight = np.clip(1 - np.abs(starts[cover] + WINDOW / 2 - mid) / (WINDOW / 2), 0.05, None)
            avg = (sims[cover] * weight[:, None]).sum(axis=0) / weight.sum()
            order = np.argsort(-avg)
            best, second = labels[order[0]], float(avg[order[1]])
            gain = float(avg[order[0]]) - second
            if best != own:
                if avg[order[0]] >= MIN_SIM and gain >= MARGIN:
                    new = best
                elif gain >= DOUBT_MARGIN or own not in cents:
                    doubt = True
        out.append({**w, "speaker": new, "diar": own, "doubt": doubt})
    return _min_runs(out)


def _min_runs(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deshace reasignaciones demasiado cortas (las deja como dudosas)."""
    i = 0
    while i < len(words):
        if words[i]["speaker"] == words[i]["diar"]:
            i += 1
            continue
        j = i
        while j + 1 < len(words) and words[j + 1]["speaker"] == words[i]["speaker"] != words[j + 1]["diar"]:
            j += 1
        if words[j]["end"] - words[i]["start"] < MIN_RUN:
            for k in range(i, j + 1):
                words[k] = {**words[k], "speaker": words[k]["diar"], "doubt": True}
        i = j + 1
    return words


def apply_overrides(words: list[dict[str, Any]], overrides: list[dict[str, Any]],
                    label_for: dict[int, str]) -> list[dict[str, Any]]:
    """Arreglos manuales: las palabras dentro de cada tramo pasan al hablante de esa persona. Mandan sobre todo."""
    out = []
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        hit = next((o for o in reversed(overrides) if o["start"] <= mid <= o["end"]), None)
        if hit:
            w = {**w, "speaker": label_for[hit["person_id"]], "doubt": False, "manual": True}
        out.append(w)
    return out


def utterances(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Intervenciones con su marca de voz: «reasignada» si la voz cambió el hablante, «dudosa» si no está claro."""
    utts = build_utterances(words)
    i = 0
    for u in utts:
        mine = []
        while i < len(words) and words[i]["start"] < u["end"] + 1e-6:
            if words[i]["word"].strip():
                mine.append(words[i])
            i += 1
        if any(w.get("manual") for w in mine):
            u["voice"] = ""
        elif any(w.get("doubt") for w in mine):
            u["voice"] = "dudosa"
        elif any(w.get("diar", w["speaker"]) != w["speaker"] for w in mine):
            u["voice"] = "reasignada"
        else:
            u["voice"] = ""
    return utts


def _kmeans2(Y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    best = None
    for _ in range(10):
        c = Y[rng.choice(len(Y), 2, replace=False)]
        for _ in range(50):
            a = np.argmax(Y @ c.T, axis=1)
            c = np.array([unit(Y[a == k].mean(0)) if (a == k).any() else c[k] for k in range(2)])
        score = sum(float((Y[a == k] @ c[k]).sum()) for k in range(2))
        if best is None or score > best[0]:
            best = (score, a, c)
    return best[1], best[2]


def _silhouette(Y: np.ndarray, a: np.ndarray) -> float:
    D = 1 - Y @ Y.T
    s = []
    for i in range(len(Y)):
        same = a == a[i]
        if same.sum() < 2 or (~same).sum() == 0:
            continue
        ai = D[i, same].sum() / (same.sum() - 1)
        bi = D[i, ~same].mean()
        s.append((bi - ai) / max(ai, bi))
    return float(np.mean(s)) if s else 0.0


def detect_splits(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Hablantes cuyas intervenciones forman dos grupos de voz claramente distintos.

    `items`: [{speaker, start, end, text, vec}] de intervenciones largas, ya reasignadas.
    """
    out = {}
    for lab in sorted({x["speaker"] for x in items}):
        mine = [x for x in items if x["speaker"] == lab]
        if len(mine) < 6:
            continue
        Y = np.stack([unit(np.asarray(x["vec"])) for x in mine])
        a, c = _kmeans2(Y)
        secs = [sum(x["end"] - x["start"] for x, k in zip(mine, a) if k == g) for g in range(2)]
        sil = _silhouette(Y, a)
        if min(secs) >= SPLIT_SECONDS and sil >= SPLIT_SILHOUETTE and float(c[0] @ c[1]) <= SPLIT_MAX_SIM:
            groups = []
            for g in sorted(range(2), key=lambda g: -secs[g]):
                members = sorted((x for x, k in zip(mine, a) if k == g), key=lambda x: x["start"])
                # `centroid`: la voz del grupo, para proponer de quién es (`speaker_fix.split_suggestions`)
                groups.append({"seconds": round(secs[g], 1), "centroid": [float(x) for x in c[g]],
                               "ranges": [[x["start"], x["end"]] for x in members],
                               "samples": [{"start": x["start"], "end": x["end"], "text": x["text"]}
                                           for x in sorted(members, key=lambda x: x["start"] - x["end"])[:5]]})
            out[lab] = {"silhouette": round(sil, 2), "groups": groups}
    return out


def load_words(ctx: JobContext) -> list[dict[str, Any]]:
    """Palabras con su hablante: las de esta fase o, en trabajos anteriores a ella, las de pyannote."""
    words = ctx.load("words.json")
    if words is None:
        turns = ctx.load("diarization.json", {}).get("turns", [])
        words = assign_speakers(flatten_words(ctx.load("aligned.json")["segments"]), turns)
    return words


def rebuild(ctx: JobContext, overrides: list[dict[str, Any]], label_for: dict[int, str]) -> None:
    """Reconstruye `utterances.json` con las palabras y los arreglos manuales actuales."""
    words = apply_overrides(load_words(ctx), overrides, label_for)
    ctx.save("utterances.json", utterances(words))


def run(ctx: JobContext) -> None:
    from pathlib import Path

    import torch
    import whisperx
    from pyannote.audio import Inference, Model
    from pyannote.core import Segment

    diar = ctx.load("diarization.json")
    words = assign_speakers(flatten_words(ctx.load("aligned.json")["segments"]), diar["turns"])
    utts = build_utterances(words)
    ctx.report(0.0, "Cargando el modelo de voz")
    model = Model.from_pretrained(Path(ctx.settings.diarization_model_dir) / "embedding")
    inf = Inference(model, window="whole", device=torch.device("cuda"))
    audio = whisperx.load_audio(str(ctx.path("audio.wav")))
    file = {"waveform": torch.from_numpy(audio).unsqueeze(0), "sample_rate": 16000}
    total = len(audio) / 16000

    def embed(a: float, b: float) -> np.ndarray | None:
        a, b = max(0.0, a), min(total, b)
        if b - a < 0.5:
            return None
        v = np.asarray(inf.crop(file, Segment(a, b))).reshape(-1)
        return unit(v) if np.all(np.isfinite(v)) and np.linalg.norm(v) > 0 else None

    # 1) Voz de cada intervención larga
    items = []
    for i, u in enumerate(utts):
        ctx.check_cancel()
        if u["end"] - u["start"] >= WINDOW:
            v = embed(u["start"] + TRIM, u["end"] - TRIM)
            if v is not None:
                items.append({"speaker": u["speaker"], "start": u["start"], "end": u["end"], "text": u["text"], "vec": v})
        if i % 20 == 0:
            ctx.report(0.05 + 0.25 * i / max(1, len(utts)), "Calculando la voz de cada intervención")
    cents = clean_centroids([(x["speaker"], x["vec"], x["end"] - x["start"]) for x in items])

    # 2) Ventanas dentro de cada intervención larga
    windows = []
    long_utts = [u for u in utts if u["end"] - u["start"] >= WINDOW]
    for i, u in enumerate(long_utts):
        ctx.check_cancel()
        t = u["start"]
        while True:
            a = min(t, u["end"] - WINDOW)
            v = embed(a, a + WINDOW)
            if v is not None:
                windows.append((a, a + WINDOW, v))
            if a + WINDOW >= u["end"]:
                break
            t += HOP
        if i % 10 == 0:
            ctx.report(0.3 + 0.6 * i / max(1, len(long_utts)), "Comprobando las voces")
    model = inf = None  # libera la memoria de la GPU
    free_gpu()

    words = decide_words(words, windows, cents)
    new_utts = utterances(words)

    # 3) Dos voces en un mismo hablante (con las intervenciones ya reasignadas)
    reassigned = []
    for x in items:
        ws = [w for w in words if x["start"] <= (w["start"] + w["end"]) / 2 <= x["end"]]
        labs = {w["speaker"] for w in ws}
        if len(labs) == 1:
            reassigned.append({**x, "speaker": labs.pop()})
    splits = detect_splits(reassigned)

    ctx.save("words.json", words)
    ctx.save("utterances.json", new_utts)
    diar["embeddings"] = {lab: [float(x) for x in c] for lab, c in cents.items()} or diar["embeddings"]
    diar["speaking_time"] = _speaking_time(new_utts)
    ctx.save("diarization.json", diar)
    changed = sum(1 for u in new_utts if u["voice"] == "reasignada")
    doubtful = sum(1 for u in new_utts if u["voice"] == "dudosa")
    ctx.save("voices.json", {"splits": splits, "reassigned": changed, "doubtful": doubtful,
                             "windows": len(windows), "speakers": sorted(cents)})
    ctx.report(1.0, f"{changed} tramos reasignados por la voz, {doubtful} dudosos")


def _speaking_time(utts: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for u in utts:
        out[u["speaker"]] = out.get(u["speaker"], 0.0) + (u["end"] - u["start"])
    return out
