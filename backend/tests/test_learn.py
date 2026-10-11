from datetime import datetime

from sqlmodel import select

from app import knowledge_store as KS
from app.knowledge import screen_summary
from app.models import KnowledgeItem, Person, Profile, Speaker, Video
from app.pipeline.learn import apply_judgment, collect_proposals

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
                     {"termino": "Zeus", "definicion": "inventado", "t": "00:00:12"},
                     {"termino": "pedidos", "definicion": "palabra común", "t": "00:00:16"}],
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
                              [{"canonical": "María López", "person_id": 1, "screen": "María L.", "readings": 3}],
                              want_sections=True)
    kinds = [(p["kind"], p["owner"], p["data"].get("term") or p["data"].get("text") or p["data"].get("name")
              or p["data"].get("title")) for p in props]
    assert ("termino", ("profile", None), "Jira") in kinds
    # inventado, palabra común, sin evidencia o sin dueño
    assert not [k for k in kinds if k[2] in ("Zeus", "pedidos", "Fuera de rango", "Nada")]
    assert ("dato", ("speaker", "SPEAKER_00"), "Lleva el proyecto Atlas") in kinds
    assert ("dato", ("new", "Lucía"), "Es del equipo de QA") in kinds
    assert ("alias", ("person", 1), "María L.") in kinds
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
    # Una nueva pasada sobre el mismo vídeo sustituye sus propuestas pendientes (no se acumulan)
    KS.merge_proposals(session, v1.id, props, auto=0.75)
    items = list(session.exec(select(KnowledgeItem)))
    assert len(items) == len(props) and all(i.seen_count == 1 for i in items)

    jira = next(i for i in items if i.kind == "termino")
    jira.status = "rechazado"
    ctx = next(i for i in items if i.kind == "contexto")
    ctx.status = "aceptado"
    session.add(jira), session.add(ctx)
    session.commit()
    KS.merge_proposals(session, v1.id, props, auto=0.75)  # lo decidido se conserva y no se vuelve a proponer
    kinds = [(i.kind, i.status) for i in session.exec(select(KnowledgeItem))]
    assert kinds.count(("contexto", "aceptado")) == 1 and ("contexto", "propuesto") not in kinds
    assert kinds.count(("termino", "rechazado")) == 1 and ("termino", "propuesto") not in kinds
    stats = KS.merge_proposals(session, v2.id, props, auto=0.75)
    assert stats["descartadas"] >= 1 and stats["nuevas"] >= 1
    ctx_item = next(i for i in list(session.exec(select(KnowledgeItem))) if i.kind == "contexto")
    assert ctx_item.seen_count == 2 and len(ctx_item.evidence) == 2
    new_person = next(i for i in list(session.exec(select(KnowledgeItem))) if i.kind == "nueva_persona")
    assert new_person.data["name"] == "Lucía" and len(new_person.data["datos"]) == 1


def test_learn_failure_does_not_break_the_job(engine, monkeypatch, tmp_path):
    import threading

    from app import worker as W
    from app.config import Settings
    from app.pipeline.base import JobContext

    def boom(*_a, **_k):
        raise RuntimeError("LLM caído")

    monkeypatch.setattr(W, "engine", engine)
    monkeypatch.setattr(W.learn, "run", boom)
    msgs = []
    ctx = JobContext(job_id=1, video_id=1, source_path=tmp_path / "v.mp4", work_dir=tmp_path, settings=Settings(),
                     options={}, profile=None, people=[], report=lambda f, m: msgs.append(m),
                     cancel_event=threading.Event())
    W.Worker()._learn(ctx, llm=None)  # no lanza
    assert ctx.load("learn_error.json") == {"error": "LLM caído"}
    assert "No se pudo aprender" in msgs[-1]


def test_pending_texts_excludes_own_video(session):
    _, maria, v1, v2 = _setup(session)
    session.add(KnowledgeItem(person_id=maria.id, kind="dato", data={"text": "Del vídeo 1"}, video_id=v1.id))
    session.add(KnowledgeItem(person_id=maria.id, kind="dato", data={"text": "Del vídeo 2"}, video_id=v2.id))
    session.commit()
    assert KS.pending_texts(session, v1.id, None, {maria.id}) == ["Del vídeo 2"]


def test_sections_only_once(session):
    prof, _, v1, v2 = _setup(session)
    session.add(KnowledgeItem(profile_id=prof.id, kind="seccion", data={"title": "Estado"}, video_id=v1.id))
    session.commit()
    assert KS.has_pending_sections(session, prof.id, v2.id)
    assert not KS.has_pending_sections(session, prof.id, v1.id)  # una nueva pasada del mismo vídeo sí las repite


