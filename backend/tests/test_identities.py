"""Quién es quién: identidades deducidas del contexto, apodos y su uso en los hablantes."""

from datetime import datetime

from app import services
from app.knowledge import person_line
from app.models import Person, Speaker, Video
from app.pipeline.analyze import collect_identities, participants
from app.pipeline.asr import build_whisper_prompt
from app.prompts import who_block

ON_SCREEN = ["Iosu Urcelay Fernandez De Arroyabe", "Jose Luis Pérez Rodríguez", "Sandra", "Edgar"]
HEARD = "Pásales a Edgar y a Sandra la protección de datos. ¿Puedes dejar de compartir, Selu? Selu, contigo."


def _chunk(identities=(), nicknames=()):
    return {"identidades": [dict(zip(("hablante", "nombre", "motivo", "t"), x)) for x in identities],
            "apodos": [dict(zip(("apodo", "nombre", "t"), x)) for x in nicknames]}


def test_identities_are_verified_and_unique():
    unnamed = {"Hablante 1": "S2", "Hablante 4": "S0"}
    taken = ["Iosu Urcelay Fernandez De Arroyabe", "Jose Luis Pérez Rodríguez"]
    partials = [
        _chunk([("Hablante 1", "Edgar Martínez", "Le preguntan a Edgar y responde", "00:10:00"),
                ("Hablante 4", "Sandra", "Se dirigen a Sandra y responde", "00:12:00"),
                ("Hablante 7", "Sandra", "no existe ese hablante", "00:01:00")]),
        _chunk([("Hablante 1", "Edgar", "Responde por su nombre", "00:20:00"),
                ("Hablante 4", "Iosu", "ya es de otro hablante", "00:21:00")]),
    ]
    ids, _ = collect_identities(partials, unnamed, ON_SCREEN + taken, taken, HEARD)
    # «Edgar Martínez» se reconoce como el «Edgar» de la pantalla; Sandra gana 1 a 0 porque «Iosu» ya
    # pertenece a otro hablante
    assert ids["S2"]["nombre"] == "Edgar" and ids["S2"]["votos"] == 2
    assert ids["S0"]["nombre"] == "Sandra"


def test_identities_reject_invented_and_doubtful_names():
    unnamed = {"Hablante 1": "S1", "Hablante 2": "S2"}
    partials = [_chunk([("Hablante 1", "Roberto", "inventado: ni en pantalla ni se oye", "00:01:00"),
                        ("Hablante 2", "Sandra", "", "00:02:00")]),
                _chunk([("Hablante 2", "Edgar", "", "00:03:00")])]
    ids, _ = collect_identities(partials, unnamed, ON_SCREEN, [], HEARD)
    assert ids == {}  # Roberto no consta; Hablante 2 empata entre dos nombres


def test_nicknames_must_be_heard():
    partials = [_chunk(nicknames=[("Selu", "José Luis", "00:30:00"), ("Xelu", "Jose Luis Pérez Rodríguez", ""),
                                  ("Sandra", "Sandra", "")])]
    _, nick = collect_identities(partials, {}, ON_SCREEN, [], HEARD)
    assert nick == {"Jose Luis Pérez Rodríguez": ["Selu"]}  # «Xelu» no se oye en el texto
    # Ejecución real: el LLM atribuyó «Selu» a Sandra y a Iosu; no se parece a sus nombres
    wrong = [_chunk(nicknames=[("Selu", "Sandra", ""), ("Selu", "Iosu Urcelay Fernandez De Arroyabe", "")])]
    assert collect_identities(wrong, {}, ON_SCREEN, [], HEARD)[1] == {}


def test_participants_ignore_single_readings():
    groups = [{"canonical": "Sandra", "readings": 94}, {"canonical": "Selu", "readings": 1}]
    assert participants(groups) == ["Sandra"]


