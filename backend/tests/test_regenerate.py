"""Regenerar con niveles: fases, disponibilidad y conservación de los hablantes confirmados."""

from datetime import datetime

from app import main, regenerate, services
from app.models import Job, Person, Speaker, Video


def test_levels_include_the_previous_ones():
    assert regenerate.stages("analysis") == ["correct", "analyze", "learn", "publish"]
    for shallow, deep in zip(regenerate.LEVELS, regenerate.LEVELS[1:]):
        assert set(regenerate.stages(shallow)) < set(regenerate.stages(deep))
    assert regenerate.stages("full")[0] == "ingest"


def test_availability(tmp_path):
    work = tmp_path / "job_1"
    work.mkdir()
    video = tmp_path / "v.mkv"
    video.write_bytes(b"v")
    r = regenerate.availability(work, None)
    assert r["analysis"] and r["full"] == "No se encuentra el archivo de vídeo"
    assert regenerate.availability(None, video) == {**{k: r["analysis"] for k in ("analysis", "speakers", "screen")},
                                                    "full": ""}
    for name in ("corrected.json", "diarization.json", "utterances.json"):
        (work / name).write_text("[]", encoding="utf-8")
    assert regenerate.availability(work, video) == dict.fromkeys(regenerate.LEVELS, "")
    assert regenerate.availability(work, None)["screen"] == "No se encuentra el archivo de vídeo"


def _ident(order, person_id=None, name=""):
    return {"order": order, "person_id": person_id, "suggested_name": name, "source": "pantalla" if name else "",
            "confidence": 0.7 if name else 0.0, "is_owner": False, "speaking_time": 10.0,
            "visual_hints": {"Iosu": 3}, "embedding": [0.1, 0.2]}


def test_identify_again_keeps_confirmed_speakers(session):
    person = Person(name="Iosu")
    v = Video(source_path="a.mkv", title="T", status="done", recorded_at=datetime(2026, 1, 1))
    session.add(person), session.add(v)
    session.commit()
    services.persist_speakers(session, v.id, {"S0": _ident(1), "S1": _ident(2), "S9": _ident(3)})
    s0 = session.exec(Speaker.__table__.select().where(Speaker.label == "S0")).first()
    sp = session.get(Speaker, s0.id)
    sp.person_id, sp.confirmed = person.id, True
    session.add(sp)
    session.commit()

    # Nueva identificación: S0 propondría otra cosa, S1 recibe propuesta y S9 ya no existe
    services.persist_speakers(session, v.id, {"S0": _ident(1, name="Otro"), "S1": _ident(2, name="Edgar")})
    rows = {sp.label: sp for sp in session.exec(Speaker.__table__.select()).all()}
    assert set(rows) == {"S0", "S1"}
    s0 = session.get(Speaker, rows["S0"].id)
    assert s0.id == sp.id and s0.confirmed and s0.person_id == person.id and s0.suggested_name == ""
    assert session.get(Speaker, rows["S1"].id).suggested_name == "Edgar"


def test_regenerate_endpoint_levels(client, session, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WORK_DIR", tmp_path)
    work = tmp_path / "job_1"
    work.mkdir()
    (work / "corrected.json").write_text("[]", encoding="utf-8")
    person = Person(name="Iosu")
    v = Video(source_path=str(tmp_path / "no-existe.mkv"), title="T", status="done", duration=600)
    session.add(person), session.add(v)
    session.commit()
    session.add(Job(id=1, video_id=v.id, status="done"))
    session.add(Speaker(video_id=v.id, label="S0", order_idx=1, person_id=person.id, confirmed=True))
    session.commit()

    info = client.get(f"/api/videos/{v.id}/regenerate").json()
    by = {x["level"]: x for x in info["levels"]}
    assert by["analysis"]["available"] and not by["speakers"]["available"] and not by["full"]["available"]
    assert by["analysis"]["seconds"] > 0 and info["confirmed_speakers"] == 1
    assert client.post(f"/api/videos/{v.id}/regenerate", json={"level": "full"}).status_code == 400

    # Sin cuerpo: el nivel básico, como el botón anterior
    assert client.post(f"/api/videos/{v.id}/regenerate").json()["ok"]
    session.expire_all()
    assert session.get(Job, 1).options["redo"] == regenerate.stages("analysis")

    # Completo (con el vídeo presente): los hablantes se desconfirman antes de volver a separar las voces
    video = tmp_path / "v.mkv"
    video.write_bytes(b"v")
    job = session.get(Job, 1)
    job.status = "done"
    vid = session.get(Video, v.id)
    vid.source_path = str(video)
    session.add(job), session.add(vid)
    session.commit()
    assert client.post(f"/api/videos/{v.id}/regenerate", json={"level": "full"}).json()["ok"]
    session.expire_all()
    sp = session.exec(Speaker.__table__.select()).first()
    assert not sp.confirmed and sp.person_id is None
    assert session.get(Person, person.id) is not None
