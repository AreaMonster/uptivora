"""Periodic maintenance jobs. Each runs under a Postgres advisory lock, so with several
workers exactly one of them performs it at a time."""

from __future__ import annotations

import logging
import os
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.db import get_engine
from app.engine.alerts import queue_ssl_alert
from app.engine.scheduler import SchedulerStats
from app.models import Monitor

log = logging.getLogger("uptivora.housekeeping")

LOCK_IDS = {
    "rollup": 7101,
    "retention": 7102,
    "ssl": 7103,
    "billing": 7104,
    "partitions": 7105,
    "licences": 7106,
}
BATCH = 5000


async def with_advisory_lock(name: str, job: Callable[[], Awaitable[object]]) -> object | None:
    """Run ``job`` only if no other worker holds the lock ``name`` right now."""
    async with get_engine().connect() as conn:
        got = await conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_IDS[name]})
        await conn.commit()
        if not got:
            return None
        try:
            return await job()
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_IDS[name]})
            await conn.commit()


# --- hourly rollups -------------------------------------------------------------------------

_ROLLUP_SQL = text(
    """
    INSERT INTO check_rollups (monitor_seq, bucket_start, checks_total, checks_up,
                               response_ms_avg, response_ms_min, response_ms_max, response_ms_p95)
    SELECT monitor_seq,
           date_trunc('hour', checked_at) AS bucket,
           count(*),
           count(*) FILTER (WHERE is_up),
           round(avg(response_ms))::int,
           min(response_ms),
           max(response_ms),
           round(percentile_cont(0.95) WITHIN GROUP (ORDER BY response_ms))::int
      FROM check_results
     WHERE checked_at >= :since AND checked_at < :until
     GROUP BY monitor_seq, bucket
    ON CONFLICT (monitor_seq, bucket_start) DO UPDATE SET
           checks_total = EXCLUDED.checks_total,
           checks_up = EXCLUDED.checks_up,
           response_ms_avg = EXCLUDED.response_ms_avg,
           response_ms_min = EXCLUDED.response_ms_min,
           response_ms_max = EXCLUDED.response_ms_max,
           response_ms_p95 = EXCLUDED.response_ms_p95
    """
)


async def rollup_hours(maker: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    """(Re)aggregate completed hours since the newest rollup (minus 2 h of late results)."""
    async with maker() as db, db.begin():
        # First run (no rollups yet): start at the oldest raw check, so nothing is skipped.
        since = await db.scalar(
            text(
                "SELECT coalesce((SELECT max(bucket_start) - interval '2 hours' "
                "FROM check_rollups), (SELECT min(checked_at) FROM check_results), now())"
            )
        )
        until = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)  # completed hours
        result = await db.execute(_ROLLUP_SQL, {"since": since, "until": until})
    return result.rowcount or 0


# --- retention ------------------------------------------------------------------------------

# Individual checks are handled by engine.partitions (whole day partitions are dropped).
_PURGES = [
    ("retained_checks", "checked_at", "failed_check_retention_days"),
    ("check_rollups", "bucket_start", "rollup_retention_days"),
    ("audit_log", "created_at", "audit_retention_days"),
]
_FIXED_PURGES = [
    "DELETE FROM system_events WHERE created_at < now() - interval '30 days'",
    "DELETE FROM notification_outbox WHERE status IN ('sent', 'cancelled', 'failed') "
    "AND created_at < now() - interval '30 days'",
    "DELETE FROM sessions WHERE expires_at < now() - interval '7 days' "
    "OR revoked_at < now() - interval '7 days'",
    "DELETE FROM auth_tokens WHERE expires_at < now() - interval '7 days'",
    "DELETE FROM worker_heartbeats WHERE last_seen_at < now() - interval '1 day'",
]


async def purge_old_data(maker: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    from app.engine.partitions import expire_raw_checks

    deleted = await expire_raw_checks(maker, settings)
    for table, column, setting in _PURGES:
        days = getattr(settings, setting)
        while True:  # small batches keep locks and WAL bursts short
            async with maker() as db, db.begin():
                # table/column come from the constant _PURGES list above, never from input.
                res = await db.execute(
                    text(  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text
                        f"DELETE FROM {table} WHERE ctid IN (SELECT ctid FROM {table} "  # noqa: S608
                        f"WHERE {column} < now() - make_interval(days => :d) LIMIT :n)"
                    ),
                    {"d": days, "n": BATCH},
                )
            deleted += res.rowcount or 0
            if (res.rowcount or 0) < BATCH:
                break
    async with maker() as db, db.begin():
        for sql in _FIXED_PURGES:
            deleted += (await db.execute(text(sql))).rowcount or 0
    return deleted


# --- SSL certificate warnings ---------------------------------------------------------------


def ssl_bucket(days_left: int, warning_days: int) -> str | None:
    """One warning per bucket: at the warning window, 7 days, 1 day and on expiry."""
    if days_left < 0:
        return "expired"
    if days_left <= 1:
        return "1d"
    if days_left <= 7 and warning_days > 7:
        return "7d"
    if days_left <= warning_days:
        return f"{warning_days}d"
    return None


async def ssl_warning_sweep(maker: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    now = datetime.now(UTC)
    queued = 0
    async with maker() as db, db.begin():
        monitors = (
            await db.scalars(
                select(Monitor).where(
                    Monitor.ssl_check_enabled.is_(True),
                    Monitor.is_paused.is_(False),
                    Monitor.ssl_expires_at.is_not(None),
                    Monitor.ssl_expires_at
                    < func.now() + func.make_interval(0, 0, 0, Monitor.ssl_warning_days),
                )
            )
        ).all()
        for m in monitors:
            days_left = (m.ssl_expires_at - now).days if m.ssl_expires_at >= now else -1
            bucket = ssl_bucket(days_left, m.ssl_warning_days)
            if bucket and await queue_ssl_alert(
                db, settings, m, days_left=days_left, bucket=bucket
            ):
                queued += 1
    return queued


# --- worker heartbeat -----------------------------------------------------------------------

_HEARTBEAT_SQL = text(
    """
    INSERT INTO worker_heartbeats (worker_id, hostname, pid, version, started_at, last_seen_at,
                                   checks_total, checks_failed, in_flight, network_held)
    VALUES (:id, :host, :pid, :version, :started, now(), :total, :failed, :in_flight, :held)
    ON CONFLICT (worker_id) DO UPDATE SET last_seen_at = now(),
        checks_total = EXCLUDED.checks_total, checks_failed = EXCLUDED.checks_failed,
        in_flight = EXCLUDED.in_flight, network_held = EXCLUDED.network_held
    """
)


async def heartbeat(
    maker: async_sessionmaker[AsyncSession],
    settings: Settings,
    worker_id: str,
    started_at: datetime,
    stats: SchedulerStats,
) -> None:
    async with maker() as db, db.begin():
        await db.execute(
            _HEARTBEAT_SQL,
            {
                "id": worker_id,
                "host": socket.gethostname()[:255],
                "pid": os.getpid(),
                "version": settings.version,
                "started": started_at,
                "total": stats.checks_total,
                "failed": stats.checks_failed,
                "in_flight": stats.in_flight,
                "held": stats.network_held,
            },
        )


async def remove_heartbeat(maker: async_sessionmaker[AsyncSession], worker_id: str) -> None:
    async with maker() as db, db.begin():
        await db.execute(
            text("DELETE FROM worker_heartbeats WHERE worker_id = :id"), {"id": worker_id}
        )
