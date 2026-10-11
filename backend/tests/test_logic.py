from app.pipeline.glossary import apply_candidates, find_candidates, phonetic
from app.pipeline.transcript import assign_speakers, build_utterances, flatten_words, fmt_ts, group_turns
from app.pipeline.voice import assign_visual_names, greedy_assign, match_name, person_centroids, similarity_matrix


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
    assert assign_visual_names({"S0": {"Ana": 5, "Luis": 1}}) == {"S0": "Ana"}
    assert assign_visual_names({"S0": {"Ana": 1}}) == {}
    assert assign_visual_names({"S0": {"Ana": 3, "Luis": 3}}) == {}  # empate: no se decide
    # Vídeo real a 2560 px: José Luis 3, Iosu 2 (resaltado de más), Edgar 1 → gana José Luis
    assert assign_visual_names({"S1": {"Jose": 3, "Iosu": 2, "Edgar": 1}, "S3": {"Iosu": 46}}) == {
        "S1": "Jose", "S3": "Iosu"}
    # Cada nombre a un solo hablante: el que más coincide (vídeo real: Iosu 40 frente a 3)
    hints = {"S3": {"Iosu": 40, "Jose": 1}, "S2": {"Iosu": 3}, "S1": {"Jose": 2}, "S0": {"Iosu": 1, "Jose": 1}}
    assert assign_visual_names(hints) == {"S3": "Iosu", "S1": "Jose"}
    # Quien presenta sale resaltado mientras hablan otros: repartido entre voces, no se asigna
    spread = {"S1": {"Presenta": 10}, "S4": {"Presenta": 11}, "S5": {"Presenta": 9}, "S6": {"Presenta": 6}}
    assert assign_visual_names(spread) == {}


def _frame(parts, active=""):
    return {"t": 0.0, "participantes": parts, "hablante_activo": active, "descripcion": "", "texto_relevante": ""}


def test_names_unify_variants_of_one_person():
    from app.pipeline import names

    # Lecturas reales del vídeo de prueba: el mismo recuadro leído de muchas formas
    long_ = ["Iosu Urcelay Fernandez De Arroyabe"] * 3 + ["Iker Urcelay Fernandez De Arroyabe"] * 4 + [
        "Ione Urcelay Fernández De Arroyabe", "Urcelay Fernandez De Arroyabe, Iosu"]
    vision = [_frame([n, "Sandra", "Jose Luis Perez Rodriguez"], n) for n in long_]
    vision += [_frame(["Jose Luis Pérez Rodríguez", "Sandia", "Edge"])] * 3 + [_frame(["Edgar", "Sandra"])]
    vision += [_frame(["Usuario con gafas (sin nombre visible)"])]
    r = names.unify(vision, ["Pues a ver, Iosu, esta pregunta", "Gracias, Sandra y Edgar"], [])
    canon = {g["canonical"] for g in r["groups"]}
    # «Iker» se lee más, pero «Iosu» es el que se oye («Edge» tampoco se oye y «Edgar» sí);
    # las tildes se conservan si aparecen en una parte apreciable de las lecturas
    assert canon == {"Iosu Urcelay Fernandez De Arroyabe", "Sandra", "Jose Luis Pérez Rodríguez", "Edgar"}
    out = names.apply(vision, r)
    assert out[3]["hablante_activo"] == "Iosu Urcelay Fernandez De Arroyabe"
    assert out[-1]["participantes"] == []


def test_names_never_merge_people_seen_together():
    from app.pipeline import names

    vision = [_frame(["Ana Ruiz", "Ana Ruiz Gil"]), _frame(["Ana Ruiz"])]
    r = names.unify(vision, [], [])
    assert len(r["groups"]) == 2


def test_names_use_known_person():
    from app.pipeline import names

    people = [{"id": 7, "name": "Iosu Urcelay", "aliases": []}]
    r = names.unify([_frame(["Iosu Urcelay Fernandez De Arroyabe"])] * 2, [], people)
    assert r["groups"][0]["canonical"] == "Iosu Urcelay" and r["groups"][0]["person_id"] == 7


def test_names_rewrite_descriptions():
    from app.pipeline import names

    vision = [{**_frame(["Iosu Urcelay"], "Iker Urcelay"), "descripcion": "Habla Iker Urcelay; Iker señala"}]
    vision += [_frame(["Iosu Urcelay"])] * 3
    out = names.apply(vision, names.unify(vision, [], []))
    assert out[0]["descripcion"] == "Habla Iosu Urcelay; Iosu señala"


def test_speaker_at_borders_and_gaps():
    from app.pipeline.transcript import speaker_at

    turns = [{"start": 0.2, "end": 5.8, "speaker": "A"}, {"start": 24.0, "end": 32.0, "speaker": "B"},
             {"start": 32.0, "end": 40.4, "speaker": "A"}]
    assert speaker_at(turns, 0.0) == "A"  # en el silencio inicial: el más cercano
    assert speaker_at(turns, 32.0) == "A"  # en el borde: el que empieza
    assert speaker_at(turns, 28.0) == "B"
    assert speaker_at(turns, 15.0) is None  # lejos de todo


def test_every_list_in_the_schemas_has_a_limit():
    from app import prompts

    def lists(schema, path=""):
        if isinstance(schema, dict):
            if schema.get("type") == "array":
                yield path, schema
            for k, v in (schema.get("properties") or {}).items():
                yield from lists(v, f"{path}.{k}")
            yield from lists(schema.get("items"), path + "[]")

    for s in (prompts.VISION_SCHEMA, prompts.CORRECT_SCHEMA, prompts.CHUNK_SCHEMA, prompts.FINAL_SCHEMA,
              prompts.LEARN_SCHEMA):
        for path, arr in lists(s):
            assert arr.get("maxItems"), path
    assert prompts.CHUNK_SCHEMA["properties"]["apodos"]["maxItems"] == 10
