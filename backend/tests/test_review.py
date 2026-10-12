"""Revisión del vídeo: espera de los relacionados, cambios sin aplicar, «Aplicar y continuar» y fin de la revisión."""

from datetime import datetime

import pytest

from app import review
from app.models import (
    Followup,
    FollowupItem,
    FollowupVideo,
    Job,
    KnowledgeItem,
    Person,
    Profile,
    Speaker,
    Video,
    VideoCorrection,
)

D = datetime(2026, 9, 2, 17)  # noqa: DTZ001


@pytest.fixture(autouse=True)
def tmp_work(tmp_path, monkeypatch):
    """La carpeta de trabajo de las pruebas (nunca la del usuario: `drop_audio` borra el audio)."""
    monkeypatch.setattr(review, "WORK_DIR", tmp_path)
    return tmp_path


def _video(session, title, profile=None, state=review.PENDING, status="done", job="done", folder="x"):
    v = Video(source_path=f"{title}.mkv", title=title, status=status, recorded_at=D, duration=600, profile_id=profile,
              review=state, folder=folder if status == "done" else "", analysis={"titulo": title} if status == "done" else {})
    session.add(v)
    session.commit()
    session.add(Job(video_id=v.id, status=job))
    session.commit()
    return v


def test_blocker_only_related_earlier_and_unreviewed(session):
    p = Profile(name="Tutoría")
    session.add(p)
    session.commit()
    v1 = _video(session, "Uno", p.id)
    v2 = _video(session, "Dos", p.id, status="processing", job="running")
    other = _video(session, "Otro tema")
    assert review.blocker(session, v2).id == v1.id
    assert review.blocker(session, v1) is None  # no espera a los encolados después
    assert review.blocker(session, other) is None  # sin relación
    v1.review = review.PROPOSALS  # aún quedan propuestas: sigue bloqueando
    session.add(v1)
    session.commit()
    assert review.blocker(session, v2).id == v1.id
    v1.review = review.DONE
    session.add(v1)
    session.commit()
    assert review.blocker(session, v2) is None


def test_blocker_by_followup_and_failed_videos_do_not_block(session):
    v1 = _video(session, "Uno", status="pending", job="cancelled")  # cancelado antes de analizarse
    v2 = _video(session, "Dos")
    v3 = _video(session, "Tres", status="processing", job="running")
    f = Followup(name="Plan")
    session.add(f)
    session.commit()
    for v in (v1, v2, v3):
        session.add(FollowupVideo(followup_id=f.id, video_id=v.id))
    session.commit()
    assert review.blocker(session, v2) is None
    assert review.blocker(session, v3).id == v2.id


def test_release_waiting(session):
    p = Profile(name="Tutoría")
    session.add(p)
    session.commit()
    v1 = _video(session, "Uno", p.id)
    v2 = _video(session, "Dos", p.id, status="processing", job="waiting")
    job = session.get(Job, 2)
    job.options = {"waiting_for": v1.id}
    session.add(job)
    session.commit()
    assert review.out(session, v1)["waiting"] == [{"id": v2.id, "title": "Dos"}]
    assert review.release_waiting(session) == 0
    v1.review = review.DONE
    session.add(v1)
    session.commit()
    assert review.release_waiting(session) == 1
    session.refresh(job)
    assert job.status == "queued" and "waiting_for" not in job.options


def test_changes_and_apply_stages(session):
    v = _video(session, "Uno")
    v.voices_applied = {}
    session.add(v)
    session.commit()
    assert review.changes(session, v) == []
    assert review.apply_stages(session, v) == ["voiceprints", "follow", "learn", "publish"]
    session.add(VideoCorrection(video_id=v.id, text="Selu es José Luis"))
    ana = Person(name="Ana")
    session.add(ana)
    session.commit()
    session.add(Speaker(video_id=v.id, label="S1", person_id=ana.id, confirmed=True))
    session.commit()
    kinds = {c["kind"]: c["label"] for c in review.changes(session, v)}
    assert kinds == {"correcciones": "1 corrección", "hablantes": "1 hablante confirmado o cambiado"}
    assert review.apply_stages(session, v)[:2] == ["correct", "analyze"]
    # Los vídeos de antes de la revisión no tienen hablantes aplicados anotados: no cuentan como cambio
    v.voices_applied = None
    assert {c["kind"] for c in review.changes(session, v)} == {"correcciones"}


