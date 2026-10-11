"""Seguimientos: estado de los puntos, contexto, aplicar y deshacer vídeos, lo manual y la API."""

from datetime import datetime

import pytest

from app import followups as F
from app import followups_store as FS
from app import main
from app.config import Settings
from app.models import Followup, FollowupItem, FollowupVideo, Job, Video

# Fechas sin zona horaria, como las de la base de datos
D1, D2, D3 = datetime(2026, 10, 4, 19), datetime(2026, 10, 5, 17), datetime(2026, 10, 6, 10)  # noqa: DTZ001
AT = datetime(2026, 10, 11)  # noqa: DTZ001


def ev(video_id, date, evento, t="00:01:00", source="ia", nota=""):
    return {"video_id": video_id, "date": date.isoformat() if date else None, "t": t, "evento": evento,
            "nota": nota, "source": source, "at": AT.isoformat()}


def item(id_, kind, text, events, manual=False, hidden=False):
    return {"id": id_, "kind": kind, "text": text, "owner": "", "due": "", "manual": manual, "hidden": hidden,
            "events": events, "status": F.derive_status(kind, events)}


# --------------------------------------------------------------------------- lógica pura

def test_status_comes_from_the_last_event():
    assert F.derive_status("tarea", [ev(1, D1, "creada")]) == "abierta"
    assert F.derive_status("tarea", [ev(1, D1, "creada"), ev(2, D2, "hecha"), ev(2, D2, "avanza")]) == "hecha"
    assert F.derive_status("tarea", [ev(1, D1, "creada"), ev(2, D2, "hecha"), ev(3, D3, "reabierta")]) == "abierta"
    assert F.derive_status("decision", [ev(1, D1, "creada"), ev(2, D2, "cambiada")]) == "cambiada"
    assert F.status_for_event("duda", "resuelta") == "resuelta" and F.status_for_event("duda", "abierta") == "reabierta"


def test_state_at_only_counts_previous_videos():
    items = [item(1, "tarea", "Enviar el informe", [ev(1, D1, "creada"), ev(2, D2, "hecha")]),
             item(2, "duda", "¿Quién paga?", [ev(2, D2, "creada")]),
             item(3, "tarea", "Llamar al banco", [ev(None, None, "creada", source="manual")], manual=True),
             item(4, "tarea", "Borrada", [ev(1, D1, "creada")], manual=True, hidden=True)]
    before_2 = {it["id"]: it["status"] for it in F.state_at(items, D2)}
    assert before_2 == {1: "abierta", 3: "abierta"}  # lo del vídeo 2 aún no ha pasado; lo manual cuenta siempre
    assert {it["id"]: it["status"] for it in F.state_at(items, None)} == {1: "hecha", 2: "abierta", 3: "abierta"}


def test_context_block_with_ids_and_limit():
    items = [item(1, "tarea", "Enviar el informe", [ev(1, D1, "creada")]),
             item(2, "decision", "Usar la cuenta común", [ev(1, D1, "creada")]),
             item(3, "duda", "¿Quién paga?", [ev(1, D1, "creada"), ev(2, D2, "resuelta")])]
    block = F.context_block("Tutoría", "", "Va bien.", items, [D1, D2], D3, with_ids=True)
    assert "[T1] Enviar el informe" in block and "[D2] Usar la cuenta común" in block
    assert "Cerrado recientemente" in block and "[P3]" in block and "Va bien." in block
    assert "[T1]" not in F.context_block("Tutoría", "", "", items, [D1, D2], D3)
    # Antes del primer vídeo no hay nada
    assert F.context_block("Tutoría", "", "", items, [D1, D2], D1) == ""
    many = [item(i, "tarea", f"Tarea número {i} con un texto largo", [ev(1, D1, "creada")]) for i in range(1, 200)]
    block = F.context_block("T", "", "", many, [D1], D2, max_chars=1000)
    assert len(block) < 1100 and "más)" in block


