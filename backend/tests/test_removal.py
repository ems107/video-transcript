"""Quitar un vídeo: qué se borra, qué se conserva y la copia de recuperación."""

import json
from datetime import datetime

from sqlmodel import select

from app import removal
from app.models import Job, KnowledgeItem, Person, Speaker, Video, VoiceEmbedding


def _published(tmp_path, copied=True):
    """Carpeta publicada con los ficheros de la app, el vídeo y un fichero del usuario."""
    original = tmp_path / "Videos" / "grabacion.mkv"
    original.parent.mkdir()
    folder = tmp_path / "Analizados" / "2026-09-02 - Tutoría"
    (folder / "fotogramas").mkdir(parents=True)
    (folder / "fotogramas" / "kf_000001.jpg").write_bytes(b"jpg")
    for name in removal.APP_FILES:
        (folder / name).write_text("x", encoding="utf-8")
    video = folder / original.name
    video.write_bytes(b"video")
    if copied:
        original.write_bytes(b"video")
    work = tmp_path / "work" / "job_1"
    work.mkdir(parents=True)
    (work / "vision.json").write_text("[]", encoding="utf-8")
    return folder, video, original, work


def _apply(folder, video, original, work, **opts):
    return removal.execute(removal.plan(folder, video, original, [work], removal.Options(**opts)))


def test_keep_everything_by_default(tmp_path):
    folder, video, original, work = _published(tmp_path)
    assert removal.plan(folder, video, original, [work], removal.Options()) == []


def test_delete_files_keeps_original_and_user_files(tmp_path):
    folder, video, original, work = _published(tmp_path)
    (folder / "mis notas.txt").write_text("del usuario", encoding="utf-8")
    assert _apply(folder, video, original, work, delete_files=True) == []
    # La copia del vídeo se va con la carpeta; el original y lo que no es de la app se quedan
    assert original.exists() and not video.exists() and not work.exists()
    assert [p.name for p in folder.iterdir()] == ["mis notas.txt"]


def test_delete_files_moves_video_back(tmp_path):
    folder, video, original, work = _published(tmp_path, copied=False)
    _apply(folder, video, original, work, delete_files=True)
    assert original.read_bytes() == b"video" and not folder.exists()


def test_delete_video_and_original(tmp_path):
    folder, video, original, work = _published(tmp_path)
    _apply(folder, video, original, work, delete_video=True)
    assert not video.exists() and original.exists() and (folder / "resumen.md").exists()
    _apply(folder, None, original, work, delete_original=True)
    assert not original.exists()


def test_remove_endpoint(client, session, tmp_path, monkeypatch):
    folder, video, original, work = _published(tmp_path)
    monkeypatch.setattr(removal, "WORK_DIR", work.parent)
    person = Person(name="Iosu")
    v = Video(source_path=str(original), video_path=str(video), folder=str(folder), title="Tutoría",
              status="done", recorded_at=datetime(2026, 9, 2))
    session.add(person), session.add(v)
    session.commit()
    session.add(Job(id=1, video_id=v.id, status="done"))
    session.add(Speaker(video_id=v.id, label="S0", order_idx=1, person_id=person.id, confirmed=True,
                        embedding=[0.1, 0.2]))
    session.add(VoiceEmbedding(person_id=person.id, video_id=v.id, vector=[0.1, 0.2]))
    session.add(KnowledgeItem(kind="dato", category="cargo", data={"text": "Tutor"}, key="tutor", status="propuesto",
                              person_id=person.id, video_id=v.id, evidence=[{"video_id": v.id, "t": 1.0, "lines": []}]))
    session.commit()

    vid = v.id
    info = client.get(f"/api/videos/{vid}/removal").json()
    assert info["source_path"] == str(original) and info["voices"] == 1 and info["pending_proposals"] == 1

    r = client.post(f"/api/videos/{vid}/remove", json={}).json()
    assert r["ok"]
    session.expire_all()
    assert session.get(Video, vid) is None
    # Sin opciones: la propuesta pendiente desaparece, la voz se conserva y todo queda en el disco
    assert session.exec(select(KnowledgeItem)).all() == []
    assert len(session.exec(select(VoiceEmbedding)).all()) == 1
    meta = json.loads((folder / "datos" / "video.json").read_text(encoding="utf-8"))
    assert meta["speakers"][0]["person"] == "Iosu" and meta["speakers"][0]["embedding"] == [0.1, 0.2]
    assert (folder / "datos" / "vision.json").exists() and video.exists() and work.exists()


def test_remove_and_forget(client, session, tmp_path):
    person = Person(name="Iosu")
    v = Video(source_path=str(tmp_path / "no.mkv"), title="T", status="done")
    session.add(person), session.add(v)
    session.commit()
    session.add(VoiceEmbedding(person_id=person.id, video_id=v.id, vector=[0.1]))
    session.commit()
    client.post(f"/api/videos/{v.id}/remove", json={"forget": True})
    session.expire_all()
    assert session.exec(select(VoiceEmbedding)).all() == []
    assert session.get(Person, person.id) is not None
