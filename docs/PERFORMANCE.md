# Performance and sizing

Measured in Phase 9 (2026-11-13). Tools live in `backend/bench/` (not shipped in images).

## Setup

- Production API image, PostgreSQL 17 (`shared_buffers=512MB`) and the worker pinned
  together to **2 CPU cores** (`--cpuset-cpus 0,1`), simulating a 2-vCPU VPS. An nginx
  container on other cores plays "the internet".
- `bench/loadtest.py` creates N monitors on a throw-away database, spreads their first checks
  over one interval and runs the real `Scheduler` (claim → HTTP check → write result). Every
  monitor has its own host name, mapped to nginx by a test-only resolver, so the per-host
  concurrency limit behaves as with real customers and no traffic leaves the test network.
- Raw environment latency (`bench/latency_probe.py`): DB round trip 0.12 ms, HTTP request with
  a new connection 3.1 ms.

## Monitoring engine: 10,000 monitors every 60 seconds

| | Before fixes | After fixes |
| --- | --- | --- |
| Checks per second needed | 166.7 | 166.7 (≈162 with the 0–3 s jitter) |
| Checks per second achieved | 138.7 | **162.1** |
| Monitors more than 5 s late (max) | 1,802 and growing | **0** |
| Worst lateness | 18.7 s | **1.8 s** |
| Worker CPU (one process) | 54 % of a core | 45 % average, 89 % peak |
| PostgreSQL CPU | 20–30 % | 24 % average, 49 % peak |
| Worker memory | 85 MB | 85 MB |

10-minute run, one worker process, concurrency 200. **Result: 10,000 monitors at 60 s fit on
2 vCPUs using about a third of the CPU.** The hosted compose file runs two worker processes,
which leaves room for API traffic and housekeeping.

### What was wrong, and the fixes

1. **The scheduler slept while work was due.** After a claim that returned fewer rows than
   requested — which also happens when only a few slots are free — the loop slept a full
   poll interval (1 s), then started the next hundred checks at once. That produced idle gaps
   (nothing in flight while 1,800 monitors were overdue) followed by CPU bursts that made every
   operation wait ~250–300 ms. Now the loop claims again immediately when it got everything it
   asked for and, when all slots are busy, continues as soon as one check finishes.
   Regression test: `test_engine_scheduler::test_run_loop_keeps_working_through_a_backlog`.
2. **A failed import on every HTTP request.** httpcore asks `sniffio` which async library is
   running; `sniffio` was not installed (newer anyio no longer depends on it), and Python
   does not cache failed imports, so every request scanned `sys.path`. Profiling showed
   ~380,000 extra function calls per 300 checks (~15 % of the hot path). `sniffio` is now an
   explicit dependency (`test_engine_checker::test_sniffio_is_installed`).

## Database queries with one day of history (14.4 million check results)

| Query | Time |
| --- | --- |
| Dashboard: 24 h uptime for 50 monitors | 64 ms |
| Monitor page: uptime 24 h / 7 d / 30 d / 90 d | 5 ms |
| Monitor page: chart 24 h / 7 d / 30 d / 90 d | 4–6 ms |
| Scheduler: claim 100 due monitors | 2.3 ms |
| Admin overview — Phase 8 version (two scans of 24 h raw results) | **2,755 ms** |
| Admin overview — now (rollups for completed hours, raw for the last hour) | **216 ms** |
| `max(bucket_start)` on rollups (every 10 min) — without / with new index | 18.8 ms / 0.9 ms |
| Rollup job tick (re-aggregates the last 2–3 hours) | 1.7 s every 10 min |
| Inserting history (seed) | ~47,000 rows/s |

Two fixes came out of this:

- **Admin overview** refreshed every 30 s and scanned all raw results of the last 24 hours
  twice. It now reads completed hours from `check_rollups` and counts raw results only after
  the newest rolled-up hour. Test: `test_admin::test_overview_counts_each_check_once_across_rollups`.
- **Missing index on `check_rollups.bucket_start`** (migration `0004`). Without it the rollup
  job's `max(bucket_start)` and the 400-day retention purge scan the whole table — about
  96 million rows for 10,000 monitors after 400 days, i.e. seconds every 10 minutes. With it,
  both use an index scan.

