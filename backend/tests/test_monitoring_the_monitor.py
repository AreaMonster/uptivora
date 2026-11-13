"""Phase 10: watching Uptivora itself — alert-storm guard, service health, heartbeat ping."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text, update

from app.engine import deadman, netwatch
from app.engine.checker import CheckOutcome
from app.engine.netwatch import NetworkWatch
from app.engine.scheduler import Scheduler
from app.models import CheckResult, Incident, Monitor, WorkerHeartbeat
from tests.localserver import LocalServer
from tests.test_engine_scheduler import isolate, make_monitor, make_user, maker  # noqa: F401

TIMEOUT = CheckOutcome(is_up=False, error_kind="timeout", error_message="Timed out after 10 s")
UP = CheckOutcome(is_up=True, status_code=200, response_ms=50)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def canary_checker(up: bool):
    calls: list[str] = []

    async def check(clients, spec, ua):
        calls.append(spec.url)
        return UP if up else TIMEOUT

    return check, calls


def watch(canaries_up: bool, clock: Clock, canaries=("https://a.example.org/",)):
    check, calls = canary_checker(canaries_up)
    return NetworkWatch(list(canaries), None, "ua", checker=check, clock=clock), calls


def fail_hosts(w: NetworkWatch, n: int, outcome: CheckOutcome = TIMEOUT) -> None:
    for i in range(n):
        w.record(f"h{i}.example.com", outcome)


# --- the guard ------------------------------------------------------------------------------


async def test_guard_is_off_without_canaries() -> None:
    w = NetworkWatch([], None, "ua")
    fail_hosts(w, 50)
    assert not w.enabled and await w.local_outage() is False


async def test_local_outage_needs_mass_failure_and_failing_canaries() -> None:
    clock = Clock()
    w, calls = watch(canaries_up=False, clock=clock)
    fail_hosts(w, netwatch.MIN_HOSTS - 1)
    assert await w.local_outage() is False and calls == []  # too few hosts to judge

    fail_hosts(w, 20)
    assert await w.local_outage() is True and w.held
    assert await w.local_outage() is True and len(calls) == 1  # verdict cached

    clock.t += netwatch.VERDICT_SECONDS + 1
    for i in range(20):
        w.record(f"h{i}.example.com", UP)  # network is back
    assert await w.local_outage() is False


async def test_real_outages_are_not_held_when_a_canary_answers() -> None:
    w, calls = watch(canaries_up=True, clock=Clock())
    fail_hosts(w, 30)
    assert await w.local_outage() is False and len(calls) == 1 and not w.held


async def test_http_errors_never_count_as_network_failure() -> None:
    w, calls = watch(canaries_up=False, clock=Clock())
    fail_hosts(w, 30, CheckOutcome(is_up=False, status_code=503, error_kind="http_status"))
    assert await w.local_outage() is False and calls == []


async def test_old_samples_expire() -> None:
    clock = Clock()
    w, _ = watch(canaries_up=False, clock=clock)
    fail_hosts(w, 30)
    clock.t += netwatch.WINDOW_SECONDS + 1
    assert w.mass_failure() is False


async def test_scheduler_holds_failures_during_a_local_outage(isolate, db, maker, settings) -> None:
    user = await make_user(db)
    m = await make_monitor(db, user)

    class AlwaysLocal(NetworkWatch):
        async def local_outage(self) -> bool:
            return True

    async def checker(clients, spec, ua):
        return TIMEOUT

    sched = Scheduler(
        maker,
        settings,
        None,
        worker_id="w-held",
        checker=checker,
        netwatch=AlwaysLocal(["https://a.example.org/"], None, "ua"),
    )
    [claim] = await sched.claim(10)
    await sched.process(claim)

    mon = await db.scalar(
        select(Monitor).where(Monitor.id == m.id).execution_options(populate_existing=True)
    )
    assert mon.lease_owner is None and mon.status.value == "pending"
    assert mon.next_check_at > datetime.now(UTC) + timedelta(seconds=30)
    results = await db.scalar(
        select(func.count()).select_from(CheckResult).where(CheckResult.monitor_seq == m.seq)
    )
    incidents = await db.scalar(
        select(func.count()).select_from(Incident).where(Incident.monitor_id == m.id)
    )
    assert results == 0 and incidents == 0
    assert sched.stats.events["held"] == 1 and sched.stats.network_held is True


# --- public service health ------------------------------------------------------------------


async def _beat(db, *, held: bool = False, age: int = 0) -> str:
    wid = f"t-{uuid.uuid4().hex[:8]}"
    db.add(
        WorkerHeartbeat(
            worker_id=wid,
            hostname="test",
            pid=1,
            version="t",
            last_seen_at=datetime.now(UTC) - timedelta(seconds=age),
            network_held=held,
        )
    )
    await db.commit()
    return wid


async def test_service_health_reports_without_details(isolate, client, db) -> None:
    await db.execute(text("DELETE FROM worker_heartbeats"))
    await db.execute(
        text("UPDATE notification_outbox SET status = 'sent' WHERE status IN ('pending','sending')")
    )
    await db.commit()

    stopped = await client.get("/api/health/service")
    assert stopped.status_code == 503 and stopped.json()["checks"] == "stopped"

    await _beat(db, age=300)  # stale heartbeats do not count
    assert (await client.get("/api/health/service")).json()["checks"] == "stopped"

    wid = await _beat(db)
    ok = await client.get("/api/health/service")
    assert ok.status_code == 200
    assert ok.json() == {"status": "ok", "checks": "running", "email": "ok"}

    await db.execute(
        update(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == wid).values(network_held=True)
    )
    await db.commit()
    held = await client.get("/api/health/service")
    assert held.status_code == 503 and held.json()["checks"] == "held"
    await db.execute(text("DELETE FROM worker_heartbeats"))
    await db.commit()


# --- outbound heartbeat ---------------------------------------------------------------------


class _Sched:
    def __init__(self) -> None:
        self.last_loop = time.monotonic()
        self.stats = type("S", (), {"network_held": False})()


async def test_heartbeat_ping_only_when_configured_and_healthy(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched = _Sched()
    assert await deadman.ping(settings, sched) is False  # default: no URL, no request
    with LocalServer() as srv:
        monkeypatch.setattr(settings, "heartbeat_url", srv.url("127.0.0.1", "/ok"))
        assert await deadman.ping(settings, sched) is True
        assert srv.hits == [("GET", "/ok")]

        sched.stats.network_held = True
        assert await deadman.ping(settings, sched) is False
        sched.stats.network_held = False
        sched.last_loop -= deadman.STALL_SECONDS + 1
        assert await deadman.ping(settings, sched) is False
        assert len(srv.hits) == 1
        monkeypatch.setattr(settings, "heartbeat_url", srv.url("127.0.0.1", "/status/500"))
        sched.last_loop = time.monotonic()
        assert await deadman.ping(settings, sched) is False
