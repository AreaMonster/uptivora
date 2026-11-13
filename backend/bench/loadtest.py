"""Monitoring engine load test (Phase 9). Not part of the application or its image.

Runs the real Scheduler (claim -> HTTP check -> apply_outcome) against N monitors on a
dedicated database. Every monitor gets its own host name; a test-only resolver maps all of
them to one local HTTP target, so nothing leaves the test network and the per-host
concurrency limit behaves as it does with real customers. See docs/PERFORMANCE.md.

  python bench/loadtest.py --monitors 10000 --interval 60 --duration 600 --target-ip 10.0.0.5

Environment: UPTIVORA_DATABASE_URL must point at a throw-away database (it is modified).
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
import random
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.auth.service import create_user
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.engine import scheduler as scheduler_module
from app.engine.checker import run_check
from app.engine.netclient import build_clients
from app.engine.scheduler import Scheduler
from app.models import UserRole

BENCH_EMAIL = "loadtest@bench.uptivora.invalid"


async def setup(n: int, interval: int, port: int) -> None:
    maker = get_sessionmaker()
    async with maker() as db:
        owner = await db.scalar(text("SELECT id FROM users WHERE email = :e"), {"e": BENCH_EMAIL})
        if owner is None:
            user = await create_user(
                db, email=BENCH_EMAIL, password=uuid.uuid4().hex + "Aa1!", role=UserRole.ADMIN
            )
            await db.commit()
            owner = user.id
        await db.execute(text("DELETE FROM monitors WHERE owner_id = :o"), {"o": owner})
        await db.execute(text("TRUNCATE check_results, check_rollups, incidents CASCADE"))
        await db.commit()
        now = datetime.now(UTC)
        rows = [
            {
                "id": uuid.uuid4(),
                "o": owner,
                "name": f"Bench {i}",
                "url": f"http://m{i}.loadtest-target.net:{port}/",
                "iv": interval,
                # first checks spread evenly over one interval, as on a long-running system
                "due": now + timedelta(seconds=random.uniform(0, interval)),  # noqa: S311
            }
            for i in range(n)
        ]
        for start in range(0, n, 1000):
            await db.execute(
                text(
                    "INSERT INTO monitors (id, owner_id, name, url, method, interval_seconds,"
                    " timeout_seconds, expected_status, follow_redirects, verify_tls,"
                    " down_threshold, recovery_threshold, notifications_enabled,"
                    " ssl_check_enabled, ssl_warning_days, is_paused, status,"
                    " consecutive_failures, consecutive_successes, next_check_at,"
                    " created_at, updated_at)"
                    " VALUES (:id, :o, :name, :url, 'GET', :iv, 10, '200-399', true, true,"
                    " 2, 1, false, false, 14, false, 'pending', 0, 0, :due, now(), now())"
                ),
                rows[start : start + 1000],
            )
        await db.commit()
        await db.execute(text("ANALYZE monitors"))
        await db.commit()
    print(f"setup: {n} monitors, interval {interval}s", flush=True)


async def sample(maker) -> dict:
    async with maker() as db:
        row = (
            await db.execute(
                text(
                    "SELECT count(*) FILTER (WHERE next_check_at < now() - interval '5 seconds')"
                    " AS late, COALESCE(EXTRACT(EPOCH FROM now() - min(next_check_at)), 0)"
                    " AS max_late FROM monitors WHERE is_paused = false"
                )
            )
        ).one()
    return {"late": row.late, "max_late": max(0.0, float(row.max_late))}


async def run(args) -> dict:
    settings = get_settings()
    maker = get_sessionmaker()
    target = ipaddress.ip_address(args.target_ip)

    async def resolver(host: str, port: int):  # test-only: every bench host is the target
        if host.endswith(".loadtest-target.net"):
            return [target]
        raise RuntimeError(f"unexpected host {host}")

    # Phase timings: claim (DB), check (HTTP), apply (DB write of the result).
    phases: dict[str, list[float]] = {"claim": [], "check": [], "apply": []}
    real_apply = scheduler_module.apply_outcome

    async def timed_apply(*a, **kw):
        t = time.perf_counter()
        try:
            return await real_apply(*a, **kw)
        finally:
            phases["apply"].append(time.perf_counter() - t)

    async def timed_check(*a, **kw):
        t = time.perf_counter()
        try:
            return await run_check(*a, **kw)
        finally:
            phases["check"].append(time.perf_counter() - t)

    scheduler_module.apply_outcome = timed_apply
    clients = build_clients(resolver=resolver, max_connections=args.concurrency * 2)
    scheduler = Scheduler(
        maker,
        settings,
        clients,
        worker_id="bench-1",
        concurrency=args.concurrency,
        batch_size=args.batch,
        poll_interval=args.poll,
        checker=timed_check,
    )
    real_claim = scheduler.claim

    async def timed_claim(limit):
        t = time.perf_counter()
        try:
            return await real_claim(limit)
        finally:
            phases["claim"].append(time.perf_counter() - t)

    scheduler.claim = timed_claim
    stop = asyncio.Event()
    task = asyncio.create_task(scheduler.run(stop))

    samples = []
    t0, cpu0, checks0 = time.monotonic(), time.process_time(), 0
    warmup = args.interval  # ignore the first interval (everything starts "pending")
    while time.monotonic() - t0 < args.duration:
        await asyncio.sleep(10)
        s = await sample(maker)
        now, cpu = time.monotonic(), time.process_time()
        done = scheduler.stats.checks_total
        s.update(
            t=round(now - t0),
            checks_per_s=round((done - checks0) / 10, 1),
            worker_cpu=round((cpu - cpu0) / 10 * 100),
            in_flight=scheduler.stats.in_flight,
        )
        checks0, cpu0 = done, cpu
        for name, values in phases.items():
            if values:
                values.sort()
                s[f"{name}_p50_ms"] = round(values[len(values) // 2] * 1000, 1)
                s[f"{name}_p95_ms"] = round(values[int(len(values) * 0.95)] * 1000, 1)
            values.clear()
        samples.append(s)
        print(json.dumps(s), flush=True)
    stop.set()
    await task
    await clients.aclose()

    steady = [s for s in samples if s["t"] > warmup] or samples
    async with maker() as db:
        size = (
            await db.execute(
                text(
                    "SELECT count(*) AS n, pg_total_relation_size('check_results') AS bytes,"
                    " pg_relation_size('check_results') AS heap FROM check_results"
                )
            )
        ).one()
    required = args.monitors / args.interval
    return {
        "monitors": args.monitors,
        "interval_s": args.interval,
        "required_checks_per_s": round(required, 1),
        "achieved_checks_per_s": round(statistics.mean(s["checks_per_s"] for s in steady), 1),
        "worker_cpu_percent_avg": round(statistics.mean(s["worker_cpu"] for s in steady)),
        "late_monitors_max": max(s["late"] for s in steady),
        "max_lateness_s": round(max(s["max_late"] for s in steady), 1),
        "checks_failed": scheduler.stats.checks_failed,
        "check_results_rows": size.n,
        "bytes_per_row_incl_indexes": round(size.bytes / max(size.n, 1)),
        "bytes_per_row_heap": round(size.heap / max(size.n, 1)),
    }


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--monitors", type=int, default=10_000)
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--duration", type=int, default=600)
    p.add_argument("--concurrency", type=int, default=200)
    p.add_argument("--batch", type=int, default=100)
    p.add_argument("--poll", type=float, default=1.0)
    p.add_argument("--target-ip", required=True)
    p.add_argument("--target-port", type=int, default=80)
    p.add_argument("--skip-setup", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if not args.skip_setup:
        await setup(args.monitors, args.interval, args.target_port)
    result = await run(args)
    print("RESULT " + json.dumps(result), flush=True)
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
