"""Scheduler: claims due monitors with leases and runs checks concurrently.

PostgreSQL is the queue (``FOR UPDATE SKIP LOCKED``): any number of worker processes can run
side by side, each due check is executed by exactly one of them, and a crashed worker's leases
simply expire. See docs/ARCHITECTURE.md §4.1.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.netguard import UnsafeURLError, validate_monitor_url
from app.engine.checker import CheckOutcome, CheckSpec, run_check
from app.engine.netclient import MonitorClients
from app.engine.results import Claim, apply_outcome

log = logging.getLogger("uptivora.scheduler")

LEASE_SECONDS = 120  # longer than the maximum check duration (timeout <= 60 s)
PER_HOST_CONCURRENCY = 2  # never hammer one host, whatever customers configure

_CLAIM_SQL = text(
    """
    UPDATE monitors AS m
       SET lease_owner = :worker, lease_until = now() + make_interval(secs => :lease)
     WHERE m.id IN (
            SELECT id FROM monitors
             WHERE is_paused = false
               AND next_check_at <= now()
               AND (lease_until IS NULL OR lease_until < now())
               AND EXISTS (SELECT 1 FROM users u WHERE u.id = monitors.owner_id AND u.is_active)
             ORDER BY next_check_at
             LIMIT :limit
             FOR UPDATE OF monitors SKIP LOCKED)
    RETURNING m.id, m.url, m.method, m.timeout_seconds, m.expected_status, m.keyword,
              m.follow_redirects, m.verify_tls, m.ssl_check_enabled
    """
)

Checker = Callable[[MonitorClients, CheckSpec, str], Awaitable[CheckOutcome]]


@dataclass
class SchedulerStats:
    checks_total: int = 0
    checks_failed: int = 0
    in_flight: int = 0
    events: dict[str, int] = field(default_factory=lambda: {"down": 0, "up": 0, "stale": 0})


class _HostLimiter:
    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._sems: dict[str, tuple[asyncio.Semaphore, int]] = {}

    async def run(self, host: str, coro_factory: Callable[[], Awaitable[CheckOutcome]]):
        sem, users = self._sems.get(host, (asyncio.Semaphore(self._limit), 0))
        self._sems[host] = (sem, users + 1)
        try:
            async with sem:
                return await coro_factory()
        finally:
            sem, users = self._sems[host]
            if users <= 1:
                del self._sems[host]
            else:
                self._sems[host] = (sem, users - 1)


class Scheduler:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        settings: Settings,
        clients: MonitorClients,
        *,
        worker_id: str,
        concurrency: int | None = None,
        batch_size: int = 100,
        poll_interval: float = 1.0,
        checker: Checker = run_check,
    ) -> None:
        self.maker = maker
        self.settings = settings
        self.clients = clients
        self.worker_id = worker_id
        self.concurrency = concurrency or settings.worker_concurrency
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.checker = checker
        self.stats = SchedulerStats()
        self._hosts = _HostLimiter(PER_HOST_CONCURRENCY)
        self._tasks: set[asyncio.Task] = set()

    async def claim(self, limit: int) -> list[Claim]:
        if limit <= 0:
            return []
        async with self.maker() as db, db.begin():
            rows = (
                await db.execute(
                    _CLAIM_SQL, {"worker": self.worker_id, "lease": LEASE_SECONDS, "limit": limit}
                )
            ).all()
        return [
            Claim(
                id=r.id,
                url=r.url,
                method=r.method,
                timeout_seconds=r.timeout_seconds,
                expected_status=r.expected_status,
                keyword=r.keyword,
                follow_redirects=r.follow_redirects,
                verify_tls=r.verify_tls,
                ssl_check_enabled=r.ssl_check_enabled,
            )
            for r in rows
        ]

    async def process(self, claim: Claim) -> None:
        self.stats.in_flight += 1
        try:
            spec = CheckSpec(
                url=claim.url,
                method=claim.method,
                timeout_seconds=claim.timeout_seconds,
                expected_status=claim.expected_status,
                keyword=claim.keyword,
                follow_redirects=claim.follow_redirects,
                verify_tls=claim.verify_tls,
                capture_tls=claim.ssl_check_enabled,
            )
            try:
                host = validate_monitor_url(claim.url).host
            except UnsafeURLError:
                host = claim.url
            outcome = await self._hosts.run(
                host, lambda: self.checker(self.clients, spec, self.settings.monitor_user_agent)
            )
            event = await apply_outcome(self.maker, self.settings, self.worker_id, claim, outcome)
            self.stats.checks_total += 1
            if not outcome.is_up:
                self.stats.checks_failed += 1
            if event:
                self.stats.events[event] = self.stats.events.get(event, 0) + 1
                if event in ("down", "up"):
                    log.info(
                        "Monitor %s is %s (%s)",
                        claim.id,
                        event.upper(),
                        outcome.error_message or "ok",
                    )
        except Exception:  # noqa: BLE001 — one bad check must not stop the scheduler
            log.exception("Check of monitor %s failed unexpectedly", claim.id)
        finally:
            self.stats.in_flight -= 1

    async def tick(self) -> int:
        """Claim as many due monitors as there is free capacity and start them."""
        free = self.concurrency - len(self._tasks)
        claims = await self.claim(min(free, self.batch_size))
        for c in claims:
            task = asyncio.create_task(self.process(c), name=f"check-{c.id}")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return len(claims)

    async def run(self, stop: asyncio.Event) -> None:
        log.info("Scheduler %s started (concurrency=%s)", self.worker_id, self.concurrency)
        while not stop.is_set():
            try:
                started = await self.tick()
            except Exception:  # noqa: BLE001 — e.g. database briefly unavailable
                log.exception("Scheduler tick failed; retrying")
                started = 0
            if started >= self.batch_size and len(self._tasks) < self.concurrency:
                continue  # backlog: claim again immediately
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass
        await self.drain()
        log.info("Scheduler %s stopped", self.worker_id)

    async def drain(self, grace_seconds: float = 30.0) -> None:
        """Let in-flight checks finish; unfinished leases expire and are retried elsewhere."""
        if self._tasks:
            _, pending = await asyncio.wait(set(self._tasks), timeout=grace_seconds)
            for task in pending:
                task.cancel()


def new_worker_id() -> str:
    import os
    import socket

    return f"{socket.gethostname()[:40]}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