def test_who_block_and_aliases_in_prompts():
    who = who_block(["Sandra"], [("Hablante 1", ""), ("Sandra", "confirmado")], {"Jose Luis": ["Selu"]})
    assert "Hablante 1: sin identificar" in who and "«Selu» = Jose Luis" in who
    assert who_block([], [], {}) == ""
    person = {"name": "José Luis Pérez", "aliases": ["Selu"], "facts": []}
    assert person_line(person) == "- José Luis Pérez (también llamado Selu)"
    prompt = build_whisper_prompt(None, [{"id": 1, **person}], [])
    assert "José Luis Pérez (Selu)" in prompt


def _video(session, **speaker):
    v = Video(source_path="a.mp4", title="Reunión", status="done", recorded_at=datetime(2026, 1, 1))
    session.add(v)
    session.commit()
    sp = Speaker(video_id=v.id, label="S0", order_idx=1, **speaker)
    session.add(sp)
    session.commit()
    return v, sp


def test_context_identity_is_only_a_proposal(client, session):
    v, sp = _video(session)
    found = {"identidades": {"S0": {"nombre": "Sandra", "motivo": "Responde cuando la llaman", "t": "00:12:00"}},
             "apodos": {"Sandra": ["Sandri"]}}
    services.apply_context_identities(session, v.id, found, [])
    session.refresh(sp)
    assert (sp.suggested_name, sp.source, sp.confirmed) == ("Sandra", "contexto", False)
    out = client.get(f"/api/videos/{v.id}").json()["speakers"][0]
    assert out["reason"] == "Responde cuando la llaman (00:12:00)" and out["aliases"] == ["Sandri"]
    assert out["visual_hints"] == {}
    assert services.speaker_names(session, v.id)["S0"] == "Sandra"

    # Al confirmar la propuesta como persona nueva, los apodos pasan a ser sus otros nombres
    client.put(f"/api/speakers/{sp.id}", json={"new_person_name": "Sandra", "confirm": True})
    person = session.exec(__import__("sqlmodel").select(Person)).one()
    assert person.aliases == ["Sandri"]

    # Una nueva pasada sin identidad ya no toca a un hablante confirmado
    services.apply_context_identities(session, v.id, {}, [])
    session.refresh(sp)
    assert sp.confirmed and sp.person_id == person.id


def test_context_identity_never_overrides_other_sources(session):
    v, sp = _video(session, suggested_name="Iosu", source="pantalla", confidence=0.7)
    services.apply_context_identities(session, v.id, {"identidades": {"S0": {"nombre": "Edgar", "motivo": ""}}}, [])
    session.refresh(sp)
    assert (sp.suggested_name, sp.source) == ("Iosu", "pantalla")


def test_regenerating_keeps_context_identities(session):
    """Al regenerar, un hablante con propuesta por contexto ya no es «Hablante N» y no se reevalúa."""
    v, sp = _video(session)
    first = {"identidades": {"S0": {"nombre": "Sandra", "motivo": "Responde", "t": ""}}, "evaluados": ["S0"]}
    services.apply_context_identities(session, v.id, first, [])
    services.apply_context_identities(session, v.id, {"identidades": {}, "evaluados": []}, [])
    session.refresh(sp)
    assert (sp.suggested_name, sp.source, sp.visual_hints.get("_motivo")) == ("Sandra", "contexto", "Responde")
    # Si se reevalúa y ya no se sostiene, se retira
    services.apply_context_identities(session, v.id, {"identidades": {}, "evaluados": ["S0"]}, [])
    session.refresh(sp)
    assert (sp.suggested_name, sp.source) == ("", "") and "_motivo" not in sp.visual_hints


def test_summary_uses_names_found_by_context():
    analysis = {"resumen_breve": "Hablante 3 prepara el informe; Hablante 1 lo revisa.",
                "tareas": [{"responsable": "Hablante 3", "tarea": "Informe"}]}
    before = {"S0": "Hablante 3", "S1": "Hablante 1", "S2": "Iosu"}
    after = {"S0": "Juan Pérez", "S1": "Hablante 1", "S2": "Iosu"}
    out = services.rename_speakers(analysis, before, after)
    assert out["resumen_breve"] == "Juan Pérez prepara el informe; Hablante 1 lo revisa."
    assert out["tareas"][0]["responsable"] == "Juan Pérez"
