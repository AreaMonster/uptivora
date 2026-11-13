"""Keep active monitors within the applicable limits — per user (hosted plans) or for the
whole installation (self-hosted licence).

* Over the limit: the newest active monitors are paused with reason ``plan_limit``.
* Room available: monitors paused for that reason are resumed, oldest first.
* Intervals faster than allowed are raised to the minimum.
Nothing is ever deleted, and pauses chosen by users or administrators are never touched.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.limits import Limits, instance_limits
from app.models import Monitor, MonitorStatus, PausedReason


async def enforce_limits(
    db: AsyncSession, limits: Limits, *, owner_id: uuid.UUID | None
) -> dict[str, int]:
    scope = [Monitor.owner_id == owner_id] if owner_id is not None else []
    active = list(
        (
            await db.scalars(
                select(Monitor)
                .where(*scope, Monitor.is_paused.is_(False))
                .order_by(Monitor.created_at, Monitor.id)
            )
        ).all()
    )
    paused = resumed = 0
    cap = limits.max_monitors
    if cap is not None and len(active) > cap:
        for m in reversed(active[cap:]):
            m.is_paused = True
            m.paused_reason = PausedReason.PLAN_LIMIT
            m.status = MonitorStatus.PAUSED
            m.lease_owner = m.lease_until = None
            paused += 1
        active = active[:cap]
    elif cap is None or len(active) < cap:
        stmt = (
            select(Monitor)
            .where(*scope, Monitor.paused_reason == PausedReason.PLAN_LIMIT)
            .order_by(Monitor.created_at, Monitor.id)
        )
        if cap is not None:
            stmt = stmt.limit(cap - len(active))
        for m in (await db.scalars(stmt)).all():
            m.is_paused = False
            m.paused_reason = None
            m.status = MonitorStatus.PENDING
            m.consecutive_failures = m.consecutive_successes = 0
            m.next_check_at = datetime.now(UTC)
            active.append(m)
            resumed += 1
    raised = 0
    for m in active:
        if m.interval_seconds < limits.min_interval_seconds:
            m.interval_seconds = limits.min_interval_seconds
            raised += 1
    await db.flush()
    return {"paused": paused, "resumed": resumed, "intervals_raised": raised}


async def enforce_instance(db: AsyncSession, settings: Settings) -> dict[str, int]:
    """Self-hosted: apply the licence limits to every monitor of the installation."""
    return await enforce_limits(db, await instance_limits(db, settings), owner_id=None)


async def enforce_instance_job(
    maker: async_sessionmaker[AsyncSession], settings: Settings
) -> dict[str, int]:
    """Worker job: picks up licence files that were added or removed on disk."""
    async with maker() as db, db.begin():
        return await enforce_instance(db, settings)