def test_apply_update_validates_the_answer():
    items = [item(1, "tarea", "Enviar el informe al gestor", [ev(1, D1, "creada")]),
             item(2, "tarea", "Pedir cita", [ev(1, D1, "creada")], manual=True)]
    update = {
        "eventos": [
            {"id": "T1", "evento": "hecha", "t": "00:05:00", "nota": "Ya lo envió"},
            {"id": "T9", "evento": "hecha", "t": "00:05:00", "nota": ""},  # no existe
            {"id": "T1", "evento": "resuelta", "t": "00:05:00", "nota": ""},  # no vale para una tarea
            {"id": "[t1]", "evento": "hecha", "t": "02:00:00", "nota": ""},  # fuera del vídeo
            {"id": "T2", "evento": "hecha", "t": "00:06:00", "nota": "Ya tiene cita"},  # manual
        ],
        "nuevos": [
            {"tipo": "tarea", "texto": "Enviar el informe al gestor", "responsable": "", "plazo": "", "t": "00:07:00"},
            {"tipo": "duda", "texto": "¿Hace falta el aval?", "responsable": "", "plazo": "", "t": "00:08:00"},
            {"tipo": "duda", "texto": "¿Hace falta el aval?", "responsable": "", "plazo": "", "t": "00:09:00"},
        ],
    }
    plan = F.apply_update(items, update, 2, D2, 25 * 60, AT)
    by_item = {iid: e for iid, e in plan["events"]}
    assert by_item[1]["evento"] == "hecha" and by_item[1]["date"] == D2.isoformat() and by_item[1]["t"] == "00:05:00"
    # Lo decidió el usuario: el vídeo solo se anota como avance
    assert by_item[2]["evento"] == "avanza" and "hecha" in by_item[2]["nota"]
    assert len(plan["events"]) == 2 and len(plan["discarded"]) == 5
    assert [n["text"] for n in plan["new"]] == ["¿Hace falta el aval?"]


def test_revert_keeps_what_the_user_did():
    items = [item(1, "tarea", "A", [ev(1, D1, "creada"), ev(2, D2, "hecha")]),
             item(2, "tarea", "B", [ev(2, D2, "creada")]),
             item(3, "tarea", "C", [ev(2, D2, "creada")], manual=True),  # la IA lo creó y el usuario lo editó
             item(4, "tarea", "D", [ev(None, None, "creada", source="manual"), ev(2, D2, "avanza")], manual=True)]
    plan = F.revert(items, {2})
    assert plan["delete"] == [2]
    assert [e["evento"] for e in plan["update"][1]] == ["creada"]
    assert [e["evento"] for e in plan["update"][3]] == ["creada"]
    assert [e["source"] for e in plan["update"][4]] == ["manual"]


def test_render_markdown():
    items = [item(1, "tarea", "Enviar el informe", [ev(1, D1, "creada", t="00:02:00"), ev(2, D2, "hecha")])]
    videos = [{"id": 1, "title": "Primera", "date": D1, "link": "../2026-10-04%20-%20Primera", "contribution": "Empieza",
               "applied": True},
              {"id": 2, "title": "Segunda", "date": D2, "link": "", "contribution": "", "applied": False}]
    md = F.render_markdown({"name": "Tutoría", "summary": "Va bien."}, items, videos)
    assert "# Seguimiento: Tutoría" in md and "**[hecha]** Enviar el informe" in md
    assert "[2026-10-04 00:02:00](../2026-10-04%20-%20Primera/resumen.md)" in md and "*(sin aplicar)*" in md


# --------------------------------------------------------------------------- con la base de datos

@pytest.fixture(autouse=True)
def tmp_analyzed(tmp_path, monkeypatch):
    monkeypatch.setattr(FS, "load_settings", lambda: Settings(analyzed_dir=str(tmp_path / "Analizados")))
    return tmp_path / "Analizados"


def _video(session, date, title, analysis=None):
    v = Video(source_path=f"{title}.mkv", title=title, status="done", recorded_at=date, duration=25 * 60,
              analysis=analysis or {"resumen_breve": title})
    session.add(v)
    session.commit()
    session.add(Job(video_id=v.id, status="done"))
    session.commit()
    return v


