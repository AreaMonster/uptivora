"""Customer monitor management. Every query is scoped to the current user (404 otherwise)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Query, Request, Response, status
from sqlalchemy import func, select

from app.auth.deps import DB, AppSettings, CurrentUser
from app.core import netguard, ratelimit
from app.core.audit import audit
from app.core.errors import AppError, LimitExceeded, NotFound
from app.core.requestctx import client_ip
from app.limits import Limits, limits_for, lock_usage_scope, monitor_usage
from app.models import HttpMethod, Incident, Monitor, MonitorStatus, PausedReason
from app.monitors import stats
from app.monitors.schemas import IncidentOut, MonitorCreate, MonitorOut, MonitorUpdate

router = APIRouter(prefix="/api/monitors", tags=["monitors"])

# Total (active + paused) monitors one account may keep, independent of plan.
HARD_CAP_FACTOR, HARD_CAP_MIN = 2, 20


async def validate_target(url: str) -> str:
    """Policy + DNS validation. Raises a field error the UI can display next to the URL."""
    try:
        safe = netguard.validate_monitor_url(url)
        await netguard.resolve_public_addresses(safe.host, safe.port)
    except netguard.UnsafeURLError as exc:
        raise AppError(
            exc.message, code=exc.code, status_code=422, fields={"url": exc.message}
        ) from exc
    return safe.url


def _check_interval(interval: int, limits: Limits) -> None:
    if interval < limits.min_interval_seconds:
        msg = f"Your plan allows checks every {limits.min_interval_seconds} seconds at most."
        raise LimitExceeded(msg, fields={"interval_seconds": msg})


async def _ensure_capacity(db, user, limits: Limits) -> None:
    if limits.max_monitors is None:
        return
    if await monitor_usage(db, user, limits) >= limits.max_monitors:
        if limits.source == "no_plan":
            raise LimitExceeded("Choose a plan to start monitoring websites.", code="no_plan")
        raise LimitExceeded(
            f"You have reached the limit of {limits.max_monitors} active monitors. "
            "Upgrade your plan or pause another monitor."
        )


async def _get_owned(db, ctx, monitor_id: uuid.UUID, *, lock: bool = False) -> Monitor:
    stmt = select(Monitor).where(Monitor.id == monitor_id, Monitor.owner_id == ctx.user.id)
    if lock:
        stmt = stmt.with_for_update()
    monitor = await db.scalar(stmt)
    if monitor is None:
        raise NotFound("Monitor not found.")
    return monitor


def _out(monitor: Monitor, uptime: float | None = None) -> MonitorOut:
    out = MonitorOut.model_validate(monitor)
    out.uptime_24h = uptime
    return out


@router.get("")
async def list_monitors(ctx: CurrentUser, db: DB) -> list[MonitorOut]:
    monitors = (
        await db.scalars(
            select(Monitor).where(Monitor.owner_id == ctx.user.id).order_by(Monitor.name)
        )
    ).all()
    uptimes = await stats.uptime_24h_bulk(db, [m.id for m in monitors])
    return [_out(m, uptimes.get(m.id)) for m in monitors]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_monitor(
    body: MonitorCreate, ctx: CurrentUser, request: Request, db: DB, settings: AppSettings
) -> MonitorOut:
    await ratelimit.hit("monitor-create", str(ctx.user.id), limit=30, window_seconds=3600)
    url = await validate_target(body.url)
    limits = await limits_for(db, settings, ctx.user)
    _check_interval(body.interval_seconds, limits)
    await lock_usage_scope(db, ctx.user, limits)
    await _ensure_capacity(db, ctx.user, limits)
    if limits.max_monitors is not None:
        total = await db.scalar(
            select(func.count()).select_from(Monitor).where(Monitor.owner_id == ctx.user.id)
        )
        if total >= max(limits.max_monitors * HARD_CAP_FACTOR, HARD_CAP_MIN):
            raise LimitExceeded("Delete some paused monitors before adding new ones.")

    monitor = Monitor(
        owner_id=ctx.user.id,
        **body.model_dump(exclude={"url"}),
        url=url,
        next_check_at=datetime.now(UTC),
    )
    db.add(monitor)
    await db.flush()
    audit(
        db,
        "monitor.create",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="monitor",
        target_id=monitor.id,
        url=url,
    )
    await db.commit()
    await db.refresh(monitor)
    return _out(monitor)


@router.get("/{monitor_id}")
async def get_monitor(monitor_id: uuid.UUID, ctx: CurrentUser, db: DB) -> dict:
    monitor = await _get_owned(db, ctx, monitor_id)
    summary = await stats.uptime_summary(db, monitor.id)
    return {"monitor": _out(monitor, summary["24h"]), "uptime": summary}


@router.patch("/{monitor_id}")
async def update_monitor(
    monitor_id: uuid.UUID,
    body: MonitorUpdate,
    ctx: CurrentUser,
    request: Request,
    db: DB,
    settings: AppSettings,
) -> MonitorOut:
    monitor = await _get_owned(db, ctx, monitor_id, lock=True)
    changes = body.model_dump(exclude_unset=True)
    for key in (
        "name",
        "url",
        "interval_seconds",
        "method",
        "timeout_seconds",
        "expected_status",
        "down_threshold",
        "recovery_threshold",
        "ssl_warning_days",
        "follow_redirects",
        "verify_tls",
        "ssl_check_enabled",
        "notifications_enabled",
    ):
        if key in changes and changes[key] is None:
            raise AppError(f"{key} cannot be null", status_code=422, fields={key: "Required"})

    if "url" in changes:
        changes["url"] = await validate_target(changes["url"])
    if "keyword" in changes:
        changes["keyword"] = (changes["keyword"] or "").strip() or None
    if "interval_seconds" in changes:
        _check_interval(changes["interval_seconds"], await limits_for(db, settings, ctx.user))

    interval = changes.get("interval_seconds", monitor.interval_seconds)
    timeout = changes.get("timeout_seconds", monitor.timeout_seconds)
    method = changes.get("method", monitor.method)
    keyword = changes.get("keyword", monitor.keyword)
    if timeout >= interval:
        raise AppError(
            "Timeout must be shorter than the check interval",
            status_code=422,
            fields={"timeout_seconds": "Must be shorter than the interval"},
        )
    if keyword and method == HttpMethod.HEAD:
        raise AppError(
            "Keyword checks need the GET method",
            status_code=422,
            fields={"keyword": "Requires GET"},
        )

    url_changed = "url" in changes and changes["url"] != monitor.url
    for key, value in changes.items():
        setattr(monitor, key, value)
    if url_changed:  # different target: start from a clean state
        monitor.status = MonitorStatus.PAUSED if monitor.is_paused else MonitorStatus.PENDING
        monitor.consecutive_failures = monitor.consecutive_successes = 0
        monitor.ssl_expires_at = monitor.ssl_issuer = monitor.ssl_error = None
        monitor.last_error = None
    if url_changed or "interval_seconds" in changes:
        monitor.next_check_at = datetime.now(UTC)
    audit(
        db,
        "monitor.update",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="monitor",
        target_id=monitor.id,
        fields=sorted(changes),
    )
    await db.commit()
    await db.refresh(monitor)
    return _out(monitor)


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(
    monitor_id: uuid.UUID, ctx: CurrentUser, request: Request, db: DB
) -> Response:
    monitor = await _get_owned(db, ctx, monitor_id)
    audit(
        db,
        "monitor.delete",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="monitor",
        target_id=monitor.id,
        url=monitor.url,
    )
    await db.delete(monitor)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{monitor_id}/pause")
async def pause_monitor(monitor_id: uuid.UUID, ctx: CurrentUser, db: DB) -> MonitorOut:
    monitor = await _get_owned(db, ctx, monitor_id, lock=True)
    if not monitor.is_paused:
        monitor.is_paused = True
        monitor.paused_reason = PausedReason.USER
        monitor.status = MonitorStatus.PAUSED
        monitor.lease_owner = monitor.lease_until = None
    await db.commit()
    await db.refresh(monitor)
    return _out(monitor)


@router.post("/{monitor_id}/resume")
async def resume_monitor(
    monitor_id: uuid.UUID, ctx: CurrentUser, db: DB, settings: AppSettings
) -> MonitorOut:
    monitor = await _get_owned(db, ctx, monitor_id, lock=True)
    if monitor.is_paused:
        if monitor.paused_reason == PausedReason.ADMIN:
            raise AppError(
                "This monitor was paused by an administrator.", code="admin_paused", status_code=403
            )
        limits = await limits_for(db, settings, ctx.user)
        await lock_usage_scope(db, ctx.user, limits)
        await _ensure_capacity(db, ctx.user, limits)
        if monitor.interval_seconds < limits.min_interval_seconds:
            monitor.interval_seconds = limits.min_interval_seconds
        monitor.is_paused = False
        monitor.paused_reason = None
        monitor.status = MonitorStatus.PENDING
        monitor.consecutive_failures = monitor.consecutive_successes = 0
        monitor.next_check_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(monitor)
    return _out(monitor)


@router.get("/{monitor_id}/series")
async def monitor_series(
    monitor_id: uuid.UUID,
    ctx: CurrentUser,
    db: DB,
    range: Literal["24h", "7d", "30d", "90d"] = Query("24h"),  # noqa: A002
) -> dict:
    monitor = await _get_owned(db, ctx, monitor_id)
    return {"range": range, "points": await stats.series(db, monitor.id, range)}


@router.get("/{monitor_id}/checks")
async def recent_checks(
    monitor_id: uuid.UUID, ctx: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=200)
) -> list[dict]:
    monitor = await _get_owned(db, ctx, monitor_id)
    from app.models import CheckResult

    rows = (
        await db.scalars(
            select(CheckResult)
            .where(CheckResult.monitor_id == monitor.id)
            .order_by(CheckResult.checked_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "checked_at": r.checked_at.isoformat(),
            "is_up": r.is_up,
            "status_code": r.status_code,
            "response_ms": r.response_ms,
            "error_kind": r.error_kind,
            "error": r.error_message,
        }
        for r in rows
    ]


@router.get("/{monitor_id}/incidents")
async def monitor_incidents(
    monitor_id: uuid.UUID, ctx: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=200)
) -> list[IncidentOut]:
    monitor = await _get_owned(db, ctx, monitor_id)
    rows = (
        await db.scalars(
            select(Incident)
            .where(Incident.monitor_id == monitor.id)
            .order_by(Incident.started_at.desc())
            .limit(limit)
        )
    ).all()
    return [incident_out(i) for i in rows]


def incident_out(incident: Incident) -> IncidentOut:
    out = IncidentOut.model_validate(incident)
    end = incident.resolved_at or datetime.now(UTC)
    out.duration_seconds = int((end - incident.started_at).total_seconds())
    return out
