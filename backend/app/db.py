"""Conexión a SQLite, creación de tablas e índice de búsqueda FTS5."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine

from . import models  # noqa: F401  (registra las tablas)
from .config import DATA_DIR

DB_PATH = DATA_DIR / "app.db"

engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
    text,
    kind UNINDEXED,      -- 'segment' | 'summary' | 'title' | 'frame'
    video_id UNINDEXED,
    ref_id UNINDEXED,    -- id del segmento / fotograma
    t UNINDEXED,         -- segundo del vídeo (si aplica)
    speaker UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
)
"""


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(FTS_DDL))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
