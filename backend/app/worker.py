"""Background worker entry point: ``python -m app.worker``.

Phase 2 runs the email outbox and housekeeping. The monitoring scheduler joins in Phase 3.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable

from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.notifications.outbox import drain_outbox

log = logging.getLogger("uptivora.worker")


async def _periodic(
    name: str, interval: float, job: Callable[[], Awaitable[object]], stop: asyncio.Event
) -> None:
    while not stop.is_set():
        try:
            await job()
        except Exception:  # noqa: BLE001 — a failing job must never kill the worker
            log.exception("Job %s failed", name)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass


async def run() -> None:
    settings = get_settings()
    maker = get_sessionmaker()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):  # Windows dev machines
            signal.signal(sig, lambda *_: stop.set())

    log.info("Worker started (edition=%s, env=%s)", settings.edition, settings.env)
    await asyncio.gather(
        _periodic("outbox", 5, lambda: drain_outbox(maker, settings), stop),
        _periodic("ratelimit-purge", 3600, ratelimit.purge_expired, stop),
    )
    await get_engine().dispose()
    log.info("Worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