class FakeAsk:
    """IA de mentira: responde por título del vídeo y guarda lo que recibe."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, state, desc, analysis):
        self.calls.append((state, desc))
        title = next(t for t in self.answers if t in desc)
        return self.answers[title]


ANSWERS = {
    "Primera": {"eventos": [], "nuevos": [
        {"tipo": "tarea", "texto": "Enviar el informe", "responsable": "Iosu", "plazo": "", "t": "00:02:00"},
        {"tipo": "duda", "texto": "¿Quién paga la cuota?", "responsable": "", "plazo": "", "t": "00:03:00"}],
        "resumen": "Empieza el tema.", "aporte": "Se plantea."},
    "Segunda": {"eventos": [{"id": "T1", "evento": "hecha", "t": "00:01:00", "nota": "Enviado"}], "nuevos": [
        {"tipo": "decision", "texto": "Abrir la cuenta común", "responsable": "", "plazo": "", "t": "00:04:00"}],
        "resumen": "Informe enviado y cuenta decidida.", "aporte": "Se cierra el informe."},
}


def _followup(session, *videos):
    f = Followup(name="Tutoría")
    session.add(f)
    session.commit()
    for v in videos:
        session.add(FollowupVideo(followup_id=f.id, video_id=v.id))
    session.commit()
    return f


def test_apply_in_order_and_rebuild_respects_manual(session, tmp_analyzed):
    v1, v2 = _video(session, D1, "Primera"), _video(session, D2, "Segunda")
    f = _followup(session, v1, v2)
    ask = FakeAsk(ANSWERS)
    FS.rebuild_from(session, f, None, ask)
    its = {it["text"]: it for it in FS.items(session, f.id)}
    assert its["Enviar el informe"]["status"] == "hecha" and its["Abrir la cuenta común"]["status"] == "vigente"
    assert f.summary == "Informe enviado y cuenta decidida."
    # El segundo vídeo recibe el estado del primero, con sus ids
    assert "[T" in ask.calls[1][0] and "Empieza el tema." in ask.calls[1][0]
    assert (tmp_analyzed / "Seguimiento - Tutoría" / "seguimiento.md").exists()

    # El usuario reabre la tarea y edita el resumen; al rehacer, la IA no lo deshace
    task = session.get(FollowupItem, its["Enviar el informe"]["id"])
    task.events = [*task.events, ev(None, None, "reabierta", source="manual")]
    task.manual, task.status = True, "abierta"
    f.summary, f.summary_manual = "Mi resumen", True
    session.add(task), session.add(f)
    session.commit()
    FS.rebuild_from(session, f, D2, ask)
    its = {it["text"]: it for it in FS.items(session, f.id)}
    assert its["Enviar el informe"]["status"] == "abierta"  # el «hecha» del vídeo queda como avance
    assert its["Enviar el informe"]["events"][-1]["evento"] == "avanza"
    assert f.summary == "Mi resumen" and f.summary_ai == "Informe enviado y cuenta decidida."
    assert len([it for it in its.values() if it["text"] == "Abrir la cuenta común"]) == 1


def test_update_for_video_older_video_marks_stale(session):
    v1, v2 = _video(session, D1, "Primera"), _video(session, D2, "Segunda")
    f = _followup(session, v2)
    FS.update_for_video(session, v2, v2.analysis, set(), FakeAsk(ANSWERS))
    assert session.get(FollowupVideo, (f.id, v2.id)).applied and f.stale_from is None
    # Un vídeo anterior que llega después: no se puede aplicar en orden sin rehacer
    session.add(FollowupVideo(followup_id=f.id, video_id=v1.id))
    session.commit()
    FS.update_for_video(session, v1, v1.analysis, set(), FakeAsk(ANSWERS))
    assert f.stale_from == D1 and "anterior" in f.stale_reason
    # Regenerar un vídeo ya aplicado sin rehacer también lo deja desactualizado
    f.stale_from = None
    FS.update_for_video(session, v2, v2.analysis, set(), FakeAsk(ANSWERS))
    assert f.stale_from == D2


def test_restore_version(session):
    v1 = _video(session, D1, "Primera")
    f = _followup(session, v1)
    FS.rebuild_from(session, f, None, FakeAsk(ANSWERS))
    version = FS.record_version(session, f, "Prueba")
    FS.revert_videos(session, f, {v1.id})
    assert FS.items(session, f.id) == [] and f.summary == ""
    FS.restore(session, f, version)
    assert len(FS.items(session, f.id)) == 2 and f.summary == "Empieza el tema." and f.stale_from is None


# --------------------------------------------------------------------------- API

def test_api_crud_items_and_versions(client, session):
    f = client.post("/api/followups", json={"name": " Tutoría "}).json()
    assert f["name"] == "Tutoría" and f["items"] == [] and f["n_videos"] == 0
    assert client.post(f"/api/followups/{f['id']}/items", json={"kind": "tarea", "text": ""}).status_code == 400
    f = client.post(f"/api/followups/{f['id']}/items", json={"kind": "tarea", "text": "Pedir cita"}).json()
    [it] = f["items"]
    assert it["manual"] and it["status"] == "abierta"
    f = client.put(f"/api/followups/{f['id']}/items/{it['id']}", json={"status": "hecha"}).json()
    assert f["items"][0]["status"] == "hecha" and f["items"][0]["events"][-1]["source"] == "manual"
    assert client.put(f"/api/followups/{f['id']}/items/{it['id']}", json={"status": "vigente"}).status_code == 400
    f = client.put(f"/api/followups/{f['id']}", json={"summary": "Mío"}).json()
    assert f["summary"] == "Mío" and f["summary_manual"]
    f = client.delete(f"/api/followups/{f['id']}/items/{it['id']}").json()
    assert f["items"] == []  # oculto, no borrado
    assert session.get(FollowupItem, it["id"]).hidden
    versions = client.get(f"/api/followups/{f['id']}/versions").json()
    with_item = next(v for v in versions if v["items"] == 1)
    f = client.post(f"/api/followups/{f['id']}/versions/{with_item['id']}/restore").json()
    assert len(f["items"]) == 1
    f = client.put(f"/api/followups/{f['id']}", json={"status": "archivado"}).json()
    assert f["status"] == "archivado"
    assert client.delete(f"/api/followups/{f['id']}").json() == {"ok": True}
    assert client.get(f"/api/followups/{f['id']}").status_code == 404


def test_api_videos(client, session, tmp_path):
    v1, v2 = _video(session, D1, "Primera"), _video(session, D2, "Segunda")
    f = client.post("/api/followups", json={"name": "Tutoría"}).json()
    # Añadir y aplicar: encola un trabajo que solo rehace el seguimiento
    r = client.post(f"/api/followups/{f['id']}/videos/{v1.id}", json={"apply": True}).json()
    job = session.get(Job, r["job_id"])
    session.refresh(job)
    assert job.status == "queued" and job.options["only"] == ["follow"] and job.options["follow_rebuild"] == [f["id"]]
    assert r["busy"]
    assert client.post(f"/api/followups/{f['id']}/videos/{v1.id}").status_code == 409
    # Sin aplicar: queda desactualizado
    r = client.post(f"/api/followups/{f['id']}/videos/{v2.id}", json={"apply": False}).json()
    assert r["stale_from"] and r["n_videos"] == 2
    detail = client.get(f"/api/videos/{v2.id}").json()
    assert detail["followups"] == [{"id": f["id"], "name": "Tutoría", "status": "abierto", "applied": False}]
    # Quitar sin rehacer un vídeo que no estaba aplicado: no cambia nada más
    r = client.delete(f"/api/followups/{f['id']}/videos/{v2.id}").json()
    assert r["n_videos"] == 1

    # Encolar un vídeo nuevo dentro del seguimiento
    video = tmp_path / "nuevo.mkv"
    video.write_bytes(b"x")
    r = client.post("/api/jobs", json={"path": str(video), "followup_ids": [f["id"]]}).json()
    assert session.get(FollowupVideo, (f["id"], r["video_id"]))
    client.put(f"/api/followups/{f['id']}", json={"status": "archivado"})
    video2 = tmp_path / "otro.mkv"
    video2.write_bytes(b"x")
    assert client.post("/api/jobs", json={"path": str(video2), "followup_ids": [f["id"]]}).status_code == 400


def test_regenerate_passes_follow_rebuild_once(client, session, tmp_path, monkeypatch):
    v = _video(session, D1, "Primera")
    f = _followup(session, v)
    monkeypatch.setattr(main.regen, "availability", lambda *_: dict.fromkeys(main.regen.LEVELS, ""))
    info = client.get(f"/api/videos/{v.id}/regenerate").json()
    assert info["followups"][0]["id"] == f.id
    r = client.post(f"/api/videos/{v.id}/regenerate", json={"level": "analysis", "follow_rebuild": [f.id]}).json()
    job = session.get(Job, r["job_id"])
    session.refresh(job)
    assert job.options["follow_rebuild"] == [f.id] and "follow" in job.options["redo"]
    job.status = "done"
    session.add(job)
    session.commit()
    client.post(f"/api/videos/{v.id}/learn")
    session.refresh(job)
    assert "follow_rebuild" not in job.options  # no se arrastra al siguiente encolado
