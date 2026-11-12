"""Background worker entry point: ``python -m app.worker``.

Runs the monitoring scheduler, the email outbox and housekeeping jobs. Start several worker
processes (or containers) to scale out; they coordinate through PostgreSQL.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.billing.service import process_due_subscriptions
from app.core import eventlog, ratelimit
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.engine import housekeeping as hk
from app.engine.netclient import build_clients
from app.engine.scheduler import Scheduler, new_worker_id
from app.notifications.outbox import drain_outbox

log = logging.getLogger("uptivora.worker")


async def _periodic(
    name: str,
    interval: float,
    job: Callable[[], Awaitable[object]],
    stop: asyncio.Event,
    *,
    initial_delay: float = 0.0,
) -> None:
    if initial_delay:
        try:
            await asyncio.wait_for(stop.wait(), timeout=initial_delay)
            return
        except TimeoutError:
            pass
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

    eventlog.install()
    worker_id = new_worker_id()
    started_at = datetime.now(UTC)
    clients = build_clients(max_connections=settings.worker_concurrency * 2)
    scheduler = Scheduler(maker, settings, clients, worker_id=worker_id)
    log.info("Worker %s started (edition=%s, env=%s)", worker_id, settings.edition, settings.env)

    def locked(name: str, job: Callable[[], Awaitable[object]]) -> Callable[[], Awaitable[object]]:
        return lambda: hk.with_advisory_lock(name, job)

    try:
        await asyncio.gather(
            scheduler.run(stop),
            _periodic(
                "heartbeat",
                15,
                lambda: hk.heartbeat(maker, settings, worker_id, started_at, scheduler.stats),
                stop,
            ),
            _periodic("outbox", 5, lambda: drain_outbox(maker, settings), stop),
            _periodic("eventlog", 10, lambda: eventlog.flush_events(maker), stop),
            _periodic(
                "rollup",
                600,
                locked("rollup", lambda: hk.rollup_hours(maker, settings)),
                stop,
                initial_delay=20,
            ),
            _periodic(
                "ssl-warnings",
                3600,
                locked("ssl", lambda: hk.ssl_warning_sweep(maker, settings)),
                stop,
                initial_delay=60,
            ),
            _periodic(
                "retention",
                6 * 3600,
                locked("retention", lambda: hk.purge_old_data(maker, settings)),
                stop,
                initial_delay=120,
            ),
            _periodic("ratelimit-purge", 3600, ratelimit.purge_expired, stop, initial_delay=300),
            _periodic(
                "billing",
                600,
                locked("billing", lambda: process_due_subscriptions(maker, settings)),
                stop,
                initial_delay=30,
            )
            if settings.is_hosted
            else asyncio.sleep(0),
        )
    finally:
        await clients.aclose()
        try:
            await hk.remove_heartbeat(maker, worker_id)
        except Exception:  # noqa: BLE001
            log.warning("Could not remove heartbeat for %s", worker_id)
        log.info("Worker %s stopped", worker_id)
        await eventlog.flush_events(maker)
        await get_engine().dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx/httpcore would log every customer URL at INFO level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    asyncio.run(run())


if __name__ == "__main__":
    main()
