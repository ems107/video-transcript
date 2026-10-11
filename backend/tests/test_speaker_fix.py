"""Arreglos manuales de hablantes por la API: al momento en la transcripción y sin perderse al regenerar."""

import json
from datetime import datetime

from sqlmodel import select

from app import main, regenerate, speaker_fix
from app.models import Job, Person, Segment, Speaker, Video


def _setup(session, tmp_path, monkeypatch):
    monkeypatch.setattr(speaker_fix, "WORK_DIR", tmp_path)
    monkeypatch.setattr(main.services, "export_video", lambda *a: None)
    edgar, iosu = Person(name="Edgar"), Person(name="Iosu")
    v = Video(source_path="a.mkv", title="T", status="done", recorded_at=datetime(2026, 1, 1),
              analysis={"titulo": "T"})
    session.add(edgar), session.add(iosu), session.add(v)
    session.commit()
    session.add(Job(id=1, video_id=v.id, status="done"))
    session.add(Speaker(video_id=v.id, label="S_E", order_idx=1, person_id=edgar.id, confirmed=True))
    session.add(Speaker(video_id=v.id, label="S_I", order_idx=2, person_id=iosu.id, confirmed=True))
    # Línea de pyannote toda de Edgar, pero «Hola Edgar» lo dice Iosu
    session.add(Segment(video_id=v.id, idx=0, start=19.8, end=28.3, speaker="S_E",
                        text="Hola, ¿qué tal? Hola Edgar. Hola, buenas."))
    session.add(Segment(video_id=v.id, idx=1, start=30.0, end=33.0, speaker="S_E", text="Otra frase de Edgar."))
    session.commit()
    words = [("Hola,", 19.8, 19.9), ("¿qué", 19.9, 20.0), ("tal?", 20.0, 20.4), ("Hola", 22.9, 23.1),
             ("Edgar.", 23.2, 23.5), ("Hola,", 24.5, 24.7), ("buenas.", 24.8, 25.2),
             ("Otra", 30.0, 30.4), ("frase", 30.5, 31.0), ("de", 31.1, 31.3), ("Edgar.", 31.4, 32.0)]
    (tmp_path / "job_1").mkdir()
    (tmp_path / "job_1" / "words.json").write_text(json.dumps(
        [{"word": w, "start": a, "end": b, "speaker": "S_E"} for w, a, b in words]), encoding="utf-8")
    return v, edgar, iosu


def _lines(session, vid):
    return [(s.speaker, s.text) for s in session.exec(select(Segment).where(Segment.video_id == vid)
                                                      .order_by(Segment.idx))]


def test_fix_part_of_a_line_and_undo(client, session, tmp_path, monkeypatch):
    v, _, iosu = _setup(session, tmp_path, monkeypatch)
    vid = v.id
    words = client.get(f"/api/videos/{vid}/words", params={"start": 19.8, "end": 28.3}).json()
    assert [w["word"] for w in words][3:5] == ["Hola", "Edgar."]
    r = client.post(f"/api/videos/{vid}/speaker-overrides",
                    json={"ranges": [[words[3]["start"], words[4]["end"]]], "person_id": iosu.id})
    assert r.json()["ok"]
    session.expire_all()
    assert _lines(session, vid) == [("S_E", "Hola, ¿qué tal?"), ("S_I", "Hola Edgar."), ("S_E", "Hola, buenas."),
                                    ("S_E", "Otra frase de Edgar.")]
    detail = client.get(f"/api/videos/{vid}").json()
    assert detail["overrides_pending"]  # el resumen aún no lo tiene en cuenta

    [o] = client.get(f"/api/videos/{vid}/speaker-overrides").json()
    assert o["person_name"] == "Iosu"
    client.delete(f"/api/speaker-overrides/{o['id']}")
    session.expire_all()
    assert {sp for sp, _ in _lines(session, vid)} == {"S_E"}
    assert not client.get(f"/api/videos/{vid}").json()["overrides_pending"]


def test_new_person_gets_a_manual_speaker(client, session, tmp_path, monkeypatch):
    v, _, _ = _setup(session, tmp_path, monkeypatch)
    vid = v.id
    client.post(f"/api/videos/{vid}/speaker-overrides", json={"ranges": [[30.0, 32.0]], "new_person_name": "Sandra"})
    session.expire_all()
    sandra = session.exec(select(Person).where(Person.name == "Sandra")).one()
    sp = session.exec(select(Speaker).where(Speaker.label == f"MANUAL_{sandra.id}")).one()
    assert sp.confirmed and sp.person_id == sandra.id
    assert _lines(session, vid)[-1] == (f"MANUAL_{sandra.id}", "Otra frase de Edgar.")
    # Al volver a separar las voces, el hablante manual no se desconfirma: se aplica por tiempo
    regenerate.unconfirm_speakers(session, vid)
    session.refresh(sp)
    assert sp.confirmed


def test_pending_tracks_the_overrides_used():
    assert not speaker_fix.pending({"titulo": "T"}, [])
    assert speaker_fix.pending({"hablantes_aplicados": [1]}, [{"id": 1}, {"id": 2}])
    assert not speaker_fix.pending({"hablantes_aplicados": [2, 1]}, [{"id": 1}, {"id": 2}])
