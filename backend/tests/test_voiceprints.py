"""Huellas y muestras de voz al aplicar la revisión: tramos, muestra, parecido y la API."""

from datetime import datetime

import numpy as np

from app import review
from app.models import Person, Video, VoiceEmbedding, VoiceSample
from app.pipeline.voiceprints import MIN_SECONDS, person_segments, pick_sample, similarity_to


def test_person_segments_use_the_fixed_speakers():
    utts = [{"start": 0.0, "end": 5.0, "speaker": "S1"}, {"start": 5.0, "end": 6.0, "speaker": "S1"},  # corta
            {"start": 6.0, "end": 12.0, "speaker": "MANUAL_7"}, {"start": 12.0, "end": 20.0, "speaker": "S2"}]
    assert person_segments(utts, {"S1": 3, "MANUAL_7": 7}) == [(3, 0.2, 4.8), (7, 6.2, 11.8)]


def test_pick_sample_takes_the_best_until_the_target():
    items = [(0.0, 4.0, 0.6), (10.0, 30.0, 0.9), (40.0, 46.0, 0.8), (50.0, 50.5, 0.95), (60.0, 66.0, 0.7)]
    chosen = pick_sample(items, min_s=5, target=15, max_s=30, clip=8)
    # El más parecido de verdad (medio segundo) es demasiado corto; el largo se recorta a 8 s
    assert chosen == [(10.0, 18.0, 0.9), (40.0, 46.0, 0.8), (60.0, 66.0, 0.7)]
    assert pick_sample([(0.0, 3.0, 0.9)], min_s=MIN_SECONDS) == []  # no llega al mínimo


def test_similarity_with_other_videos():
    a = [1.0, 0.0, 0.0]
    assert similarity_to(np.array(a), []) is None
    assert round(similarity_to(np.array(a), [[1.0, 0.1, 0.0], [0.9, 0.0, 0.1]]), 2) == 1.0
    assert similarity_to(np.array(a), [[0.0, 1.0, 0.0]]) == 0.0


def test_api_doubtful_voice_and_samples(client, session, tmp_path):
    ana = Person(name="Ana")
    v = Video(source_path="a.mkv", title="Uno", status="done", recorded_at=datetime(2026, 9, 2), review="propuestas")  # noqa: DTZ001
    session.add(ana), session.add(v)
    session.commit()
    audio = tmp_path / "ana.flac"
    audio.write_bytes(b"fLaC")
    e = VoiceEmbedding(person_id=ana.id, video_id=v.id, vector=[1.0, 0.0], doubtful=True, similarity=0.3, seconds=12)
    session.add(e), session.add(VoiceSample(person_id=ana.id, video_id=v.id, path=str(audio), seconds=12, score=0.8))
    session.commit()
    vid, eid, pid = v.id, e.id, ana.id
    data = client.get(f"/api/videos/{vid}").json()["review"]
    assert data["pending"]["voces"] == 1 and data["doubtful_voices"][0]["person_name"] == "Ana"
    voice = client.get(f"/api/people/{pid}/voice").json()
    assert voice["prints"] == 0 and voice["doubtful"] == 1 and voice["samples"][0]["video_title"] == "Uno"
    assert client.get(f"/api/voice-samples/{voice['samples'][0]['id']}/audio").content == b"fLaC"
    # Descartarla borra también su muestra; ya no queda nada por decidir y el vídeo queda revisado
    client.post(f"/api/voice-embeddings/{eid}/decide", json={"keep": False})
    session.expire_all()
    assert not audio.exists() and session.get(Video, vid).review == review.DONE
    assert client.get(f"/api/people/{pid}/voice").json() == {"prints": 0, "doubtful": 0, "samples": []}
