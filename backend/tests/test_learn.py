from datetime import datetime

from sqlmodel import select

from app import knowledge_store as KS
from app.models import KnowledgeItem, Person, Profile, Speaker, Video
from app.pipeline.learn import collect_proposals

UTTS = [
    {"start": 10.0, "end": 15.0, "speaker": "SPEAKER_00", "text": "Yo llevo el proyecto Atlas desde enero."},
    {"start": 16.0, "end": 20.0, "speaker": "SPEAKER_01", "text": "Y Lucía, la de QA, revisa los pedidos en Jira."},
]
VISION = [{"t": 30.0, "texto_relevante": "Jira - Sprint 12", "terminos": ["Jira"], "descripcion": ""}]
NAMES = {"SPEAKER_00": "María López", "SPEAKER_01": "Hablante 2"}
PEOPLE = [{"id": 1, "name": "María López", "aliases": [], "facts": []}]
PROFILE = {"id": 1, "name": "Trabajo", "glossary": [], "summary_sections": [], "learned": []}


def llm_result():
    return {
        "terminos": [{"termino": "Jira", "definicion": "", "t": "00:00:16"},
                     {"termino": "Zeus", "definicion": "inventado", "t": "00:00:12"}],
        "contexto": [{"categoria": "proyecto", "texto": "Atlas es un proyecto activo desde enero", "t": "00:00:11",
                      "reemplaza": 0},
                     {"categoria": "otro", "texto": "Fuera de rango", "t": "02:00:00", "reemplaza": 0}],
        "personas": [{"nombre": "María López", "categoria": "proyecto", "dato": "Lleva el proyecto Atlas",
                      "t": "00:00:10", "reemplaza": 0},
                     {"nombre": "Lucía", "categoria": "equipo", "dato": "Es del equipo de QA", "t": "00:00:17",
                      "reemplaza": 0},
                     {"nombre": "el cliente", "categoria": "otro", "dato": "Nada", "t": "00:00:17", "reemplaza": 0}],
        "secciones": ["Estado del proyecto", "Riesgos"],
    }


def test_collect_proposals_verifies_everything():
    props = collect_proposals([llm_result()], [(10.0, 20.0)], UTTS, VISION, NAMES, PEOPLE, PROFILE,
                              {"SPEAKER_00": {"María L.": 3}}, want_sections=True)
    kinds = [(p["kind"], p["owner"], p["data"].get("term") or p["data"].get("text") or p["data"].get("name")
              or p["data"].get("title")) for p in props]
    assert ("termino", ("profile", None), "Jira") in kinds
    assert not [k for k in kinds if k[2] in ("Zeus", "Fuera de rango", "Nada")]  # inventado, sin evidencia o sin dueño
    assert ("dato", ("speaker", "SPEAKER_00"), "Lleva el proyecto Atlas") in kinds
    assert ("dato", ("new", "Lucía"), "Es del equipo de QA") in kinds
    assert ("alias", ("speaker", "SPEAKER_00"), "María L.") in kinds
    assert [k[2] for k in kinds if k[0] == "seccion"] == ["Estado del proyecto", "Riesgos"]
    term = next(p for p in props if p["kind"] == "termino")
    assert term["t"] == 16.0 and term["lines"]  # evidencia real

    no_profile = collect_proposals([llm_result()], [(10.0, 20.0)], UTTS, VISION, NAMES, PEOPLE, None, {}, False)
    assert {p["kind"] for p in no_profile} == {"dato"}  # sin perfil solo se aprende de personas


def _setup(session):
    prof = Profile(name="Trabajo")
    maria = Person(name="María López")
    session.add(prof), session.add(maria)
    session.commit()
    v1 = Video(source_path="a.mp4", profile_id=prof.id, recorded_at=datetime(2026, 1, 1))
    v2 = Video(source_path="b.mp4", profile_id=prof.id, recorded_at=datetime(2026, 2, 1))
    session.add(v1), session.add(v2)
    session.commit()
    for v, conf in ((v1, 0.6), (v2, 0.9)):
        session.add(Speaker(video_id=v.id, label="SPEAKER_00", suggested_person_id=maria.id, source="voz",
                            confidence=conf))
    session.commit()
    return prof, maria, v1, v2


def test_merge_proposals_dedupes_and_respects_rejections(session):
    _, _, v1, v2 = _setup(session)
    props = collect_proposals([llm_result()], [(10.0, 20.0)], UTTS, VISION, NAMES, PEOPLE, PROFILE, {}, True)
    stats = KS.merge_proposals(session, v1.id, props, auto=0.75)
    assert stats["nuevas"] == len(props)
    again = KS.merge_proposals(session, v1.id, props, auto=0.75)  # mismo vídeo otra vez
    assert again["nuevas"] == 0
    items = list(session.exec(select(KnowledgeItem)))
    assert all(i.seen_count == 1 for i in items)

    jira = next(i for i in items if i.kind == "termino")
    jira.status = "rechazado"
    session.add(jira)
    session.commit()
    stats = KS.merge_proposals(session, v2.id, props, auto=0.75)
    assert stats["descartadas"] >= 1 and stats["nuevas"] >= 1
    ctx_item = next(i for i in list(session.exec(select(KnowledgeItem))) if i.kind == "contexto")
    assert ctx_item.seen_count == 2 and len(ctx_item.evidence) == 2
    new_person = next(i for i in list(session.exec(select(KnowledgeItem))) if i.kind == "nueva_persona")
    assert new_person.data["name"] == "Lucía" and len(new_person.data["datos"]) == 1
