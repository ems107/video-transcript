def test_profile_versions_and_restore(client):
    p = client.post("/api/profiles", json={"name": "Trabajo", "context": "v1"}).json()
    client.put(f"/api/profiles/{p['id']}", json={"name": "Trabajo", "context": "v2"})
    client.put(f"/api/profiles/{p['id']}", json={"name": "Trabajo", "context": "v2"})  # sin cambios: sin versión
    versions = client.get(f"/api/profiles/{p['id']}/versions").json()
    assert [v["reason"] for v in versions] == ["Cambios manuales", "Creado"]
    assert versions[0]["diff"]["manual"] == ["context"]

    r = client.post(f"/api/profiles/{p['id']}/versions/{versions[-1]['id']}/restore")
    assert r.json()["context"] == "v1"
    versions = client.get(f"/api/profiles/{p['id']}/versions").json()
    assert versions[0]["reason"].startswith("Restaurada") and len(versions) == 3


def test_person_versions(client):
    p = client.post("/api/people", json={"name": "María"}).json()
    client.put(f"/api/people/{p['id']}", json={"name": "María López", "role": "PM"})
    versions = client.get(f"/api/people/{p['id']}/versions").json()
    assert len(versions) == 2
    r = client.post(f"/api/people/{p['id']}/versions/{versions[-1]['id']}/restore").json()
    assert r["name"] == "María" and r["role"] == ""


def _video_with_proposals(session):
    from datetime import datetime

    from app import knowledge_store as KS
    from app.models import Person, Profile, Speaker, Video
    from app.pipeline.learn import collect_proposals
    from tests.test_learn import NAMES, PEOPLE, PROFILE, UTTS, VISION, llm_result

    prof = Profile(name="Trabajo")
    maria = Person(name="María López")
    session.add(prof), session.add(maria)
    session.commit()
    v = Video(source_path="a.mp4", title="Reunión", profile_id=prof.id, status="done", recorded_at=datetime(2026, 1, 1))
    session.add(v)
    session.commit()
    sp = Speaker(video_id=v.id, label="SPEAKER_00", order_idx=1, suggested_person_id=maria.id, source="voz",
                 confidence=0.6)
    session.add(sp)
    session.commit()
    props = collect_proposals([llm_result()], [(10.0, 20.0)], UTTS, VISION, NAMES, PEOPLE, PROFILE, {}, True)
    KS.merge_proposals(session, v.id, props, auto=0.75)
    return prof, maria, v, sp


def test_proposals_flow(client, session):
    prof, maria, v, sp = _video_with_proposals(session)
    r = client.get("/api/proposals").json()
    kinds = sorted(i["kind"] for i in r["items"])
    assert kinds == ["contexto", "nueva_persona", "seccion", "seccion", "termino"]
    assert [w["owner"]["type"] for w in r["waiting"]] == ["speaker"]  # voz poco segura: espera confirmación
    assert client.get("/api/status").json()["pending_proposals"] == 5

    term = next(i for i in r["items"] if i["kind"] == "termino")
    new = next(i for i in r["items"] if i["kind"] == "nueva_persona")
    sec = [i["id"] for i in r["items"] if i["kind"] == "seccion"]
    res = client.post("/api/proposals/decide", json={
        "accept": [term["id"], new["id"]], "reject": sec, "edits": {str(term["id"]): {"definition": "Gestor de tareas"}},
    }).json()
    assert res == {"aceptadas": 2, "rechazadas": 2, "en_espera": 0}
    know = client.get(f"/api/profiles/{prof.id}/knowledge").json()
    assert [(k["text"], k["data"]["definition"]) for k in know] == [("Jira", "Gestor de tareas")]
    people = {p["name"]: p for p in client.get("/api/people").json()}
    lucia = people["Lucía"]
    assert [k["text"] for k in client.get(f"/api/people/{lucia['id']}/knowledge").json()] == ["Es del equipo de QA"]
    assert client.get(f"/api/profiles/{prof.id}")  .json()["person_ids"] == [lucia["id"]]

    # Confirmar al hablante libera su propuesta para María
    client.put(f"/api/speakers/{sp.id}", json={"person_id": maria.id})
    r = client.get(f"/api/proposals?person_id={maria.id}").json()
    assert [i["text"] for i in r["items"]] == ["Lleva el proyecto Atlas"] and not r["waiting"]
    client.post("/api/proposals/decide", json={"accept": [r["items"][0]["id"]]})
    assert len(client.get(f"/api/people/{maria.id}/knowledge").json()) == 1

    # Reasignar el hablante a otra persona mueve lo aprendido
    pedro = client.post("/api/people", json={"name": "Pedro"}).json()
    client.put(f"/api/speakers/{sp.id}", json={"person_id": pedro["id"]})
    assert client.get(f"/api/people/{maria.id}/knowledge").json() == []
    assert len(client.get(f"/api/people/{pedro['id']}/knowledge").json()) == 1
    assert client.get(f"/api/people/{maria.id}/versions").json()[0]["reason"] == "Reasignado un hablante"

    # Olvidar el vídeo retira lo que solo venía de él
    stats = client.post(f"/api/knowledge/forget-video/{v.id}").json()
    assert stats["retirados"] >= 3
    assert client.get(f"/api/profiles/{prof.id}/knowledge").json() == []


def test_profile_from_video_requires_work_data(client, session, tmp_path, monkeypatch):
    from app import main
    from app.models import Job, Video

    v = Video(source_path="a.mp4", title="Reunión", status="done")
    session.add(v)
    session.commit()
    job = Job(video_id=v.id, status="done")
    session.add(job)
    session.commit()
    monkeypatch.setattr(main, "WORK_DIR", tmp_path)
    r = client.post("/api/profiles/from-video", json={"video_id": v.id, "name": "Nuevo"})
    assert r.status_code == 400 and client.get("/api/profiles").json() == []  # se deshace

    (tmp_path / f"job_{job.id}").mkdir()
    (tmp_path / f"job_{job.id}" / "corrected.json").write_text("[]", encoding="utf-8")
    r = client.post("/api/profiles/from-video", json={"video_id": v.id, "name": "Nuevo"})
    assert r.status_code == 200
    session.refresh(job), session.refresh(v)
    assert job.status == "queued" and job.options["redo"] == ["learn"] and v.profile_id == r.json()["id"]
    assert client.get(f"/api/profiles/{v.profile_id}/versions").json()[0]["reason"].startswith("Creado desde")
