"""Operational event log shown in the admin dashboard ("Application logs").

A logging handler buffers records in memory (bounded); ``flush_events`` writes them to the
``system_events`` table in one batch. Logging therefore never blocks a request or a check, and
a database outage cannot make logging itself fail (records are dropped when the buffer is full).

Captured: WARNING and above from every ``uptivora.*`` logger, plus INFO from the worker and
scheduler (start/stop, outages, recoveries).
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import SystemEvent

MAX_BUFFER = 2000
INFO_SOURCES = ("uptivora.worker", "uptivora.scheduler")
_SOURCE_PREFIX = "uptivora."


class _BufferHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.buffer: deque[dict] = deque(maxlen=MAX_BUFFER)
        # NB: not "self.lock" — logging.Handler already uses that name and holds it in emit().
        self._buffer_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        name = record.name
        if not name.startswith(_SOURCE_PREFIX):
            return
        if record.levelno < logging.WARNING and not name.startswith(INFO_SOURCES):
            return
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 — never raise from logging
            message = str(record.msg)
        details: dict = {"logger": name}
        if record.exc_info and record.exc_info[0] is not None:
            details["exception"] = f"{record.exc_info[0].__name__}: {record.exc_info[1]}"[:1000]
        with self._buffer_lock:
            self.buffer.append(
                {
                    "level": record.levelname.lower()[:10],
                    "source": name.removeprefix(_SOURCE_PREFIX).split(".")[0][:32],
                    "message": message[:1000],
                    "details": details,
                    "created_at": datetime.fromtimestamp(record.created, UTC),
                }
            )

    def drain(self) -> list[dict]:
        with self._buffer_lock:
            items = list(self.buffer)
            self.buffer.clear()
        return items


handler = _BufferHandler()


def install() -> None:
    """Attach the buffer handler to the ``uptivora`` logger tree (idempotent)."""
    root = logging.getLogger("uptivora")
    if handler not in root.handlers:
        root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)


async def flush_events(maker: async_sessionmaker[AsyncSession]) -> int:
    items = handler.drain()
    if not items:
        return 0
    try:
        async with maker() as db, db.begin():
            await db.execute(insert(SystemEvent), items)
    except Exception:  # noqa: BLE001 — DB down: drop rather than loop on logging errors
        return 0
    return len(items)