def test_done_when_nothing_left_to_decide(session):
    v = _video(session, "Uno", state=review.PROPOSALS)
    item = KnowledgeItem(kind="termino", data={"term": "Naturgy"}, video_id=v.id)
    f = Followup(name="Plan")
    session.add(item), session.add(f)
    session.commit()
    session.add(FollowupVideo(followup_id=f.id, video_id=v.id))
    dup = FollowupItem(followup_id=f.id, kind="tarea", text="Enviar la póliza", status="abierta",
                       events=[{"video_id": v.id, "evento": "creada", "source": "ia"}],
                       review={"tipo": "duplicado", "de": 1, "motivo": "Parece la misma"})
    session.add(dup)
    session.commit()
    assert review.pending(session, v) == {"propuestas": 1, "seguimiento": 1, "voces": 0}
    assert not review.check_done(session, v)
    item.status = "aceptado"
    dup.review = {}
    session.add(item), session.add(dup)
    session.commit()
    assert review.check_done(session, v) and v.review == review.DONE


def test_library_card_says_what_is_left(client, session):
    a = _video(session, "Uno", state=review.PROPOSALS)
    _video(session, "Dos", state=review.PENDING)
    session.add(KnowledgeItem(kind="termino", data={"term": "Naturgy"}, video_id=a.id))
    session.commit()
    p = Person(name="Iosu")
    session.add(p)
    session.commit()
    session.add_all([Speaker(video_id=a.id, label="S1", order_idx=1, person_id=p.id),
                     Speaker(video_id=a.id, label="MANUAL_1", order_idx=2, person_id=p.id)])
    session.commit()
    cards = {c["title"]: c for c in client.get("/api/videos").json()}
    assert cards["Uno"]["people"] == ["Iosu"]
    assert cards["Uno"]["to_decide"] == {"propuestas": 1, "seguimiento": 0, "voces": 0}
    assert cards["Dos"]["to_decide"] is None


def test_api_apply_and_changes_reopen_the_review(client, session, monkeypatch):
    v = _video(session, "Uno", state=review.DONE)
    v.voices_applied = {}
    session.add(v)
    session.commit()
    vid = v.id
    assert client.get(f"/api/videos/{vid}").json()["review"]["state"] == review.DONE
    # Una corrección en un vídeo ya revisado lo deja pendiente de aplicar
    client.post(f"/api/videos/{vid}/corrections", json={"text": "Selu es José Luis"})
    data = client.get(f"/api/videos/{vid}").json()["review"]
    assert data["state"] == review.PENDING and [c["kind"] for c in data["changes"]] == ["correcciones"]
    info = client.get(f"/api/videos/{vid}/apply").json()
    assert info["stages"][:2] == ["correct", "analyze"] and info["seconds"] > 0
    monkeypatch.setattr("app.main._requeue", lambda s, v, redo, msg, check_work=True, extra=None:
                        Job(id=99, video_id=v.id, options={**(extra or {}), "redo": redo}))
    r = client.post(f"/api/videos/{vid}/apply").json()
    assert r["job_id"] == 99
    session.expire_all()
    assert session.get(Video, vid).review == review.APPLYING


def test_short_jobs_go_first():
    """Aplicar una revisión o rehacer un seguimiento no espera a que termine el análisis de otro vídeo."""
    from app.worker import is_short

    assert is_short(Job(video_id=1, options={"apply": True, "redo": []}))
    assert is_short(Job(video_id=1, options={"only": ["follow"]}))
    assert not is_short(Job(video_id=1, options={"file_mode": "copy"}))
    assert not is_short({"redo": ["analyze"]})
