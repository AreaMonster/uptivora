"""Raw latency of the bench environment: plain DB round trips and plain HTTP requests.

Separates infrastructure latency (Docker networking, VM scheduling) from application cost.
  python bench/latency_probe.py <db-dsn> <http-url>
"""

import asyncio
import statistics
import sys
import time

import asyncpg
import httpx


async def main(dsn: str, url: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = []
    for _ in range(200):
        t = time.perf_counter()
        await conn.fetchval("SELECT 1")
        db.append((time.perf_counter() - t) * 1000)
    await conn.close()

    http = []
    async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=0)) as c:
        for _ in range(200):
            t = time.perf_counter()
            await c.get(url)
            http.append((time.perf_counter() - t) * 1000)

    loop_lag = []
    for _ in range(200):
        t = time.perf_counter()
        await asyncio.sleep(0)
        loop_lag.append((time.perf_counter() - t) * 1000)

    for name, v in (("db SELECT 1", db), ("http GET (new conn)", http), ("loop tick", loop_lag)):
        v.sort()
        p95 = v[int(len(v) * 0.95)]
        print(f"{name:<22} p50 {statistics.median(v):7.2f} ms   p95 {p95:7.2f} ms")


asyncio.run(main(sys.argv[1], sys.argv[2]))
