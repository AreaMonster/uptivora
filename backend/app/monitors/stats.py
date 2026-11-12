"""Uptime and response-time statistics.

Raw ``check_results`` are used where available; ``check_rollups`` (hourly) cover older data.
For a given monitor, everything before the end of its newest rollup bucket is read from
rollups and everything after from raw results, so no check is counted twice.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

RANGES = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}
# Chart bucket size per range (keeps every chart at ~100-300 points).
BUCKETS = {
    "24h": timedelta(minutes=5),
    "7d": timedelta(hours=1),
    "30d": timedelta(hours=6),
    "90d": timedelta(days=1),
}


async def uptime_24h_bulk(
    db: AsyncSession, monitor_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, float]:
    if not monitor_ids:
        return {}
    rows = await db.execute(
        text(
            """
            SELECT monitor_id, count(*) FILTER (WHERE is_up) AS up, count(*) AS total
            FROM check_results
            WHERE monitor_id = ANY(:ids) AND checked_at > now() - interval '24 hours'
            GROUP BY monitor_id
            """
        ),
        {"ids": list(monitor_ids)},
    )
    return {r.monitor_id: round(100.0 * r.up / r.total, 3) for r in rows if r.total}


async def _rollup_cutoff(db: AsyncSession, monitor_id: uuid.UUID) -> datetime | None:
    last = await db.scalar(
        text("SELECT max(bucket_start) FROM check_rollups WHERE monitor_id = :m"),
        {"m": monitor_id},
    )
    return last + timedelta(hours=1) if last else None


async def uptime(db: AsyncSession, monitor_id: uuid.UUID, since: datetime) -> float | None:
    cutoff = await _rollup_cutoff(db, monitor_id)
    up = total = 0
    if cutoff and cutoff > since:
        row = (
            await db.execute(
                text(
                    """
                    SELECT coalesce(sum(checks_up), 0) AS up,
                           coalesce(sum(checks_total), 0) AS total
                    FROM check_rollups
                    WHERE monitor_id = :m AND bucket_start >= :since AND bucket_start < :cutoff
                    """
                ),
                {"m": monitor_id, "since": since, "cutoff": cutoff},
            )
        ).one()
        up, total = int(row.up), int(row.total)
    raw_since = max(since, cutoff) if cutoff else since
    row = (
        await db.execute(
            text(
                """
                SELECT count(*) FILTER (WHERE is_up) AS up, count(*) AS total
                FROM check_results WHERE monitor_id = :m AND checked_at >= :since
                """
            ),
            {"m": monitor_id, "since": raw_since},
        )
    ).one()
    up += int(row.up)
    total += int(row.total)
    return round(100.0 * up / total, 3) if total else None


async def uptime_summary(db: AsyncSession, monitor_id: uuid.UUID) -> dict[str, float | None]:
    now = datetime.now(UTC)
    return {name: await uptime(db, monitor_id, now - delta) for name, delta in RANGES.items()}


async def series(db: AsyncSession, monitor_id: uuid.UUID, range_name: str) -> list[dict]:
    """Bucketed response time + uptime for charts."""
    since = datetime.now(UTC) - RANGES[range_name]
    bucket = BUCKETS[range_name]
    cutoff = await _rollup_cutoff(db, monitor_id)
    params = {"m": monitor_id, "since": since, "bucket": bucket}
    # Rollups for the older part (only matters beyond the raw retention window).
    sql = """
        WITH raw AS (
            SELECT date_bin(:bucket, checked_at, TIMESTAMPTZ '2000-01-01') AS bucket,
                   count(*) AS total, count(*) FILTER (WHERE is_up) AS up,
                   avg(response_ms) AS ms_sum_avg, count(response_ms) AS ms_n
            FROM check_results
            WHERE monitor_id = :m AND checked_at >= :raw_since
            GROUP BY 1
        ), rolled AS (
            SELECT date_bin(:bucket, bucket_start, TIMESTAMPTZ '2000-01-01') AS bucket,
                   sum(checks_total) AS total, sum(checks_up) AS up,
                   sum(response_ms_avg::float8 * checks_total) / nullif(sum(checks_total), 0)
                       AS ms_sum_avg,
                   sum(checks_total) AS ms_n
            FROM check_rollups
            WHERE monitor_id = :m AND bucket_start >= :since AND bucket_start < :raw_since
            GROUP BY 1
        ), combined AS (SELECT * FROM raw UNION ALL SELECT * FROM rolled)
        SELECT bucket, sum(total) AS total, sum(up) AS up,
               sum(ms_sum_avg * ms_n) / nullif(sum(ms_n), 0) AS avg_ms
        FROM combined GROUP BY bucket ORDER BY bucket
    """
    # Use rollups only where raw data has already been purged.
    raw_since = since
    if cutoff and cutoff > since:
        oldest_raw = await db.scalar(
            text("SELECT min(checked_at) FROM check_results WHERE monitor_id = :m"),
            {"m": monitor_id},
        )
        if oldest_raw is None or oldest_raw > since:
            raw_since = min(cutoff, oldest_raw) if oldest_raw else cutoff
    params["raw_since"] = raw_since
    rows = await db.execute(text(sql), params)
    return [
        {
            "t": r.bucket.isoformat(),
            "checks": int(r.total),
            "uptime": round(100.0 * int(r.up) / int(r.total), 3) if r.total else None,
            "avg_ms": round(float(r.avg_ms)) if r.avg_ms is not None else None,
        }
        for r in rows
    ]
