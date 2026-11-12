"""Scheduler, outcome persistence, incidents, alerts and housekeeping (real PostgreSQL)."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text, update

from app.auth.service import create_user
from app.core.db import get_sessionmaker
from app.engine import housekeeping as hk
from app.engine.checker import CheckOutcome, CheckSpec, TlsInfo
from app.engine.results import apply_outcome
from app.engine.scheduler import Scheduler
from app.models import (
    CheckResult,
    CheckRollup,
    Incident,
    Monitor,
    MonitorStatus,
    NotificationKind,
    NotificationOutbox,
    NotificationSettings,
    User,
    WorkerHeartbeat,
)


class ScriptedChecker:
    """Returns pre-programmed outcomes per URL (default: up)."""

    def __init__(self) -> None:
        self.script: dict[str, list[CheckOutcome]] = {}
        self.calls: list[str] = []

    def push(self, url: str, *outcomes: CheckOutcome) -> None:
        self.script.setdefault(url, []).extend(outcomes)

    async def __call__(self, clients, spec: CheckSpec, ua: str) -> CheckOutcome:
        self.calls.append(spec.url)
        queue = self.script.get(spec.url)
        if queue:
            return queue.pop(0)
        return CheckOutcome(is_up=True, status_code=200, response_ms=120)


UP = CheckOutcome(is_up=True, status_code=200, response_ms=100)
DOWN = CheckOutcome(
    is_up=False,
    status_code=503,
    response_ms=40,
    error_kind="http_status",
    error_message="HTTP 503 Service Unavailable (expected 200-399)",
)


@pytest.fixture
async def isolate(db):
    """Push every pre-existing monitor far into the future so only this test's are due."""
    await db.execute(
        update(Monitor).values(
            next_check_at=func.now() + text("interval '1 year'"), lease_owner=None, lease_until=None
        )
    )
    await db.commit()


@pytest.fixture
def maker(migrated_db_url):
    return get_sessionmaker()


async def make_user(db, *, verified: bool = True, active: bool = True) -> User:
    user = await create_user(
        db, email=f"eng-{uuid.uuid4().hex[:10]}@example.com", password="Engine-test-pass-1"
    )
    user.email_verified_at = datetime.now(UTC) if verified else None
    user.is_active = active
    await db.commit()
    return user


async def make_monitor(db, user: User, **kw) -> Monitor:
    m = Monitor(
        owner_id=user.id,
        name=kw.pop("name", "Site"),
        url=kw.pop("url", f"https://{uuid.uuid4().hex[:8]}.example.com/"),
        next_check_at=datetime.now(UTC) - timedelta(seconds=1),
        **kw,
    )
    db.add(m)
    await db.commit()
    return m


async def run_once(sched: Scheduler) -> int:
    started = await sched.tick()
    await sched.drain()
    return started


# The test session runs at READ COMMITTED, so each statement sees the workers' commits;
# populate_existing refreshes objects already in the identity map.
async def reload(db, model, id_):
    return await db.get(model, id_, populate_existing=True)


async def outbox_for(db, monitor_id) -> list[NotificationOutbox]:
    return list(
        (
            await db.scalars(
                select(NotificationOutbox)
                .where(NotificationOutbox.monitor_id == monitor_id)
                .order_by(NotificationOutbox.created_at)
                .execution_options(populate_existing=True)
            )
        ).all()
    )


async def test_full_outage_lifecycle(isolate, db, maker, settings) -> None:
    user = await make_user(db)
    m = await make_monitor(db, user, down_threshold=2)
    checker = ScriptedChecker()
    checker.push(m.url, UP, DOWN, DOWN, DOWN, UP)
    sched = Scheduler(maker, settings, None, worker_id="w-life", checker=checker)

    async def step():
        await db.execute(
            update(Monitor)
            .where(Monitor.id == m.id)
            .values(next_check_at=func.now() - text("interval '1 second'"))
        )
        await db.commit()
        assert await run_once(sched) == 1

    await step()
    mon = await reload(db, Monitor, m.id)
    assert mon.status == MonitorStatus.UP and mon.last_response_ms == 100

    await step()  # first failure: confirming, re-check soon, still "up"
    mon = await reload(db, Monitor, m.id)
    assert mon.status == MonitorStatus.UP and mon.consecutive_failures == 1
    assert mon.next_check_at - datetime.now(UTC) < timedelta(seconds=31)
    assert await outbox_for(db, m.id) == []

    await step()  # second failure: confirmed outage
    mon = await reload(db, Monitor, m.id)
    assert mon.status == MonitorStatus.DOWN and "503" in mon.last_error
    incidents = (await db.scalars(select(Incident).where(Incident.monitor_id == m.id))).all()
    assert len(incidents) == 1 and incidents[0].resolved_at is None
    # Incident starts at the FIRST failed check, not at confirmation time.
    first_fail = (
        await db.scalars(
            select(CheckResult.checked_at)
            .where(CheckResult.monitor_id == m.id, CheckResult.is_up.is_(False))
            .order_by(CheckResult.checked_at)
        )
    ).first()
    assert incidents[0].started_at == first_fail
    mails = await outbox_for(db, m.id)
    assert [x.kind for x in mails] == [NotificationKind.MONITOR_DOWN]
    assert mails[0].recipient == user.email and "DOWN" in mails[0].subject

    await step()  # still down: no second email
    assert len(await outbox_for(db, m.id)) == 1

    await step()  # recovered
    mon = await reload(db, Monitor, m.id)
    assert mon.status == MonitorStatus.UP and mon.last_error is None
    inc = await reload(db, Incident, incidents[0].id)
    assert inc.resolved_at is not None
    mails = await outbox_for(db, m.id)
    assert [x.kind for x in mails] == [NotificationKind.MONITOR_DOWN, NotificationKind.MONITOR_UP]
    assert "RECOVERED" in mails[1].subject
    count = await db.scalar(
        select(func.count()).select_from(CheckResult).where(CheckResult.monitor_id == m.id)
    )
    assert count == 5


