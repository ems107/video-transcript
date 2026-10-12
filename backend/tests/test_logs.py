"""Registros: fichero por día, limpieza, contexto, peticiones, LLM y errores de la web."""

import logging
from datetime import date

import pytest

from app import logs


@pytest.fixture
def restore_logging():
    """`logs.setup` cambia el logger raíz: se deja como estaba al terminar."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    for h in handlers:
        root.addHandler(h)
    root.setLevel(level)


def test_one_file_per_day_with_date_and_context(tmp_path, restore_logging):
    day = [date(2026, 10, 13)]
    logs.setup("INFO", 30, tmp_path, today=lambda: day[0])
    log = logging.getLogger("app.prueba")
    with logs.context(job=3, video=1), logs.context(stage="analyze"):
        log.info("Fase terminada")
    log.debug("No sale con INFO")
    day[0] = date(2026, 10, 14)
    log.warning("Otro día")
    first = (tmp_path / "2026-10-13.log").read_text(encoding="utf-8")
    assert "INFO    app.prueba [trabajo 3 · vídeo 1 · analyze]: Fase terminada" in first
    assert first.startswith("2026-") and "No sale" not in first
    assert "Otro día" in (tmp_path / "2026-10-14.log").read_text(encoding="utf-8")
    # Sin contexto, la línea no lleva corchetes
    assert "app.prueba: Otro día" in (tmp_path / "2026-10-14.log").read_text(encoding="utf-8")


def test_cleanup_removes_only_old_dated_logs(tmp_path):
    for name in ("2026-09-01.log", "2026-09-13.log", "2026-09-14.log", "notas.log", "otro.txt"):
        (tmp_path / name).write_text("x")
    removed = logs.cleanup(tmp_path, 30, date(2026, 10, 13))
    assert sorted(p.name for p in removed) == ["2026-09-01.log", "2026-09-13.log"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-09-14.log", "notas.log", "otro.txt"]


def test_uvicorn_lines_go_through_our_format(tmp_path, restore_logging):
    logs.setup("INFO", 30, tmp_path, today=lambda: date(2026, 10, 13))
    logging.getLogger("uvicorn.error").error("Exception in ASGI application")
    logging.getLogger("uvicorn.access").info("GET /api/status 200")
    logging.getLogger("httpx").info("HTTP Request: POST …")
    text = (tmp_path / "2026-10-13.log").read_text(encoding="utf-8")
    assert "ERROR   uvicorn.error: Exception in ASGI application" in text
    assert "GET /api/status" not in text and "HTTP Request" not in text


def test_importing_the_app_does_not_create_logs():
    from app import main  # noqa: F401

    assert not any(isinstance(h, logs.DailyFileHandler) for h in logging.getLogger().handlers)


def test_requests_are_logged_by_level(client, caplog):
    caplog.set_level(logging.DEBUG, logger="http")
    client.get("/api/settings")
    client.get("/api/videos/999")
    client.post("/api/proposals/decide", json={"accept": [], "reject": []})
    client.get("/api/search?q=algo privado")
    lines = [(r.levelname, r.getMessage()) for r in caplog.records if r.name == "http"]
    assert ("DEBUG", "GET /api/settings → 200") == (lines[0][0], lines[0][1].split(" (")[0])
    assert lines[1][0] == "WARNING" and lines[1][1].startswith("GET /api/videos/999 → 404")
    assert lines[2][0] == "INFO" and lines[2][1].startswith("POST /api/proposals/decide → 200")
    assert "privado" not in " ".join(m for _, m in lines)  # nunca la consulta
    assert logs.request_level("GET", 200, 1500) == logging.WARNING


def test_job_kind_for_the_log():
    from app.worker import job_kind

    assert job_kind({"file_mode": "copy"}) == "análisis"
    assert job_kind({"apply": True, "follow_rebuild": [2]}) == "aplicar la revisión; rehacer los seguimientos 2"
    assert job_kind({"only": ["learn"]}) == "solo learn"
    assert job_kind({"redo": ["correct", "analyze"]}) == "repetir correct, analyze"


def test_requeue_and_review_changes_are_logged(client, session, caplog):
    from app import review
    from app.models import Job, Video

    caplog.set_level(logging.INFO)
    v = Video(source_path="a.mkv", title="Uno", status="done", folder="x", review=review.DONE, analysis={"titulo": "Uno"})
    session.add(v)
    session.commit()
    session.add(Job(video_id=v.id, status="done", options={"file_mode": "copy"}))
    session.commit()
    client.post(f"/api/videos/{v.id}/corrections", json={"text": "Selu es José Luis"})
    msgs = [r.getMessage() for r in caplog.records]
    assert f"Vídeo {v.id}: vuelve a quedar pendiente de revisar por un cambio del usuario" in msgs
    assert "Selu" not in " ".join(msgs)  # el texto de la corrección no se registra
