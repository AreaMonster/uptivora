"""Daily partitions of ``check_results`` and tiered retention of individual checks.

* Every check lands in the partition of its UTC day (``check_results_pYYYYMMDD``). The worker
  creates partitions a few days ahead; anything outside them goes to ``check_results_default``.
* When a day is older than ``raw_retention_days`` (3), it is summarised into hourly rollups
  once more, its failed checks and the checks around incidents are copied to
  ``retained_checks``, and the partition is dropped — no row-by-row deletes, no table bloat.
* ``retained_checks`` keeps those rows for ``failed_check_retention_days`` (30), so incident
  timelines stay complete after the raw data is gone.

Partition names and bounds are built from dates only, never from input.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings

log = logging.getLogger("uptivora.partitions")

PARENT = "check_results"
DEFAULT_PARTITION = "check_results_default"
_NAME_RE = re.compile(r"^check_results_p(\d{8})$")
# Creating or dropping a partition locks the whole table. Give up quickly if a long query is
# in the way (and retry on the next run) instead of making every insert queue behind us.
LOCK_TIMEOUT = "SET LOCAL lock_timeout = '5s'"
COLUMNS = "monitor_seq, checked_at, is_up, status_code, response_ms, error_kind, error_message"


def partition_name(day: date) -> str:
    return f"{PARENT}_p{day:%Y%m%d}"


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0), tzinfo=UTC)
    return start, start + timedelta(days=1)


def _literal(ts: datetime) -> str:
    return ts.strftime("'%Y-%m-%d %H:%M:%S+00'")


async def ensure_partitions(
    maker: async_sessionmaker[AsyncSession], *, days_back: int = 1, days_ahead: int = 3
) -> int:
    """Create missing day partitions around today. Returns how many were created."""
    today = datetime.now(UTC).date()
    created = 0
    for offset in range(-days_back, days_ahead + 1):
        day = today + timedelta(days=offset)
        if await create_partition(maker, day):
            created += 1
    return created


async def create_partition(maker: async_sessionmaker[AsyncSession], day: date) -> bool:
    try:
        return await _create_partition(maker, day)
    except DBAPIError as exc:
        if "lock timeout" not in str(exc):
            raise
        log.warning("Partition for %s not created yet: table busy, retrying later", day)
        return False


async def _create_partition(maker: async_sessionmaker[AsyncSession], day: date) -> bool:
    name = partition_name(day)
    lo, hi = day_bounds(day)
    async with maker() as db, db.begin():
        if await db.scalar(text("SELECT to_regclass(:n)"), {"n": name}) is not None:
            return False
        await db.execute(text(LOCK_TIMEOUT))
        # Rows for this day may already sit in the default partition (e.g. after a long
        # worker outage); PostgreSQL refuses to create the partition until they are moved.
        await db.execute(
            text(f"CREATE TEMP TABLE _moved (LIKE {PARENT}) ON COMMIT DROP")  # noqa: S608
        )
        await db.execute(
            text(
                f"WITH d AS (DELETE FROM {DEFAULT_PARTITION} "  # noqa: S608
                "WHERE checked_at >= :lo AND checked_at < :hi RETURNING *) "
                "INSERT INTO _moved SELECT * FROM d"
            ),
            {"lo": lo, "hi": hi},
        )
        await db.execute(
            text(
                f"CREATE TABLE {name} PARTITION OF {PARENT} "
                f"FOR VALUES FROM ({_literal(lo)}) TO ({_literal(hi)})"
            )
        )
        await db.execute(text(f"INSERT INTO {PARENT} SELECT * FROM _moved"))  # noqa: S608
    log.info("Created partition %s", name)
    return True


async def list_day_partitions(db: AsyncSession) -> list[tuple[str, date]]:
    rows = await db.execute(
        text(
            "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "WHERE i.inhparent = CAST(:p AS regclass)"
        ),
        {"p": PARENT},
    )
    out = []
    for (relname,) in rows:
        m = _NAME_RE.match(relname)
        if m:
            out.append((relname, datetime.strptime(m.group(1), "%Y%m%d").date()))
    return sorted(out, key=lambda r: r[1])


def _retain_sql(source: str) -> str:
    """Copy failed checks and checks around incidents in [lo, hi) from ``source``."""
    return f"""
        INSERT INTO retained_checks ({COLUMNS})
        SELECT {COLUMNS} FROM {source}
         WHERE NOT is_up AND checked_at >= :lo AND checked_at < :hi
        UNION ALL
        SELECT DISTINCT c.monitor_seq, c.checked_at, c.is_up, c.status_code, c.response_ms,
               c.error_kind, c.error_message
          FROM incidents i
          JOIN monitors m ON m.id = i.monitor_id
          JOIN {source} c ON c.monitor_seq = m.seq
               AND c.checked_at >= i.started_at - make_interval(secs => 2 * m.interval_seconds)
               AND c.checked_at <= coalesce(i.resolved_at, now())
                                   + make_interval(secs => 2 * m.interval_seconds)
         WHERE c.is_up AND c.checked_at >= :lo AND c.checked_at < :hi
           AND i.started_at < CAST(:hi AS timestamptz) + interval '2 days'
           AND coalesce(i.resolved_at, now()) > CAST(:lo AS timestamptz) - interval '2 days'
    """  # noqa: S608 — table names are constants or generated from dates


async def expire_raw_checks(maker: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    """Drop day partitions past ``raw_retention_days`` (after keeping what must stay) and
    clean the default partition. Returns the number of partitions dropped."""
    from app.engine.housekeeping import _ROLLUP_SQL

    cutoff = datetime.now(UTC) - timedelta(days=settings.raw_retention_days)
    dropped = 0
    async with maker() as db:
        partitions = await list_day_partitions(db)
    for name, day in partitions:
        lo, hi = day_bounds(day)
        if hi > cutoff:
            break
        try:
            async with maker() as db, db.begin():
                await db.execute(text(LOCK_TIMEOUT))
                has_rows = await db.scalar(text(f"SELECT EXISTS (SELECT 1 FROM {name})"))  # noqa: S608
                if has_rows:
                    # Summarise the whole day once more (idempotent), so its hours are in
                    # check_rollups even if rows arrived after the regular rollup window.
                    await db.execute(_ROLLUP_SQL, {"since": lo, "until": hi})
                    await db.execute(text(_retain_sql(name)), {"lo": lo, "hi": hi})
                await db.execute(text(f"DROP TABLE {name}"))
        except DBAPIError as exc:
            if "lock timeout" not in str(exc):
                raise
            log.warning("Partition %s not dropped yet: table busy, retrying later", name)
            break
        dropped += 1
        log.info("Dropped partition %s", name)

    # Default partition: normally empty; same rules, row by row.
    async with maker() as db, db.begin():
        oldest = await db.scalar(text(f"SELECT min(checked_at) FROM {DEFAULT_PARTITION}"))  # noqa: S608
        if oldest is not None and oldest < cutoff:
            # Whole hours only, so the rollup of the boundary hour stays complete.
            limit = cutoff.replace(minute=0, second=0, microsecond=0)
            if limit > oldest:
                await db.execute(_ROLLUP_SQL, {"since": oldest, "until": limit})
                await db.execute(text(_retain_sql(DEFAULT_PARTITION)), {"lo": oldest, "hi": limit})
                await db.execute(
                    text(f"DELETE FROM {DEFAULT_PARTITION} WHERE checked_at < :hi"),  # noqa: S608
                    {"hi": limit},
                )
    return dropped
