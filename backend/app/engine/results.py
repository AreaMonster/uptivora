"""Persist a check outcome: result row, monitor state, incidents and alerts — atomically."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.engine.alerts import queue_down_alert, queue_up_alert
from app.engine.checker import CheckOutcome
from app.engine.state import Event, transition
from app.models import CheckResult, Incident, Monitor

CONFIRM_DELAY_SECONDS = 30  # re-check quickly after a first failure


@dataclass(frozen=True, slots=True)
class Claim:
    """Snapshot of a monitor taken when the worker leased it."""

    id: uuid.UUID
    url: str
    method: str
    timeout_seconds: int
    expected_status: str
    keyword: str | None
    follow_redirects: bool
    verify_tls: bool
    ssl_check_enabled: bool


def next_check_time(now: datetime, interval: int, *, confirming: bool) -> datetime:
    if confirming:
        return now + timedelta(seconds=min(CONFIRM_DELAY_SECONDS, interval))
    jitter = random.uniform(0, min(10.0, interval * 0.05))  # noqa: S311 — load spreading only
    return now + timedelta(seconds=interval + jitter)


async def _first_failure_time(
    db: AsyncSession, monitor_seq: int, failures: int, fallback: datetime
) -> datetime:
    if failures <= 1:
        return fallback
    ts = await db.scalar(
        select(CheckResult.checked_at)
        .where(CheckResult.monitor_seq == monitor_seq)
        .order_by(CheckResult.checked_at.desc())
        .offset(failures - 1)
        .limit(1)
    )
    return ts or fallback


HOLD_SECONDS = 60


async def defer_check(
    maker: async_sessionmaker[AsyncSession],
    worker_id: str,
    claim: Claim,
    seconds: int = HOLD_SECONDS,
) -> None:
    """Release a claim without recording a result and retry later (local network problem)."""
    async with maker() as db, db.begin():
        await db.execute(
            update(Monitor)
            .where(Monitor.id == claim.id, Monitor.lease_owner == worker_id)
            .values(
                next_check_at=func.now() + timedelta(seconds=seconds),
                lease_owner=None,
                lease_until=None,
            )
        )


async def apply_outcome(
    maker: async_sessionmaker[AsyncSession],
    settings: Settings,
    worker_id: str,
    claim: Claim,
    outcome: CheckOutcome,
    *,
    checked_at: datetime | None = None,
) -> Event | Literal["stale"]:
    now = checked_at or datetime.now(UTC)
    async with maker() as db, db.begin():
        m = await db.scalar(select(Monitor).where(Monitor.id == claim.id).with_for_update())
        if m is None:
            return "stale"  # deleted while we were checking
        if m.lease_owner != worker_id or m.is_paused or m.url != claim.url:
            # Paused, edited or re-leased meanwhile: the result no longer applies.
            if m.lease_owner == worker_id:
                m.lease_owner = m.lease_until = None
            return "stale"

        db.add(
            CheckResult(
                monitor_seq=m.seq,
                checked_at=now,
                is_up=outcome.is_up,
                status_code=outcome.status_code,
                response_ms=outcome.response_ms,
                error_kind=outcome.error_kind,
                error_message=(outcome.error_message or None) and outcome.error_message[:500],
            )
        )
        await db.flush()

        t = transition(
            m.status,
            m.consecutive_failures,
            m.consecutive_successes,
            is_up=outcome.is_up,
            down_threshold=m.down_threshold,
            recovery_threshold=m.recovery_threshold,
        )
        if t.status != m.status:
            m.last_status_change_at = now
        m.status = t.status
        m.consecutive_failures = t.consecutive_failures
        m.consecutive_successes = t.consecutive_successes
        m.last_checked_at = now
        m.last_status_code = outcome.status_code
        m.last_response_ms = outcome.response_ms if outcome.is_up else None
        m.last_error = None if outcome.is_up else (outcome.error_message or "Check failed")[:500]

        if claim.ssl_check_enabled and claim.url.startswith("https://"):
            if outcome.tls is not None:
                m.ssl_expires_at = outcome.tls.expires_at
                m.ssl_issuer = outcome.tls.issuer
                m.ssl_error = None
                m.ssl_last_checked_at = now
            elif outcome.tls_error:
                m.ssl_error = outcome.tls_error[:500]
                m.ssl_last_checked_at = now

        m.next_check_at = next_check_time(now, m.interval_seconds, confirming=t.confirming)
        m.lease_owner = m.lease_until = None

        if t.event == "down":
            started = await _first_failure_time(db, m.seq, t.consecutive_failures, now)
            incident = await db.scalar(
                select(Incident).where(Incident.monitor_id == m.id, Incident.resolved_at.is_(None))
            )
            if incident is None:  # partial unique index guarantees at most one open incident
                incident = Incident(
                    monitor_id=m.id,
                    started_at=started,
                    cause=(outcome.error_message or "Unreachable")[:500],
                    error_kind=outcome.error_kind,
                    status_code=outcome.status_code,
                )
                db.add(incident)
                await db.flush()
            await queue_down_alert(db, settings, m, incident)
        elif t.event == "up":
            incident = await db.scalar(
                select(Incident).where(Incident.monitor_id == m.id, Incident.resolved_at.is_(None))
            )
            if incident is not None:
                incident.resolved_at = now
                await db.flush()
                await queue_up_alert(db, settings, m, incident)
        return t.event
