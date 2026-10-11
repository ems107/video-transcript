"""Correcciones del usuario sobre un vídeo: API, uso en el análisis y aviso de «sin aplicar»."""

import json
import threading
from datetime import datetime

from app import removal, services
from app.config import Settings
from app.models import Video
from app.pipeline import analyze
from app.pipeline.base import JobContext
from app.prompts import corrections_block


def _video(session, **kw):
    v = Video(source_path="a.mkv", title="T", status="done", recorded_at=datetime(2026, 1, 1), **kw)
    session.add(v)
    session.commit()
    return v


def test_corrections_crud_and_pending(client, session):
    v = _video(session, analysis={"titulo": "T"})
    assert client.post(f"/api/videos/{v.id}/corrections", json={"text": "  "}).status_code == 400
    client.post(f"/api/videos/{v.id}/corrections", json={"text": "Selu es José Luis, no Sandra"})
    detail = client.get(f"/api/videos/{v.id}").json()
    [c] = detail["video_corrections"]
    assert c["text"] == "Selu es José Luis, no Sandra" and detail["corrections_pending"] and not c["applied"]

    # El análisis guarda con qué correcciones se generó: ya no está pendiente
    vid = session.get(Video, v.id)
    vid.analysis = {"titulo": "T", "correcciones_aplicadas": services.corrections_applied([c])}
    session.add(vid)
    session.commit()
    detail = client.get(f"/api/videos/{v.id}").json()
    assert not detail["corrections_pending"] and detail["video_corrections"][0]["applied"]

    # Editarla o borrarla vuelve a dejarla pendiente
    client.put(f"/api/corrections/{c['id']}", json={"text": "Selu es José Luis"})
    detail = client.get(f"/api/videos/{v.id}").json()
    assert detail["corrections_pending"] and not detail["video_corrections"][0]["applied"]
    client.delete(f"/api/corrections/{c['id']}")
    assert client.get(f"/api/videos/{v.id}").json()["video_corrections"] == []


def test_no_pending_without_corrections(client, session):
    v = _video(session, analysis={"titulo": "T"})  # vídeo analizado antes de existir las correcciones
    assert not client.get(f"/api/videos/{v.id}").json()["corrections_pending"]


def test_corrections_block():
    assert corrections_block(["", " "]) == ""
    block = corrections_block(["Selu es José Luis"])
    assert "prevalecen" in block and "- Selu es José Luis" in block


class FakeLLM:
    def __init__(self):
        self.prompts = []

    def start(self):
        pass

    def chat_json(self, system, user, schema, max_tokens=0):
        self.prompts.append(user)
        if "titulo" in schema["properties"]:
            return {"titulo": "T", "resumen_breve": "", "resumen_detallado": "", "participantes": [], "temas": [],
                    "tareas": [], "decisiones": [], "pendientes": []}
        return {"resumen": "", "temas": [], "tareas": [], "decisiones": [], "pendientes": [], "identidades": [],
                "apodos": []}


def test_analysis_receives_corrections(tmp_path):
    ctx = JobContext(job_id=1, video_id=1, source_path=tmp_path / "v.mp4", work_dir=tmp_path, settings=Settings(),
                     options={}, profile=None, people=[], report=lambda f, m: None, cancel_event=threading.Event(),
                     corrections=[{"id": 4, "text": "La tarea X no se acordó", "updated_at": "2026-10-11T10:00:00"}])
    ctx.save("corrected.json", [{"start": 1.0, "end": 2.0, "speaker": "S0", "text": "Hola"}])
    ctx.save("probe.json", {"duration": 60})
    llm = FakeLLM()
    analyze.run(ctx, llm)
    assert all("La tarea X no se acordó" in p for p in llm.prompts)  # bloques e informe final
    assert ctx.load("analysis.json")["correcciones_aplicadas"] == [{"id": 4, "updated_at": "2026-10-11T10:00:00"}]


def test_corrections_saved_for_recovery(client, session, tmp_path):
    folder = tmp_path / "carpeta"
    folder.mkdir()
    v = _video(session, folder=str(folder))
    client.post(f"/api/videos/{v.id}/corrections", json={"text": "Iosu es el tutor"})
    removal.save_recovery(session, session.get(Video, v.id))
    meta = json.loads((folder / "datos" / "video.json").read_text(encoding="utf-8"))
    assert [c["text"] for c in meta["corrections"]] == ["Iosu es el tutor"]
