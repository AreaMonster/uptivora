"""Query timings at scale (Phase 9). Run after loadtest.py on the same throw-away database.

Fills check_results with one day of synthetic 60-second history for every monitor
(10,000 monitors -> 14.4 million rows), builds the hourly rollups, then times the queries the
dashboard, monitor page, admin overview, scheduler and housekeeping run.

  python bench/queryplans.py [--hours 24] [--skip-seed]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid

from sqlalchemy import text

from app.admin import overview
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.engine import housekeeping as hk
from app.engine.scheduler import _CLAIM_SQL
from app.monitors import stats


async def seed(hours: int) -> None:
    maker = get_sessionmaker()
    async with maker() as db:
        await db.execute(text("TRUNCATE check_results, check_rollups"))
        await db.commit()
        n = await db.scalar(text("SELECT count(*) FROM monitors"))
        t = time.monotonic()
        # One hour per statement keeps transactions and WAL bursts moderate.
        for h in range(hours):
            await db.execute(
                text(
                    """
                    INSERT INTO check_results (monitor_seq, checked_at, is_up, status_code,
                                               response_ms)
                    SELECT m.seq,
                           now() - make_interval(hours => :h) - g * interval '60 seconds'
                               - random() * interval '50 seconds',
                           random() > 0.003, 200, (80 + random() * 300)::int
                      FROM monitors m, generate_series(0, 59) g
                    """
                ),
                {"h": h},
            )
            await db.commit()
        await db.execute(text("ANALYZE check_results"))
        await db.commit()
        print(f"seeded {n} monitors x {hours} h in {time.monotonic() - t:.0f}s", flush=True)


def text_now_hour():
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(minute=0, second=0, microsecond=0)


async def db_index(sql: str, maker) -> None:
    async with maker() as db:
        await db.execute(text(sql))
        await db.execute(text("ANALYZE check_rollups"))
        await db.commit()


async def timed(label: str, coro_factory, results: dict, repeat: int = 3) -> None:
    best = None
    for _ in range(repeat):
        t = time.perf_counter()
        await coro_factory()
        ms = (time.perf_counter() - t) * 1000
        best = ms if best is None else min(best, ms)
    results[label] = round(best, 1)
    print(f"{label:<48} {best:9.1f} ms", flush=True)


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--skip-seed", action="store_true")
    args = p.parse_args()
    settings = get_settings()
    maker = get_sessionmaker()
    if not args.skip_seed:
        await seed(args.hours)

    results: dict = {}
    t = time.monotonic()
    async with maker() as db, db.begin():
        since = await db.scalar(text(f"SELECT now() - interval '{args.hours + 1} hours'"))
        await db.execute(hk._ROLLUP_SQL, {"since": since, "until": text_now_hour()})
    results["initial_rollup_all_hours_s"] = round(time.monotonic() - t, 1)
    print(f"initial rollup of all hours: {results['initial_rollup_all_hours_s']} s", flush=True)
    async with maker() as db:
        await db.execute(text("ANALYZE check_rollups"))
        await db.commit()
        ids = list((await db.scalars(text("SELECT seq FROM monitors ORDER BY seq LIMIT 50"))).all())
        one = ids[0]
        sizes = (
            await db.execute(
                text(
                    "SELECT (SELECT sum(pg_total_relation_size(inhrelid)) FROM pg_inherits"
                    " WHERE inhparent = 'check_results'::regclass) AS raw,"
                    " pg_total_relation_size('check_rollups') AS rolled,"
                    " (SELECT count(*) FROM check_results) AS raw_rows,"
                    " (SELECT count(*) FROM check_rollups) AS rolled_rows"
                )
            )
        ).one()
    results["sizes"] = dict(sizes._mapping)
    print(json.dumps(results["sizes"], default=str), flush=True)

    async def q_dashboard():
        async with maker() as db:
            await stats.uptime_24h_bulk(db, ids)

    async def q_monitor_summary():
        async with maker() as db:
            await stats.uptime_summary(db, one)

    async def q_series(rng):
        async def run():
            async with maker() as db:
                await stats.series(db, one, rng)

        return run

    async def q_admin_overview():
        async with maker() as db:
            await overview.overview(db, settings)

    async def q_claim():
        async with maker() as db, db.begin():
            await db.execute(
                _CLAIM_SQL, {"worker": "plan-" + uuid.uuid4().hex[:6], "lease": 1, "limit": 100}
            )
            await db.rollback()

    async def q_rollup_tick():
        async with maker() as db, db.begin():
            since = await db.scalar(
                text("SELECT max(bucket_start) - interval '2 hours' FROM check_rollups")
            )
            await db.execute(hk._ROLLUP_SQL, {"since": since, "until": text_now_hour()})

    async def q_overview_before():  # the Phase 8 queries: two scans of 24 h raw results
        async with maker() as db:
            await db.execute(
                text(
                    "SELECT count(*) FILTER (WHERE checked_at > now() - interval '1 hour'),"
                    " count(*) FILTER (WHERE checked_at > now() - interval '1 hour'"
                    " AND NOT is_up), count(*) FROM check_results"
                    " WHERE checked_at > now() - interval '24 hours'"
                )
            )
            await db.execute(
                text(
                    "SELECT date_trunc('hour', checked_at), count(*),"
                    " count(*) FILTER (WHERE NOT is_up) FROM check_results"
                    " WHERE checked_at > now() - interval '24 hours' GROUP BY 1 ORDER BY 1"
                )
            )

    async def q_max_bucket():
        async with maker() as db:
            await db.execute(text("SELECT max(bucket_start) FROM check_rollups"))

    async def q_purge_plan():
        async with maker() as db:
            plan = (
                (
                    await db.execute(
                        text(
                            "EXPLAIN SELECT ctid FROM check_rollups"
                            " WHERE bucket_start < now() - interval '400 days' LIMIT 5000"
                        )
                    )
                )
                .scalars()
                .all()
            )
            return " / ".join(plan)

    await db_index("DROP INDEX IF EXISTS ix_check_rollups_bucket_start", maker)
    await timed("rollup max(bucket_start), no index", q_max_bucket, results)
    results["purge_plan_no_index"] = await q_purge_plan()
    await db_index(
        "CREATE INDEX IF NOT EXISTS ix_check_rollups_bucket_start ON check_rollups (bucket_start)",
        maker,
    )
    await timed("rollup max(bucket_start), with index", q_max_bucket, results)
    results["purge_plan_with_index"] = await q_purge_plan()
    await timed("admin overview, Phase 8 queries", q_overview_before, results)

    await timed("dashboard: uptime 24h for 50 monitors", q_dashboard, results)
    await timed("monitor page: uptime 24h/7d/30d/90d", q_monitor_summary, results)
    for rng in ("24h", "7d", "30d", "90d"):
        await timed(f"monitor page: chart {rng}", await q_series(rng), results)
    await timed("admin overview, Phase 9 (all queries)", q_admin_overview, results)
    await timed("scheduler claim of 100 due monitors", q_claim, results)
    await timed("rollup job tick (last 2-3 h)", q_rollup_tick, results, repeat=1)
    print("RESULT " + json.dumps(results, default=str), flush=True)
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
