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

### How checks are stored (since migration 0005)

| Table | Holds | Kept | Measured size |
| --- | --- | --- | --- |
| `check_results`, one partition per UTC day | every check | `UPTIVORA_RAW_RETENTION_DAYS` (3) | **98 bytes** per check (was 214) |
| `retained_checks` | failed checks and the checks around each incident | `UPTIVORA_FAILED_CHECK_RETENTION_DAYS` (30) | same rows, a small fraction |
| `check_rollups` | hourly summary per monitor | `UPTIVORA_ROLLUP_RETENTION_DAYS` (400) | **108 bytes** per hour (was 120) |

What changed and why it is smaller:

- **Leaner rows:** no surrogate id, no worker name per row, and a 4-byte monitor number
  (`monitors.seq`) instead of the 16-byte UUID in the rows and their index.
- **BRIN index on time:** a few kilobytes per day instead of a B-tree with one entry per row.
  It stays precise because each day partition is only ever appended to.
- **Daily partitions:** an expired day is summarised once more, its failed and incident
  checks are copied to `retained_checks`, and the partition is dropped — instant, no
  row-by-row deletes, no table bloat. The worker creates partitions a few days ahead;
  partition maintenance uses a 5 s lock timeout, so a long query delays it instead of
  stalling inserts.
- **3 days of raw checks instead of 30:** every chart beyond 24 hours (7/30/90 days) and all
  uptime percentages beyond 24 hours already come from hourly summaries, so nothing visible
  is lost. Incident timelines keep their checks for 30 days via `retained_checks`.
- **zstd backups:** `pg_dump --compress=zstd:9` — **~10 bytes per check** in a backup, against
  35 with the previous gzip setting. Older gzip dumps still restore.

Measured with the production image: 3.6 million checks (10,000 monitors × 6 h) take 353 MB
including indexes; a zstd dump of them 37 MB; a full dump restored completely. The engine
still keeps up with 10,000 monitors at 60 s (162 checks/s, no late monitors) and the page
queries stay in the low milliseconds.

### Per monitor, after 400 days (rollups are then the largest part)

| Interval | Raw checks (3–4 days) | Rollups | Database | 14 backups | Total |
| --- | --- | --- | --- | --- | --- |
| 30 s | 1.0 MB | 1.0 MB | ~2.0 MB | ~2.5 MB | **~4.5 MB** |
| 60 s | 0.5 MB | 1.0 MB | ~1.6 MB | ~1.9 MB | **~3.5 MB** (was ~33 MB) |
| 5 min | 0.1 MB | 1.0 MB | ~1.2 MB | ~1.3 MB | **~2.5 MB** |

### Whole installations, 60-second checks, default settings

| Monitors | Database | One backup | Database + 14 backups | Before (Phase 9) |
| --- | --- | --- | --- | --- |
| 25 (Starter licence) | ~40 MB | ~3 MB | ~0.1 GB | ~0.8 GB |
| 500 | ~0.8 GB | ~65 MB | ~1.7 GB | ~17 GB |
| 2,000 | ~3.2 GB | ~0.26 GB | ~7 GB | ~66 GB |
| 10,000 | ~16 GB | ~1.3 GB | ~34 GB | ~330 GB |

Overall about **90 % less disk** than before.

## Recommended sizing

| Installation | CPU | RAM | Disk |
| --- | --- | --- | --- |
| Self-hosted, up to 500 monitors | 1 vCPU | 1 GB | 10 GB |
| Up to 2,000 monitors | 2 vCPU | 2 GB | 20 GB |
| Up to 10,000 monitors at 60 s | 2 vCPU | 4 GB | 60 GB |

Beyond that: more worker processes (they coordinate through PostgreSQL). Disk headroom for
WAL and for one restore test is included above.

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
