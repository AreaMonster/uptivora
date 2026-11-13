"""Admin: KPIs and system health."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import sys
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.auth.deps import DB, AppSettings, require_admin
from app.selfhosted.licence import licence_status

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

PROCESS_STARTED = time.time()  # imported with the API at startup
WORKER_STALE_SECONDS = 60
OVERDUE_SECONDS = 60


async def _one(db, sql: str, **params):
    return (await db.execute(text(sql), params)).one()


@router.get("/overview")
async def overview(db: DB, settings: AppSettings) -> dict:
    users = await _one(
        db,
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE created_at > now() - interval '7 days') AS new_7d,
               count(*) FILTER (WHERE last_login_at > now() - interval '30 days') AS active_30d,
               count(*) FILTER (WHERE NOT is_active) AS suspended,
               count(*) FILTER (WHERE role = 'admin') AS admins
          FROM users""",
    )
    monitors = await _one(
        db,
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE NOT is_paused) AS active,
               count(*) FILTER (WHERE is_paused) AS paused,
               count(*) FILTER (WHERE status = 'down' AND NOT is_paused) AS down,
               count(*) FILTER (WHERE paused_reason = 'admin') AS admin_paused
          FROM monitors""",
    )
    # The last hour is counted from raw results (index range scan on checked_at). Older hours
    # come from the hourly rollups below, so the page stays fast with millions of results.
    checks = await _one(
        db,
        """
        SELECT count(*) AS last_hour, count(*) FILTER (WHERE NOT is_up) AS failed_last_hour
          FROM check_results WHERE checked_at > now() - interval '1 hour'""",
    )
    incidents = await _one(
        db,
        """
        SELECT count(*) FILTER (WHERE resolved_at IS NULL) AS open,
               count(*) FILTER (WHERE started_at > now() - interval '24 hours') AS last_24h
          FROM incidents""",
    )
    outbox = await _one(
        db,
        """
        SELECT count(*) FILTER (WHERE status IN ('pending', 'sending')) AS queued,
               count(*) FILTER (WHERE status = 'failed'
                                  AND created_at > now() - interval '7 days') AS failed_7d,
               count(*) FILTER (WHERE status = 'sent'
                                  AND sent_at > now() - interval '24 hours') AS sent_24h
          FROM notification_outbox""",
    )
    series = (
        await db.execute(
            text("""
        WITH cut AS (
            SELECT coalesce(max(bucket_start) + interval '1 hour',
                            date_trunc('hour', now() - interval '24 hours')) AS t
              FROM check_rollups WHERE bucket_start >= now() - interval '26 hours'
        ), parts AS (
            SELECT bucket_start AS hour, checks_total AS total,
                   checks_total - checks_up AS failed
              FROM check_rollups, cut
             WHERE bucket_start >= date_trunc('hour', now() - interval '24 hours')
               AND bucket_start < cut.t
            UNION ALL
            SELECT date_trunc('hour', checked_at), count(*), count(*) FILTER (WHERE NOT is_up)
              FROM check_results, cut
             WHERE checked_at >= greatest(cut.t, now() - interval '24 hours')
             GROUP BY 1
        )
        SELECT hour, sum(total)::bigint AS total, sum(failed)::bigint AS failed
          FROM parts GROUP BY hour ORDER BY hour""")
        )
    ).all()

    result: dict = {
        "edition": settings.edition,
        "environment": settings.env,
        "billing_test_mode": settings.billing_test_mode,
        "users": dict(users._mapping),
        "monitors": dict(monitors._mapping),
        "checks": {
            **dict(checks._mapping),
            "last_24h": sum(r.total for r in series),
            "per_minute": round(checks.last_hour / 60, 1),
        },
        "incidents": dict(incidents._mapping),
        "emails": dict(outbox._mapping),
        "checks_by_hour": [
            {"t": r.hour.isoformat(), "total": r.total, "failed": r.failed} for r in series
        ],
    }
    if settings.is_hosted:
        subs = (
            await db.execute(
                text("""
            SELECT s.status, s.is_test, count(*) AS n, coalesce(sum(p.price_cents), 0) AS cents,
                   max(p.currency) AS currency
              FROM subscriptions s JOIN plans p ON p.id = s.plan_id
             GROUP BY s.status, s.is_test""")
            )
        ).all()
        by_status: dict[str, int] = {}
        mrr = {"real_cents": 0, "test_cents": 0, "currency": "CHF"}
        for r in subs:
            by_status[r.status] = by_status.get(r.status, 0) + r.n
            if r.status in ("active", "past_due"):
                mrr["test_cents" if r.is_test else "real_cents"] += int(r.cents)
                mrr["currency"] = r.currency or "CHF"
        result["subscriptions"] = {
            "active": by_status.get("active", 0),
            "past_due": by_status.get("past_due", 0),
            "cancelled": by_status.get("cancelled", 0),
            "expired": by_status.get("expired", 0),
            "mrr": mrr,
        }
    else:
        status = await licence_status(db, settings)
        lic = status.licence
        result["licence"] = {
            "installed": lic is not None,
            "edition": lic.edition.value if lic else None,
            "licensee": lic.licensee_name if lic else None,
            "license_id": lic.license_id if lic else None,
            "limits": lic.limits.to_dict() if lic else None,
            "error": status.error,
            "source": status.source,
        }
    return result


@router.get("/health")
async def health(db: DB, settings: AppSettings) -> dict:
    started = time.perf_counter()
    await db.execute(text("SELECT 1"))
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    database = await _one(
        db,
        """
        SELECT version() AS version,
               pg_database_size(current_database()) AS size_bytes,
               (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database())
                   AS connections,
               (SELECT setting::int FROM pg_settings WHERE name = 'max_connections')
                   AS max_connections""",
    )
    tables = (
        await db.execute(
            text("""
        SELECT relname AS name, n_live_tup AS rows,
               pg_total_relation_size(relid) AS bytes
          FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 8""")
        )
    ).all()
    workers = (
        await db.execute(
            text("""
        SELECT worker_id, hostname, pid, version, started_at, last_seen_at, checks_total,
               checks_failed, in_flight,
               extract(epoch FROM now() - last_seen_at) AS seen_ago
          FROM worker_heartbeats ORDER BY last_seen_at DESC""")
        )
    ).all()
    lag = await _one(
        db,
        """
        SELECT count(*) AS overdue,
               coalesce(extract(epoch FROM now() - min(next_check_at)), 0) AS max_delay
          FROM monitors
         WHERE NOT is_paused AND next_check_at < now() - make_interval(secs => :s)""",
        s=OVERDUE_SECONDS,
    )
    outbox = await _one(
        db,
        """
        SELECT count(*) AS queued,
               coalesce(extract(epoch FROM now() - min(created_at)), 0) AS oldest_seconds
          FROM notification_outbox WHERE status IN ('pending', 'sending')""",
    )

    live_workers = [w for w in workers if w.seen_ago < WORKER_STALE_SECONDS]
    try:
        disk = shutil.disk_usage(os.getcwd())
        disk_info = {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free}
    except OSError:
        disk_info = None
    try:
        load = list(os.getloadavg())  # not available on Windows
    except (AttributeError, OSError):
        load = None

    issues: list[str] = []
    if not live_workers:
        issues.append(
            "No monitoring worker has reported in the last minute — checks are not running."
        )
    if lag.overdue:
        issues.append(f"{lag.overdue} monitors are overdue (oldest {int(lag.max_delay)} s).")
    if outbox.queued and outbox.oldest_seconds > 600:
        issues.append(
            f"{outbox.queued} emails are waiting (oldest {int(outbox.oldest_seconds)} s) "
            "— check the SMTP settings."
        )
    if not settings.smtp_host:
        issues.append("SMTP is not configured; alert emails cannot be sent.")

    return {
        "status": "ok" if not issues else "degraded",
        "issues": issues,
        "app": {
            "version": settings.version,
            "edition": settings.edition,
            "environment": settings.env,
            "python": sys.version.split()[0],
            "platform": platform.platform(terse=True),
            "hostname": socket.gethostname(),
            "api_uptime_seconds": int(time.time() - PROCESS_STARTED),
            "now": datetime.now(UTC).isoformat(),
        },
        "server": {"disk": disk_info, "load_average": load, "cpu_count": os.cpu_count()},
        "database": {
            "ok": True,
            "latency_ms": latency_ms,
            "version": database.version.split(",")[0],
            "size_bytes": database.size_bytes,
            "connections": database.connections,
            "max_connections": database.max_connections,
            "largest_tables": [dict(t._mapping) for t in tables],
        },
        "workers": [
            {
                "worker_id": w.worker_id,
                "hostname": w.hostname,
                "pid": w.pid,
                "version": w.version,
                "started_at": w.started_at.isoformat(),
                "last_seen_at": w.last_seen_at.isoformat(),
                "checks_total": w.checks_total,
                "checks_failed": w.checks_failed,
                "in_flight": w.in_flight,
                "alive": w.seen_ago < WORKER_STALE_SECONDS,
            }
            for w in workers
        ],
        "scheduler": {"overdue_monitors": lag.overdue, "max_delay_seconds": int(lag.max_delay)},
        "email": {
            "queued": outbox.queued,
            "oldest_seconds": int(outbox.oldest_seconds),
            "smtp_configured": bool(settings.smtp_host),
            "smtp_host": settings.smtp_host or None,
        },
    }
