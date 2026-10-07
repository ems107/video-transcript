import numpy as np

from app.knowledge import (
    add_evidence,
    duplicate_candidates,
    excerpt_at,
    find_match,
    item_key,
    make_snapshot,
    merged_aliases,
    resolve_name,
    restore_plan,
    single_value_conflicts,
    speaker_person,
    term_candidates,
    term_occurrences,
    version_diff,
)

UTTS = [
    {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00", "text": "Hoy revisamos el despliegue del CRM en Atlas."},
    {"start": 6.0, "end": 9.0, "speaker": "SPEAKER_01", "text": "El equipo de QA ya validó Atlas."},
    {"start": 60.0, "end": 64.0, "speaker": "SPEAKER_00", "text": "Lo del CRM lo vemos el lunes con DevOps."},
]
VISION = [{"t": 30.0, "texto_relevante": "Tablero Jira - Sprint 12", "terminos": ["Jira"], "descripcion": ""}]


def test_term_candidates_and_occurrences():
    cands = term_candidates(UTTS, ["Jira", "Atlas"], exclude={"atlas"})
    assert cands[0] == "Jira"
    assert "CRM" in cands  # sigla repetida
    assert "Atlas" not in cands  # ya está en el perfil
    assert "Hoy" not in cands  # mayúscula de inicio de frase
    assert term_occurrences("crm", UTTS, VISION) == [0.0, 60.0]
    assert term_occurrences("Jira", UTTS, VISION) == [30.0]
    assert term_occurrences("Zeus", UTTS, VISION) == []  # término inventado: sin apariciones


def test_excerpt_at():
    lines = excerpt_at(UTTS, 7.0)
    assert [l["label"] for l in lines] == ["SPEAKER_00", "SPEAKER_01"]
    assert excerpt_at(UTTS, 200.0) == []


def test_find_match_and_evidence():
    items = [
        {"id": 1, "kind": "termino", "key": item_key("termino", {"term": "Salesforce"}), "status": "aceptado"},
        {"id": 2, "kind": "dato", "key": item_key("dato", {"text": "Lleva la integración con Salesforce"}),
         "status": "rechazado"},
    ]
    assert find_match("termino", item_key("termino", {"term": "salesforce"}), items)["id"] == 1
    assert find_match("termino", item_key("termino", {"term": "Salesforces"}), items) is None
    assert find_match("dato", item_key("dato", {"text": "lleva la integracion con Salesforce."}), items)["id"] == 2
    assert find_match("dato", item_key("dato", {"text": "Vive en Valencia"}), items) is None

    ev, new = add_evidence([], {"video_id": 1, "t": 3})
    ev, new2 = add_evidence(ev, {"video_id": 1, "t": 9})
    assert new and not new2 and len(ev) == 1  # el mismo vídeo no cuenta dos veces


def test_resolve_name():
    speakers = {"SPEAKER_00": "María López", "SPEAKER_01": "Hablante 2"}
    people = [{"id": 7, "name": "Pedro Ruiz", "aliases": ["Perico"]}, {"id": 8, "name": "María López", "aliases": []}]
    assert resolve_name("María", speakers, people) == ("speaker", "SPEAKER_00")
    assert resolve_name("Hablante 2", speakers, people) == ("speaker", "SPEAKER_01")
    assert resolve_name("Hablante 3", speakers, people) is None
    assert resolve_name("Perico", speakers, people) == ("person", 7)
    assert resolve_name("Lucía", speakers, people) == ("new", "Lucía")
    assert resolve_name("el cliente", speakers, people) is None


def test_speaker_person():
    auto = 0.75
    assert speaker_person({"confirmed": True, "person_id": 3}, auto) == 3
    assert speaker_person({"suggested_person_id": 4, "source": "voz", "confidence": 0.9}, auto) == 4
    assert speaker_person({"suggested_person_id": 4, "source": "voz", "confidence": 0.6}, auto) is None
    assert speaker_person({"suggested_person_id": 4, "source": "pantalla", "confidence": 0.7}, auto) is None
    assert speaker_person({"suggested_person_id": 5, "source": "micrófono", "confidence": 0.95}, auto) == 5


def test_single_value_conflicts():
    accepted = [{"id": 1, "kind": "dato", "category": "cargo"}, {"id": 2, "kind": "dato", "category": "proyecto"}]
    assert single_value_conflicts({"id": 9, "kind": "dato", "category": "cargo"}, accepted) == [1]
    assert single_value_conflicts({"id": 9, "kind": "dato", "category": "proyecto"}, accepted) == []


def test_snapshot_restore_roundtrip():
    a = {"id": 1, "kind": "termino", "category": "", "data": {"term": "CRM"}, "status": "aceptado"}
    b = {"id": 2, "kind": "contexto", "category": "proyecto", "data": {"text": "Atlas es el proyecto"},
         "status": "aceptado"}
    snap = make_snapshot({"context": "manual"}, [a, b], person_ids=[3, 1])
    assert snap["person_ids"] == [1, 3]
    # Después: se retiró 1, se editó 2 y se aceptó 3
    current = [
        {**a, "status": "retirado"},
        {**b, "data": {"text": "Atlas es el proyecto principal"}},
        {"id": 3, "kind": "termino", "category": "", "data": {"term": "Jira"}, "status": "aceptado"},
    ]
    plan = restore_plan(snap, current)
    assert plan["accept"] == [1] and plan["retire"] == [3]
    assert plan["update"] == {2: {"data": {"text": "Atlas es el proyecto"}, "category": "proyecto"}}
    assert plan["create"] == []
    assert restore_plan(snap, [])["create"] and len(restore_plan(snap, [])["create"]) == 2

    later = make_snapshot({"context": "otro"}, [current[1], current[2]], person_ids=[1, 3])
    d = version_diff(snap, later)
    assert d["added"] == ["Jira"] and d["removed"] == ["CRM"]
    assert d["changed"] == ["Atlas es el proyecto principal"] and d["manual"] == ["context"]


def test_duplicates_and_merge_aliases():
    people = [
        {"id": 1, "name": "María López", "aliases": []},
        {"id": 2, "name": "María", "aliases": []},
        {"id": 3, "name": "Juan Pérez", "aliases": []},
        {"id": 4, "name": "J. P.", "aliases": []},
    ]
    v = np.array([1.0, 0.0])
    dups = duplicate_candidates(people, {3: v, 4: v})
    assert {"a": 1, "b": 2, "reasons": ["nombre"]} in dups
    assert {"a": 3, "b": 4, "reasons": ["voz"]} in dups
    assert len(dups) == 2
    assert merged_aliases({"name": "María López", "aliases": ["Mari"]}, {"name": "María", "aliases": ["mari"]}) \
        == ["Mari", "María"]


PROFILE = {
    "name": "Trabajo",
    "glossary": [{"term": "Salesforce", "variants": ["sels fors"], "definition": "CRM"}],
    "summary_sections": ["Estado"],
    "learned": [
        {"kind": "termino", "category": "", "data": {"term": "Atlas", "definition": "Proyecto"}, "seen_count": 3},
        {"kind": "termino", "category": "", "data": {"term": "salesforce", "definition": ""}, "seen_count": 1},
        {"kind": "contexto", "category": "cliente", "data": {"text": "Acme es el cliente principal"}, "seen_count": 2},
        {"kind": "seccion", "category": "", "data": {"title": "Riesgos"}, "seen_count": 1},
    ],
}


def test_effective_glossary_and_sections():
    from app.knowledge import effective_glossary, effective_sections

    g = effective_glossary(PROFILE)
    assert [(e["term"], e["trusted"]) for e in g] == [("Salesforce", True), ("Atlas", False)]
    assert effective_sections(PROFILE) == ["Estado", "Riesgos"]


def test_learned_terms_never_applied_without_llm():
    from app.knowledge import effective_glossary
    from app.pipeline.glossary import find_candidates

    cands = find_candidates(["Lo vemos en atlas y en sels fors."], effective_glossary(PROFILE))
    by = {c.original: c for c in cands}
    assert by["sels fors"].trusted and by["sels fors"].kind == "variante"
    assert not by["atlas"].trusted and by["atlas"].kind == "mayusculas"


def test_profile_block_and_people():
    from app.knowledge import learned_block, person_line, prompt_people
    from app.prompts import profile_block

    block = learned_block(PROFILE)
    assert "[Cliente] Acme es el cliente principal" in block and "Término «Atlas»: Proyecto" in block
    assert "salesforce" not in block  # ya está en el glosario manual
    assert learned_block(PROFILE, max_chars=10).count("\n") == 0

    maria = {"id": 1, "name": "María", "role": "", "notes": "", "in_profile": True, "facts": [
        {"category": "cargo", "text": "Jefa de proyecto"}, {"category": "organizacion", "text": "Acme"},
        {"category": "proyecto", "text": "Lleva Atlas"}]}
    other = {"id": 2, "name": "Pedro", "role": "", "facts": [], "in_profile": False}
    assert person_line(maria) == "- María (Jefa de proyecto; Organización: Acme): Lleva Atlas"
    assert prompt_people([other, maria]) == [maria]
    assert prompt_people([other]) == [other]  # sin perfil: cualquiera
    text = profile_block(PROFILE, [maria, other])
    assert "Aprendido de vídeos anteriores" in text and "Pedro" not in text


def test_whisper_prompt_learned_after_manual():
    from app.pipeline.asr import build_whisper_prompt

    prompt = build_whisper_prompt(PROFILE, [], ["Jira"])
    assert prompt.index("Salesforce") < prompt.index("Atlas") < prompt.index("Jira")
