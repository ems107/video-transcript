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
