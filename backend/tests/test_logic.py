from app.pipeline.glossary import apply_candidates, find_candidates, phonetic
from app.pipeline.transcript import assign_speakers, build_utterances, flatten_words, fmt_ts, group_turns
from app.pipeline.voice import dominant_visual_name, greedy_assign, match_name, person_centroids, similarity_matrix


def test_fmt_ts():
    assert fmt_ts(0) == "00:00:00"
    assert fmt_ts(3725.9) == "01:02:05"


def test_flatten_fills_missing_times():
    segs = [{"start": 1.0, "end": 3.0, "text": "son 25 euros", "words": [
        {"word": "son", "start": 1.0, "end": 1.3},
        {"word": "25"},
        {"word": "euros", "start": 2.0, "end": 2.5},
    ]}]
    w = flatten_words(segs)
    assert w[1]["start"] == 1.3 and w[1]["end"] == 2.0


def test_assign_and_utterances():
    words = [
        {"word": "Hola", "start": 0.0, "end": 0.4},
        {"word": "qué", "start": 0.5, "end": 0.7},
        {"word": "tal.", "start": 0.7, "end": 1.0},
        {"word": "Bien,", "start": 1.2, "end": 1.5},
        {"word": "gracias.", "start": 1.5, "end": 2.0},
        {"word": "Vale.", "start": 10.0, "end": 10.3},  # fuera de turnos, cerca de nada
    ]
    turns = [
        {"start": 0.0, "end": 1.1, "speaker": "A"},
        {"start": 1.1, "end": 2.2, "speaker": "B"},
    ]
    assign_speakers(words, turns)
    assert [w["speaker"] for w in words] == ["A", "A", "A", "B", "B", "B"]
    utts = build_utterances(words)
    assert [(u["speaker"], u["text"]) for u in utts] == [
        ("A", "Hola qué tal."), ("B", "Bien, gracias."), ("B", "Vale.")
    ]
    assert len(group_turns(utts)) == 3  # la pausa de 8 s no se une


def test_glossary_variants_case_and_phonetic():
    glossary = [
        {"term": "Salesforce", "variants": ["sels fors"]},
        {"term": "SAP", "variants": []},
        {"term": "Kubernetes", "variants": []},
    ]
    segs = [
        "Lo subimos a sels fors y luego al sap.",
        "El clúster de cubernetes está caído.",
        "Esto en Salesforce ya funciona.",
        "Mañana hablamos con el cliente.",
    ]
    cands = find_candidates(segs, glossary)
    kinds = {(c.segment, c.original, c.suggestion, c.kind) for c in cands}
    assert (0, "sels fors", "Salesforce", "variante") in kinds
    assert (0, "sap", "SAP", "mayusculas") in kinds
    assert (1, "cubernetes", "Kubernetes", "fonetica") in kinds
    assert not [c for c in cands if c.segment in (2, 3)]
    fixed = apply_candidates(segs[0], [c for c in cands if c.segment == 0])
    assert fixed == "Lo subimos a Salesforce y luego al SAP."


def test_phonetic_key():
    assert phonetic("cubernetes") == phonetic("Kubernetes")
    assert phonetic("llave") == phonetic("yabe")


def test_voice_matching():
    people = {1: [[1.0, 0.0, 0.0], [0.9, 0.1, 0.0]], 2: [[0.0, 1.0, 0.0]]}
    cents = person_centroids(people)
    sims = similarity_matrix({"S0": [0.95, 0.05, 0.0], "S1": [0.1, 0.9, 0.1], "S2": [0.0, 0.0, 1.0]}, cents)
    res = greedy_assign(sims, threshold=0.5)
    assert res["S0"][0] == 1 and res["S1"][0] == 2 and "S2" not in res


def test_names_and_visual_hints():
    people = [{"id": 1, "name": "María López", "aliases": ["Maria L."]}, {"id": 2, "name": "Juan", "aliases": []}]
    assert match_name("maria lopez", people) == 1
    assert match_name("López, María", people) == 1
    assert match_name("Pedro", people) is None
    assert dominant_visual_name({"Ana": 5, "Luis": 1}) == "Ana"
    assert dominant_visual_name({"Ana": 1}) is None
    assert dominant_visual_name({"Ana": 3, "Luis": 3}) is None
