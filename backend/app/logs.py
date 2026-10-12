"""Registros de la app: un fichero por día en `DATA_DIR/logs/AAAA-MM-DD.log` y el mismo texto en la consola.

Cada línea lleva fecha y hora, nivel, módulo y, si lo hay, el contexto del trabajo («[trabajo 3 · vídeo 1 ·
analyze]»), para seguir un flujo buscando su vídeo. Nunca se registra contenido (transcripciones, prompts,
notas, datos personales ni cuerpos de peticiones): solo ids, fases, tiempos y recuentos. Así el log se puede
pasar a quien ayude a encontrar un fallo.

Uso: `log = logging.getLogger(__name__)` en cada módulo. `setup` se llama al arrancar el servidor (no al
importar: los tests y los scripts no crean ficheros).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from pathlib import Path
from typing import Any

from .config import DATA_DIR

LOGS_DIR = DATA_DIR / "logs"
FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s%(ctx)s: %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"

_context: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)
_LABELS = {"job": "trabajo", "video": "vídeo", "followup": "seguimiento"}


def context_text(ctx: dict[str, Any] | None) -> str:
    """« [trabajo 3 · vídeo 1 · analyze]», o «» sin contexto."""
    if not ctx:
        return ""
    parts = [f"{_LABELS[k]} {ctx[k]}" for k in _LABELS if ctx.get(k) is not None]
    if ctx.get("stage"):
        parts.append(str(ctx["stage"]))
    return f" [{' · '.join(parts)}]" if parts else ""


@contextmanager
def context(**values: Any) -> Iterator[None]:
    """Añade a las líneas registradas dentro del bloque el trabajo, el vídeo o la fase (se acumula)."""
    token = _context.set({**(_context.get() or {}), **{k: v for k, v in values.items() if v is not None}})
    try:
        yield
    finally:
        _context.reset(token)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.ctx = context_text(_context.get())
        return True


def cleanup(folder: Path, keep_days: int, today: date) -> list[Path]:
    """Borra los registros de hace `keep_days` días o más (por la fecha del nombre; nada más)."""
    removed = []
    for f in folder.glob("*.log"):
        try:
            day = date.fromisoformat(f.stem)
        except ValueError:
            continue
        if (today - day).days >= keep_days:
            try:
                f.unlink()
                removed.append(f)
            except OSError:
                pass  # abierto por otro programa: se borrará otro día
    return removed


class DailyFileHandler(logging.Handler):
    """Escribe en el fichero del día. Al cambiar de día abre el nuevo sin renombrar nada: el rotado estándar
    renombra el fichero a medianoche y, en Windows, eso falla mientras está abierto."""

    def __init__(self, folder: Path, keep_days: int, today: Callable[[], date] = date.today):
        super().__init__()
        self.folder, self.keep_days, self.today = folder, keep_days, today
        self.day: date | None = None
        self.stream = None

    def _open(self, day: date) -> None:
        if self.stream:
            self.stream.close()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.stream = open(self.folder / f"{day:%Y-%m-%d}.log", "a", encoding="utf-8")  # noqa: SIM115
        self.day = day
        cleanup(self.folder, self.keep_days, day)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            day = self.today()
            if day != self.day:
                self._open(day)
            self.stream.write(self.format(record) + "\n")
            self.stream.flush()
        except Exception:  # noqa: BLE001  (un fallo al registrar nunca debe romper la app)
            self.handleError(record)

    def close(self) -> None:
        self.acquire()
        try:
            if self.stream:
                self.stream.close()
                self.stream = None
        finally:
            self.release()
        super().close()


def set_level(level: str) -> None:
    logging.getLogger().setLevel(getattr(logging, level, logging.INFO))


def setup(level: str = "INFO", keep_days: int = 30, folder: Path = LOGS_DIR,
          today: Callable[[], date] = date.today) -> None:
    """Consola y fichero diario con el mismo formato. Se puede llamar otra vez (sustituye lo anterior)."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    formatter, flt = logging.Formatter(FORMAT, DATEFMT), ContextFilter()
    for h in (logging.StreamHandler(sys.stderr), DailyFileHandler(folder, keep_days, today)):
        h.setFormatter(formatter)
        h.addFilter(flt)
        root.addHandler(h)
    set_level(level)
    # uvicorn configura sus propios handlers (sin fecha): sus mensajes y sus trazas pasan por los nuestros
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    # Cada petición y cada llamada al LLM ya se registran con más sentido (middleware de main.py y llm.py)
    for name in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
