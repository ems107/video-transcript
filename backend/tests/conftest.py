import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import main
from app.db import FTS_DDL, get_session


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(text(FTS_DDL))
    return eng


@pytest.fixture(autouse=True)
def _no_real_work_dir(tmp_path, monkeypatch):
    """Ninguna prueba toca la carpeta de trabajo del usuario (`review.drop_audio` borra audios)."""
    from app import review

    monkeypatch.setattr(review, "WORK_DIR", tmp_path / "work")


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine, monkeypatch):
    """API con una base de datos en memoria (sin arrancar el worker)."""

    def _session():
        with Session(engine) as s:
            yield s

    main.app.dependency_overrides[get_session] = _session
    monkeypatch.setattr(main.worker, "notify", lambda: None)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
