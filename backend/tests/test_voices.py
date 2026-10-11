"""Comprobación por la voz y arreglos manuales de hablantes (lógica pura, con huellas sintéticas)."""

import numpy as np

from app.pipeline import voices as V

A, B, C = np.eye(3)  # voces sintéticas: Edgar (A), Iosu (B) y una tercera (C)


def _word(text, start, end, speaker):
    return {"word": text, "start": start, "end": end, "speaker": speaker}


def _windows(spans):
    """Ventanas de 1,5 s cada 0,5 s con la voz indicada por tramo: [(desde, hasta, vector)]."""
    out = []
    t = 0.0
    while t + V.WINDOW <= max(b for _, b, _ in spans) + 1e-9:
        mid = t + V.WINDOW / 2
        vec = next(v for a, b, v in spans if a <= mid < b)
        out.append((t, t + V.WINDOW, vec))
        t += V.HOP
    return out


def test_reassigns_a_clear_change_of_voice_inside_a_line():
    # pyannote dice que toda la línea es de A, pero de 3 a 6 s la voz es claramente B
    words = [_word(f"p{i}", i * 0.5, i * 0.5 + 0.4, "A") for i in range(18)]
    windows = _windows([(0, 3, A), (3, 6, B), (6, 9.5, A)])
    out = V.decide_words(words, windows, {"A": A, "B": B})
    who = {w["word"]: w["speaker"] for w in out}
    assert who["p0"] == "A" and who["p8"] == "B" and who["p16"] == "A"
    assert all(w["diar"] == "A" for w in out)


def test_unclear_voice_is_doubtful_not_reassigned():
    mixed = V.unit(A + 0.9 * B)  # casi a medias: no hay ventaja suficiente
    words = [_word(f"p{i}", i * 0.5, i * 0.5 + 0.4, "A") for i in range(8)]
    out = V.decide_words(words, _windows([(0, 4.5, mixed)]), {"A": A, "B": B})
    assert all(w["speaker"] == "A" for w in out)


def test_a_single_word_is_never_reassigned_alone():
    words = [_word("larga", 0, 2, "A"), _word("sí", 2.0, 2.2, "A"), _word("otra", 2.3, 4.5, "A")]
    windows = [(0.0, 1.5, A), (1.35, 2.85, B), (3.0, 4.5, A)]
    out = V.decide_words(words, windows, {"A": A, "B": B})
    assert out[1]["speaker"] == "A" and out[1]["doubt"]


def test_clean_centroids_ignore_misassigned_utterances():
    items = [("A", A, 5.0)] * 5 + [("A", B, 5.0)] + [("B", B, 5.0)] * 5
    cents = V.clean_centroids(items)
    assert cents["A"] @ A > 0.99  # la intervención de A con voz de B no contamina la voz de A


def test_overrides_win_and_survive_new_labels():
    words = [_word("hola", 0, 0.5, "SPEAKER_07"), _word("Edgar", 0.6, 1.0, "SPEAKER_07"), _word("adiós", 2, 2.5, "SPEAKER_02")]
    out = V.apply_overrides(words, [{"start": 0.55, "end": 1.1, "person_id": 9}], {9: "SPEAKER_03"})
    assert [w["speaker"] for w in out] == ["SPEAKER_07", "SPEAKER_03", "SPEAKER_02"]
    assert out[1]["manual"]


def test_utterances_carry_the_voice_mark():
    words = [{**_word("No", 0, 0.3, "A"), "diar": "A"}, {**_word("sé", 0.4, 0.7, "A"), "diar": "A"},
             {**_word("Vale", 1.0, 1.4, "B"), "diar": "A"}, {**_word("pero", 1.5, 1.8, "B"), "diar": "A"},
             {**_word("ya", 3.6, 3.9, "B"), "diar": "B", "doubt": True}]
    utts = V.utterances(words)
    assert [(u["speaker"], u["voice"]) for u in utts] == [("A", ""), ("B", "reasignada"), ("B", "dudosa")]


def test_detects_two_voices_in_one_speaker():
    rng = np.random.default_rng(1)
    noise = lambda v: V.unit(v + rng.normal(0, 0.05, 3))
    items = [{"speaker": "S0", "start": i * 10.0, "end": i * 10.0 + 5, "text": f"t{i}", "vec": noise(A)} for i in range(6)]
    items += [{"speaker": "S0", "start": 100 + i * 10.0, "end": 100 + i * 10.0 + 5, "text": f"u{i}", "vec": noise(C)}
              for i in range(5)]
    items += [{"speaker": "S1", "start": 300 + i * 10.0, "end": 305 + i * 10.0, "text": "x", "vec": noise(B)} for i in range(8)]
    splits = V.detect_splits(items)
    assert list(splits) == ["S0"]
    assert [g["seconds"] for g in splits["S0"]["groups"]] == [30.0, 25.0]
    assert len(splits["S0"]["groups"][1]["ranges"]) == 5
