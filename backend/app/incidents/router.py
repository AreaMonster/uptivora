"""Incident history and incident management (acknowledge, notes, timeline)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, union_all

from app.auth.deps import DB, CurrentUser
from app.core.audit import audit
from app.core.errors import NotFound
from app.core.requestctx import client_ip
from app.models import CheckResult, Incident, Monitor, NotificationOutbox, RetainedCheck, User

router = APIRouter(prefix="/api/incidents", tags=["incidents"])
MAX_TIMELINE_CHECKS = 300


def _duration(i: Incident, now: datetime) -> int:
    return int(((i.resolved_at or now) - i.started_at).total_seconds())


def _incident_out(i: Incident, monitor_name: str, now: datetime) -> dict:
    return {
        "id": str(i.id),
        "monitor_id": str(i.monitor_id),
        "monitor_name": monitor_name,
        "started_at": i.started_at.isoformat(),
        "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
        "cause": i.cause,
        "error_kind": i.error_kind,
        "status_code": i.status_code,
        "duration_seconds": _duration(i, now),
        "acknowledged_at": i.acknowledged_at.isoformat() if i.acknowledged_at else None,
        "note": i.note,
    }


def _owned(ctx):
    return (
        select(Incident, Monitor.name)
        .join(Monitor, Monitor.id == Incident.monitor_id)
        .where(Monitor.owner_id == ctx.user.id)
    )


@router.get("")
async def list_incidents(
    ctx: CurrentUser,
    db: DB,
    state: Literal["all", "open", "resolved"] = Query("all", alias="status"),
    monitor_id: uuid.UUID | None = None,
    before: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    stmt = _owned(ctx)
    if state == "open":
        stmt = stmt.where(Incident.resolved_at.is_(None))
    elif state == "resolved":
        stmt = stmt.where(Incident.resolved_at.is_not(None))
    if monitor_id:
        stmt = stmt.where(Incident.monitor_id == monitor_id)
    if before:
        stmt = stmt.where(Incident.started_at < before)
    rows = (await db.execute(stmt.order_by(Incident.started_at.desc()).limit(limit + 1))).all()
    now = datetime.now(UTC)
    items = [_incident_out(i, name, now) for i, name in rows[:limit]]
    return {
        "items": items,
        "next_before": items[-1]["started_at"] if len(rows) > limit else None,
    }


@router.get("/summary")
async def incident_summary(ctx: CurrentUser, db: DB, days: int = Query(30, ge=1, le=365)) -> dict:
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    rows = (
        await db.execute(
            _owned(ctx).where(or_(Incident.started_at >= since, Incident.resolved_at.is_(None)))
        )
    ).all()
    resolved = [i for i, _ in rows if i.resolved_at is not None]
    # Only count the part of each outage that falls inside the window.
    downtime = sum(
        int(((i.resolved_at or now) - max(i.started_at, since)).total_seconds()) for i, _ in rows
    )
    mttr = int(sum(_duration(i, now) for i in resolved) / len(resolved)) if resolved else None
    return {
        "days": days,
        "total": len(rows),
        "open": sum(1 for i, _ in rows if i.resolved_at is None),
        "downtime_seconds": downtime,
        "mean_time_to_recovery_seconds": mttr,
    }


async def _get_owned(db, ctx, incident_id: uuid.UUID) -> tuple[Incident, Monitor]:
    row = (
        await db.execute(
            select(Incident, Monitor)
            .join(Monitor, Monitor.id == Incident.monitor_id)
            .where(Incident.id == incident_id, Monitor.owner_id == ctx.user.id)
        )
    ).first()
    if row is None:
        raise NotFound("Incident not found.")
    return row[0], row[1]


@router.get("/{incident_id}")
async def incident_detail(incident_id: uuid.UUID, ctx: CurrentUser, db: DB) -> dict:
    incident, monitor = await _get_owned(db, ctx, incident_id)
    now = datetime.now(UTC)
    end = incident.resolved_at or now
    # Checks from shortly before the outage until shortly after it ended.
    window_start = incident.started_at - timedelta(seconds=monitor.interval_seconds * 2)
    window_end = end + timedelta(seconds=monitor.interval_seconds * 2)

    # Recent days come from check_results; older incidents from retained_checks, which keeps
    # failed checks and the checks around every incident after the raw data has expired.
    def window(table):
        return select(
            table.checked_at,
            table.is_up,
            table.status_code,
            table.response_ms,
            table.error_kind,
            table.error_message,
        ).where(
            table.monitor_seq == monitor.seq,
            table.checked_at >= window_start,
            table.checked_at <= window_end,
        )

    both = union_all(window(CheckResult), window(RetainedCheck)).subquery()
    checks = (
        await db.execute(select(both).order_by(both.c.checked_at).limit(MAX_TIMELINE_CHECKS))
    ).all()
    notifications = (
        await db.scalars(
            select(NotificationOutbox)
            .where(NotificationOutbox.incident_id == incident.id)
            .order_by(NotificationOutbox.created_at)
        )
    ).all()
    ack_name = None
    if incident.acknowledged_by:
        ack_user = await db.get(User, incident.acknowledged_by)
        ack_name = (ack_user.full_name or ack_user.email) if ack_user else None
    return {
        "incident": {**_incident_out(incident, monitor.name, now), "acknowledged_by": ack_name},
        "monitor": {
            "id": str(monitor.id),
            "name": monitor.name,
            "url": monitor.url,
            "status": monitor.status,
            "interval_seconds": monitor.interval_seconds,
        },
        "checks": [
            {
                "checked_at": c.checked_at.isoformat(),
                "is_up": c.is_up,
                "status_code": c.status_code,
                "response_ms": c.response_ms,
                "error_kind": c.error_kind,
                "error": c.error_message,
            }
            for c in checks
        ],
        "notifications": [
            {
                "kind": n.kind,
                "recipient": n.recipient,
                "status": n.status,
                "created_at": n.created_at.isoformat(),
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "last_error": n.last_error,
            }
            for n in notifications
        ],
    }


class IncidentPatch(BaseModel):
    acknowledged: bool | None = None
    note: str | None = Field(default=None, max_length=2000)


@router.patch("/{incident_id}")
async def update_incident(
    incident_id: uuid.UUID, body: IncidentPatch, ctx: CurrentUser, request: Request, db: DB
) -> dict:
    incident, monitor = await _get_owned(db, ctx, incident_id)
    changes = body.model_dump(exclude_unset=True)
    if "acknowledged" in changes:
        if body.acknowledged and incident.acknowledged_at is None:
            incident.acknowledged_at = datetime.now(UTC)
            incident.acknowledged_by = ctx.user.id
        elif body.acknowledged is False:
            incident.acknowledged_at = None
            incident.acknowledged_by = None
    if "note" in changes:
        incident.note = (body.note or "").strip() or None
    audit(
        db,
        "incident.update",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="incident",
        target_id=incident.id,
        fields=sorted(changes),
    )
    await db.commit()
    return _incident_out(incident, monitor.name, datetime.now(UTC))