## Storage

Measured: **~214 bytes per stored check** (row + both indexes), **~120 bytes per hourly
rollup**.

Per monitor:

| Interval | Raw results, 30 days | Raw results, 7 days | Rollups, 400 days |
| --- | --- | --- | --- |
| 30 s | 18.5 MB | 4.3 MB | 1.2 MB |
| 60 s | 9.2 MB | 2.2 MB | 1.2 MB |
| 5 min | 1.8 MB | 0.4 MB | 1.2 MB |

**Backups:** a `pg_dump` (custom format, compression 6) is about 6.4× smaller than the
database — measured ~35 bytes per check (1 million rows: 224 MB in the database, 35 MB
dumped). The backup service keeps 14 daily dumps by default, so backups need roughly as much
disk as the database itself.

Whole installations at 60-second checks, default retention (raw 30 days, rollups 400 days,
14 backups):

| Monitors | Database | One backup | Database + 14 backups |
| --- | --- | --- | --- |
| 25 (Starter licence) | ~260 MB | ~40 MB | ~0.8 GB |
| 500 | ~5 GB | ~0.8 GB | ~17 GB |
| 2,000 | ~21 GB | ~3.2 GB | ~66 GB |
| 10,000 | ~104 GB | ~16 GB | ~330 GB |
| 10,000 with `UPTIVORA_RAW_RETENTION_DAYS=7`, `BACKUP_KEEP_DAYS=7` | ~34 GB | ~6 GB | ~76 GB (7 backups) |

At 5-minute intervals divide the raw part by five. Raw results are only needed for the
last day's detail and for the 30-day chart until rollups take over; uptime percentages for
7/30/90 days come from rollups. Large installations can lower `UPTIVORA_RAW_RETENTION_DAYS`
and `BACKUP_KEEP_DAYS` (after copying backups off the server) without losing history.

## Recommended sizing

| Installation | CPU | RAM | Disk |
| --- | --- | --- | --- |
| Self-hosted, up to 500 monitors | 1 vCPU | 1 GB | 25 GB |
| Up to 2,000 monitors | 2 vCPU | 2 GB | 80 GB, or 40 GB with 7-day raw retention and 7 backups |
| Up to 10,000 monitors at 60 s | 2 vCPU | 4 GB | 120 GB with 7-day raw retention and 7 backups (copied off-site) |

Beyond that: more worker processes (they coordinate through PostgreSQL) and table
partitioning of `check_results` by day, so retention becomes dropping a partition instead of
deleting rows. Neither is needed at the sizes above.

## Repeating the measurements

```bash
docker network create uptivora-bench
docker run -d --name bench-db --network uptivora-bench --cpuset-cpus 0,1 \
  -e POSTGRES_USER=uptivora -e POSTGRES_PASSWORD=bench -e POSTGRES_DB=uptivora \
  postgres:17-alpine -c shared_buffers=512MB
docker run -d --name bench-target --network uptivora-bench --cpuset-cpus 2,3 nginx:alpine
# DSN for the commands below (Git Bash: prefix with MSYS_NO_PATHCONV=1)
ENV="-e PYTHONPATH=/app -e UPTIVORA_ENV=test -e UPTIVORA_PUBLIC_URL=http://localhost:3000 \
  -e UPTIVORA_DATABASE_URL=postgresql+asyncpg://uptivora:bench@bench-db:5432/uptivora"
docker run --rm --network uptivora-bench $ENV uptivora/api:dev python -m app.cli migrate
docker run --rm --network uptivora-bench --cpuset-cpus 0,1 -v "$PWD/backend/bench:/bench:ro" \
  $ENV uptivora/api:dev python /bench/loadtest.py --monitors 10000 --duration 600 \
  --target-ip "$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' bench-target)"
docker run --rm --network uptivora-bench --cpuset-cpus 0,1 -v "$PWD/backend/bench:/bench:ro" \
  $ENV uptivora/api:dev python /bench/queryplans.py --hours 24
```
