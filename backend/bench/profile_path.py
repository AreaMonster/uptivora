"""Profile one worker's hot path (claim -> check -> apply) sequentially, without concurrency.

  python bench/profile_path.py --target-ip 10.0.0.5 [--n 300]
Needs monitors created by loadtest.py in the same database.
"""

import argparse
import asyncio
import cProfile
import ipaddress
import pstats
import time

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.engine.netclient import build_clients
from app.engine.scheduler import Scheduler


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--target-ip", required=True)
    p.add_argument("--n", type=int, default=300)
    args = p.parse_args()
    target = ipaddress.ip_address(args.target_ip)

    async def resolver(host, port):
        return [target]

    maker = get_sessionmaker()
    async with maker() as db:
        await db.execute(text("UPDATE monitors SET next_check_at = now(), lease_until = NULL"))
        await db.commit()
    clients = build_clients(resolver=resolver)
    s = Scheduler(maker, get_settings(), clients, worker_id="profile", concurrency=1)
    times = {"claim": 0.0, "process": 0.0}
    prof = cProfile.Profile()
    prof.enable()
    for _ in range(args.n):
        t = time.perf_counter()
        claims = await s.claim(1)
        times["claim"] += time.perf_counter() - t
        t = time.perf_counter()
        await s.process(claims[0])
        times["process"] += time.perf_counter() - t
    prof.disable()
    await clients.aclose()
    for k, v in times.items():
        print(f"{k:<8} {v / args.n * 1000:6.2f} ms per check (sequential)")
    pstats.Stats(prof).sort_stats("tottime").print_stats(30)


asyncio.run(main())