async def test_alert_preferences_and_verification(isolate, db, maker, settings) -> None:
    unverified = await make_user(db, verified=False)
    muted_user = await make_user(db)
    await db.execute(
        update(NotificationSettings)
        .where(NotificationSettings.user_id == muted_user.id)
        .values(notify_down=False)
    )
    await db.commit()
    m1 = await make_monitor(db, unverified, down_threshold=1)
    m2 = await make_monitor(db, muted_user, down_threshold=1)
    m3 = await make_monitor(db, muted_user, down_threshold=1, notifications_enabled=False)
    checker = ScriptedChecker()
    for m in (m1, m2, m3):
        checker.push(m.url, DOWN)
    await run_once(Scheduler(maker, settings, None, worker_id="w-pref", checker=checker))
    for m in (m1, m2, m3):
        assert (await reload(db, Monitor, m.id)).status == MonitorStatus.DOWN
        assert await outbox_for(db, m.id) == []  # incident recorded, but no email
        assert (
            await db.scalar(
                select(func.count()).select_from(Incident).where(Incident.monitor_id == m.id)
            )
            == 1
        )


async def test_tls_info_persisted(isolate, db, maker, settings) -> None:
    user = await make_user(db)
    m = await make_monitor(db, user)
    expires = datetime(2030, 1, 1, tzinfo=UTC)
    checker = ScriptedChecker()
    checker.push(
        m.url,
        CheckOutcome(
            is_up=True,
            status_code=200,
            response_ms=50,
            tls=TlsInfo(expires, "Let's Encrypt R11", "x"),
        ),
    )
    await run_once(Scheduler(maker, settings, None, worker_id="w-tls", checker=checker))
    mon = await reload(db, Monitor, m.id)
    assert mon.ssl_expires_at == expires and mon.ssl_issuer == "Let's Encrypt R11"


async def test_paused_suspended_and_future_monitors_not_claimed(isolate, db, maker, settings):
    active = await make_user(db)
    suspended = await make_user(db, active=False)
    await make_monitor(db, active, is_paused=True, status=MonitorStatus.PAUSED)
    await make_monitor(db, suspended)
    future = await make_monitor(db, active)
    future.next_check_at = datetime.now(UTC) + timedelta(minutes=5)
    await db.commit()
    checker = ScriptedChecker()
    assert (
        await run_once(Scheduler(maker, settings, None, worker_id="w-skip", checker=checker)) == 0
    )


async def test_result_discarded_when_monitor_changed_during_check(isolate, db, maker, settings):
    user = await make_user(db)
    m = await make_monitor(db, user)
    sched = Scheduler(maker, settings, None, worker_id="w-stale")
    [claim] = await sched.claim(10)
    await db.execute(
        update(Monitor).where(Monitor.id == m.id).values(url="https://new.example.com/")
    )
    await db.commit()
    assert await apply_outcome(maker, settings, "w-stale", claim, DOWN) == "stale"
    assert (
        await db.scalar(
            select(func.count()).select_from(CheckResult).where(CheckResult.monitor_id == m.id)
        )
        == 0
    )
    # A different worker's result is also rejected.
    assert await apply_outcome(maker, settings, "intruder", claim, DOWN) == "stale"


async def test_leases_prevent_double_claims_and_expire(isolate, db, maker, settings) -> None:
    user = await make_user(db)
    m = await make_monitor(db, user)
    a = Scheduler(maker, settings, None, worker_id="w-a")
    b = Scheduler(maker, settings, None, worker_id="w-b")
    assert len(await a.claim(10)) == 1
    assert await b.claim(10) == []
    # Worker A "crashes": its lease expires and B may take over.
    await db.execute(
        update(Monitor)
        .where(Monitor.id == m.id)
        .values(lease_until=func.now() - text("interval '1 second'"))
    )
    await db.commit()
    assert [c.id for c in await b.claim(10)] == [m.id]