def test_requeued_video_returns_to_done(engine, monkeypatch):
    from app import worker as W
    from app.models import Job

    monkeypatch.setattr(W, "engine", engine)
    from sqlmodel import Session

    with Session(engine) as s:
        v = Video(source_path="a.mp4", status="processing", folder="C:/x")
        s.add(v)
        s.commit()
        job = Job(video_id=v.id, status="running")
        s.add(job)
        s.commit()
        jid, vid = job.id, v.id
    W.Worker()._finish(jid, "done", "Completado")
    with Session(engine) as s:
        assert s.get(Video, vid).status == "done"


def test_screen_terms_are_judged_and_forms_are_grouped():
    utts = [{"start": 10.0, "end": 15.0, "speaker": "SPEAKER_00", "text": "Entra en la plataforma y crea el lead."}]
    # Bárymont es el contenido de la pantalla; Trello solo está en la barra de tareas (lista de visibles)
    vision = [{"t": 10.0 + i, "texto_relevante": "Grupo Bárymont · Gestibarymont · Bárymont · Lead",
               "terminos": ["Bárymont", "Gestibarymont", "Grupo Bárymont", "Trello", "Jira"],
               "descripcion": "Navegador con la plataforma", "tipo_escena": "navegador"} for i in range(4)]
    result = {"terminos": [{"termino": t, "definicion": d, "t": "00:00:11"} for t, d in
                           (("Bárymont", "CRM de la empresa"), ("Gestibarymont", ""), ("Grupo Bárymont", ""),
                            ("Trello", "gestor de tareas"), ("Jira", ""), ("lead", ""))],
              "contexto": [], "personas": [], "secciones": []}
    props = collect_proposals([result], [(0.0, 60.0)], utts, vision, NAMES, PEOPLE, PROFILE, [], False)
    terms = {p["data"]["term"]: p for p in props if p["kind"] == "termino"}
    # Las formas de un mismo nombre van juntas; todo lo visto solo en pantalla queda para que la IA lo valore
    assert sorted(terms["Bárymont"]["data"]["forms"]) == ["Gestibarymont", "Grupo Bárymont"]
    assert terms["Bárymont"]["data"]["definition"] == "CRM de la empresa"
    assert terms["Bárymont"]["screen_only"] and terms["Trello"]["screen_only"]
    answer = {"terminos": [{"termino": "Bárymont", "relacion": "relacionado", "motivo": "Es la plataforma que se usa"},
                           {"termino": "Trello", "relacion": "sin_relacion", "motivo": "Solo en la barra de tareas"}]}
    kept, judged = apply_judgment(props, answer)
    kept_terms = {p["data"]["term"]: p["data"].get("pantalla") for p in kept if p["kind"] == "termino"}
    assert kept_terms == {"Bárymont": {"relacion": "relacionado", "motivo": "Es la plataforma que se usa"},
                          "Jira": {"relacion": "dudoso", "motivo": "La IA no lo valoró."}}
    assert {j["termino"]: j["relacion"] for j in judged} == {"Bárymont": "relacionado", "Trello": "sin_relacion",
                                                              "Jira": "dudoso"}
    assert not any("screen_only" in p for p in kept)


def test_screen_summary_says_where_a_term_is_seen():
    vision = [{"t": 30.0, "texto_relevante": "", "terminos": ["Trello"], "descripcion": "Escritorio con pestañas",
               "tipo_escena": "escritorio"},
              {"t": 600.0, "texto_relevante": "Tablero de Trello del proyecto", "terminos": [],
               "descripcion": "Se comparte el tablero", "tipo_escena": "navegador"}]
    text = screen_summary("Trello", vision)
    assert "en 2 fotogramas, de 0:30 a 10:00; en el contenido principal de 1" in text.replace("00:00:30", "0:30").replace("00:10:00", "10:00")
    assert "Se comparte el tablero" in text


def test_participants_seen_on_screen_are_not_terms():
    utts = [{"start": 10.0, "end": 15.0, "speaker": "SPEAKER_00", "text": "Vamos con el plan."}]
    vision = [{"t": 10.0, "texto_relevante": "Iosu Urcelay · Plan Light", "terminos": ["Iosu Urcelay", "Plan Light"],
               "descripcion": ""}]
    names = [{"canonical": "Iosu Urcelay", "variants": {"Iosu Urcelay": 3, "Ioni Urcelay": 1}, "readings": 4}]
    result = {"terminos": [{"termino": t, "definicion": ""} for t in ("Iosu Urcelay", "Ioni Urcelay", "Plan Light")],
              "contexto": [], "personas": [], "secciones": []}
    props = collect_proposals([result], [(0.0, 60.0)], utts, vision, NAMES, PEOPLE, PROFILE, names, False)
    assert [p["data"]["term"] for p in props if p["kind"] == "termino"] == ["Plan Light"]