async def test_concurrent_workers_check_each_monitor_exactly_once(isolate, db, maker, settings):
    user = await make_user(db)
    n = 300
    db.add_all(
        [
            Monitor(
                owner_id=user.id,
                name=f"M{i}",
                url=f"https://h{i}.example.com/",
                next_check_at=datetime.now(UTC) - timedelta(seconds=1),
            )
            for i in range(n)
        ]
    )
    await db.commit()
    ids = set((await db.scalars(select(Monitor.id).where(Monitor.owner_id == user.id))).all())

    async def fast_checker(clients, spec, ua):
        await asyncio.sleep(0.005)
        return UP

    workers = [
        Scheduler(
            maker,
            settings,
            None,
            worker_id=f"w-load-{i}",
            concurrency=40,
            batch_size=40,
            checker=fast_checker,
        )
        for i in range(3)
    ]
    started = time.monotonic()
    total = 0
    while total < n and time.monotonic() - started < 60:
        counts = await asyncio.gather(*(w.tick() for w in workers))
        total += sum(counts)
        await asyncio.gather(*(w.drain() for w in workers))
    elapsed = time.monotonic() - started
    rows = (
        await db.execute(
            select(CheckResult.monitor_id, func.count())
            .where(CheckResult.monitor_id.in_(ids))
            .group_by(CheckResult.monitor_id)
        )
    ).all()
    assert total == n and len(rows) == n and all(c == 1 for _, c in rows)
    assert sum(w.stats.checks_total for w in workers) == n
    assert elapsed < 30, f"300 checks took {elapsed:.1f}s"


async def test_rollups_match_raw_data(isolate, db, maker, settings) -> None:
    user = await make_user(db)
    m = await make_monitor(db, user)
    base = (datetime.now(UTC) - timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    for i in range(12):  # 12 checks in one complete hour: 9 up, 3 down
        db.add(
            CheckResult(
                monitor_id=m.id,
                checked_at=base + timedelta(minutes=5 * i),
                is_up=i % 4 != 0,
                response_ms=100 + i * 10 if i % 4 else None,
            )
        )
    await db.commit()
    await hk.rollup_hours(maker, settings)
    await hk.rollup_hours(maker, settings)  # idempotent
    r = await db.scalar(
        select(CheckRollup).where(CheckRollup.monitor_id == m.id, CheckRollup.bucket_start == base)
    )
    assert (r.checks_total, r.checks_up) == (12, 9)
    assert r.response_ms_min == 110 and r.response_ms_max == 210


async def test_retention_purges_old_results(isolate, db, maker, settings) -> None:
    user = await make_user(db)
    m = await make_monitor(db, user)
    old = datetime.now(UTC) - timedelta(days=settings.raw_retention_days + 1)
    db.add_all(
        [
            CheckResult(monitor_id=m.id, checked_at=old, is_up=True),
            CheckResult(monitor_id=m.id, checked_at=datetime.now(UTC), is_up=True),
        ]
    )
    await db.commit()
    await hk.purge_old_data(maker, settings)
    left = (
        await db.scalars(select(CheckResult.checked_at).where(CheckResult.monitor_id == m.id))
    ).all()
    assert len(left) == 1 and left[0] > old


def test_ssl_buckets() -> None:
    assert hk.ssl_bucket(20, 14) is None
    assert hk.ssl_bucket(14, 14) == "14d"
    assert hk.ssl_bucket(6, 14) == "7d"
    assert hk.ssl_bucket(6, 5) is None
    assert hk.ssl_bucket(4, 5) == "5d"
    assert hk.ssl_bucket(1, 14) == "1d"
    assert hk.ssl_bucket(-1, 14) == "expired"


async def test_ssl_warning_sweep_is_deduplicated(isolate, db, maker, settings) -> None:
    user = await make_user(db)
    m = await make_monitor(db, user, ssl_warning_days=14)
    m.ssl_expires_at = datetime.now(UTC) + timedelta(days=5, hours=2)
    far = await make_monitor(db, user)
    far.ssl_expires_at = datetime.now(UTC) + timedelta(days=60)
    await db.commit()
    await hk.ssl_warning_sweep(maker, settings)
    await hk.ssl_warning_sweep(maker, settings)
    mails = await outbox_for(db, m.id)
    assert len(mails) == 1 and mails[0].kind == NotificationKind.SSL_EXPIRING
    assert "5 days" in mails[0].subject
    assert await outbox_for(db, far.id) == []


async def test_heartbeat_and_advisory_lock(isolate, db, maker, settings) -> None:
    sched = Scheduler(maker, settings, None, worker_id="w-hb")
    sched.stats.checks_total = 7
    await hk.heartbeat(maker, settings, "w-hb", datetime.now(UTC), sched.stats)
    await hk.heartbeat(maker, settings, "w-hb", datetime.now(UTC), sched.stats)
    hb = await db.get(WorkerHeartbeat, "w-hb")
    assert hb.checks_total == 7
    await hk.remove_heartbeat(maker, "w-hb")

    entered = asyncio.Event()
    release = asyncio.Event()

    async def slow_job():
        entered.set()
        await release.wait()
        return "first"

    first = asyncio.create_task(hk.with_advisory_lock("rollup", slow_job))
    await entered.wait()
    assert await hk.with_advisory_lock("rollup", lambda: asyncio.sleep(0, "second")) is None
    release.set()
    assert await first == "first"
