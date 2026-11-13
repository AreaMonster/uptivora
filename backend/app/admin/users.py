"""Admin: user management, read-only support view, monitor moderation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.auth.deps import DB, AppSettings, CurrentAdmin, require_admin
from app.auth.service import revoke_sessions
from app.core.audit import audit
from app.core.errors import AppError, Conflict, NotFound
from app.core.requestctx import client_ip
from app.limits import limits_for, live_subscription, monitor_usage
from app.models import (
    AuditLog,
    Incident,
    Monitor,
    MonitorStatus,
    PausedReason,
    Plan,
    Subscription,
    User,
    UserRole,
)
from app.models.billing import LIVE_SUBSCRIPTION_STATUSES

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _user_row(u: User, plan_name: str | None, sub_status: str | None, monitors: int) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": u.is_active,
        "email_verified": u.email_verified_at is not None,
        "pending_invite": u.password_hash.startswith("!pending-invitation:"),
        "created_at": u.created_at.isoformat(),
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "plan": plan_name,
        "subscription_status": sub_status,
        "monitors": monitors,
    }


@router.get("/users")
async def list_users(
    db: DB,
    q: str | None = Query(None, max_length=100),
    role: Literal["user", "admin"] | None = None,
    state: Literal["all", "active", "suspended"] = Query("all", alias="status"),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(25, ge=1, le=100),
) -> dict:
    monitor_count = (
        select(func.count())
        .select_from(Monitor)
        .where(Monitor.owner_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    stmt = (
        select(User, Plan.name, Subscription.status, monitor_count)
        .outerjoin(
            Subscription,
            (Subscription.user_id == User.id) & Subscription.status.in_(LIVE_SUBSCRIPTION_STATUSES),
        )
        .outerjoin(Plan, Plan.id == Subscription.plan_id)
    )
    filters = []
    if q:
        filters.append(
            or_(
                User.email.ilike(_like(q.strip().lower()), escape="\\"),
                User.full_name.ilike(_like(q.strip()), escape="\\"),
            )
        )
    if role:
        filters.append(User.role == role)
    if state != "all":
        filters.append(User.is_active.is_(state == "active"))
    stmt = stmt.where(*filters)
    total = await db.scalar(select(func.count()).select_from(User).where(*filters))
    rows = (
        await db.execute(
            stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {
        "items": [_user_row(u, plan, status, n) for u, plan, status, n in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def _get_user(db, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("User not found.")
    return user


@router.get("/users/{user_id}")
async def user_detail(user_id: uuid.UUID, db: DB, settings: AppSettings) -> dict:
    """Read-only support view. There is deliberately no "log in as" feature."""
    user = await _get_user(db, user_id)
    limits = await limits_for(db, settings, user)
    found = await live_subscription(db, user.id)
    monitors = (
        await db.scalars(select(Monitor).where(Monitor.owner_id == user.id).order_by(Monitor.name))
    ).all()
    events = (
        await db.scalars(
            select(AuditLog)
            .where(or_(AuditLog.actor_user_id == user.id, AuditLog.target_id == str(user.id)))
            .order_by(AuditLog.created_at.desc())
            .limit(25)
        )
    ).all()
    open_incidents = await db.scalar(
        select(func.count())
        .select_from(Incident)
        .join(Monitor, Monitor.id == Incident.monitor_id)
        .where(Monitor.owner_id == user.id, Incident.resolved_at.is_(None))
    )
    sub = None
    if found:
        s, plan = found
        sub = {
            "plan": plan.name,
            "plan_code": plan.code,
            "status": s.status,
            "is_test": s.is_test,
            "current_period_end": s.current_period_end.isoformat(),
            "cancel_at_period_end": s.cancel_at_period_end,
            "provider": s.provider,
        }
    return {
        "user": _user_row(
            user, sub["plan"] if sub else None, sub["status"] if sub else None, len(monitors)
        ),
        "timezone": user.timezone,
        "limits": limits.to_dict(),
        "usage": {
            "active_monitors": await monitor_usage(db, user, limits),
            "open_incidents": open_incidents,
        },
        "subscription": sub,
        "monitors": [
            {
                "id": str(m.id),
                "name": m.name,
                "url": m.url,
                "status": m.status,
                "is_paused": m.is_paused,
                "paused_reason": m.paused_reason,
                "interval_seconds": m.interval_seconds,
                "last_checked_at": m.last_checked_at.isoformat() if m.last_checked_at else None,
            }
            for m in monitors
        ],
        "audit": [
            {
                "action": e.action,
                "created_at": e.created_at.isoformat(),
                "ip": e.ip_address,
                "by_self": e.actor_user_id == user.id,
            }
            for e in events
        ],
    }


class UserPatch(BaseModel):
    is_active: bool | None = None
    role: Literal["user", "admin"] | None = None


async def _admin_count(db) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
        or 0
    )


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID, body: UserPatch, ctx: CurrentAdmin, request: Request, db: DB
) -> dict:
    user = await _get_user(db, user_id)
    changes = body.model_dump(exclude_unset=True)
    if user.id == ctx.user.id and (
        changes.get("is_active") is False or changes.get("role") == "user"
    ):
        raise Conflict("You cannot suspend or demote your own account.")
    losing_admin = (
        user.role == UserRole.ADMIN
        and user.is_active
        and (changes.get("role") == "user" or changes.get("is_active") is False)
    )
    if losing_admin and await _admin_count(db) <= 1:
        raise Conflict("At least one active administrator is required.")
    if "role" in changes and changes["role"] is not None:
        user.role = UserRole(changes["role"])
    if "is_active" in changes and changes["is_active"] is not None:
        user.is_active = changes["is_active"]
        if not user.is_active:
            await revoke_sessions(db, user.id)
    audit(
        db,
        "admin.user_update",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="user",
        target_id=user.id,
        changes=changes,
    )
    await db.commit()
    return {"id": str(user.id), "role": user.role, "is_active": user.is_active}


@router.post("/users/{user_id}/revoke-sessions")
async def admin_revoke_sessions(
    user_id: uuid.UUID, ctx: CurrentAdmin, request: Request, db: DB
) -> dict:
    user = await _get_user(db, user_id)
    if user.id == ctx.user.id:
        raise Conflict("Use your own account settings to sign out your sessions.")
    await revoke_sessions(db, user.id)
    audit(
        db,
        "admin.revoke_sessions",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="user",
        target_id=user.id,
    )
    await db.commit()
    return {"status": "revoked"}


# --- monitors -------------------------------------------------------------------------------


@router.get("/monitors")
async def list_monitors(
    db: DB,
    q: str | None = Query(None, max_length=200),
    state: Literal["all", "up", "down", "paused", "pending", "admin_paused"] = Query(
        "all", alias="status"
    ),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    stmt = select(Monitor, User.email).join(User, User.id == Monitor.owner_id)
    filters = []
    if q:
        like = _like(q.strip())
        filters.append(
            or_(
                Monitor.url.ilike(like, escape="\\"),
                Monitor.name.ilike(like, escape="\\"),
                User.email.ilike(like, escape="\\"),
            )
        )
    if state == "admin_paused":
        filters.append(Monitor.paused_reason == PausedReason.ADMIN)
    elif state == "paused":
        filters.append(Monitor.is_paused.is_(True))
    elif state != "all":
        filters.append(Monitor.status == state)
        filters.append(Monitor.is_paused.is_(False))
    total = await db.scalar(
        select(func.count())
        .select_from(Monitor)
        .join(User, User.id == Monitor.owner_id)
        .where(*filters)
    )
    rows = (
        await db.execute(
            stmt.where(*filters)
            .order_by(Monitor.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            {
                "id": str(m.id),
                "name": m.name,
                "url": m.url,
                "owner_email": email,
                "owner_id": str(m.owner_id),
                "status": m.status,
                "is_paused": m.is_paused,
                "paused_reason": m.paused_reason,
                "interval_seconds": m.interval_seconds,
                "last_checked_at": m.last_checked_at.isoformat() if m.last_checked_at else None,
                "last_error": m.last_error,
                "created_at": m.created_at.isoformat(),
            }
            for m, email in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


class ModerationIn(BaseModel):
    reason: str | None = None


@router.post("/monitors/{monitor_id}/pause")
async def admin_pause(
    monitor_id: uuid.UUID, body: ModerationIn, ctx: CurrentAdmin, request: Request, db: DB
) -> dict:
    """Stop an abusive or problematic monitor. The owner cannot resume it themselves."""
    m = await db.scalar(select(Monitor).where(Monitor.id == monitor_id).with_for_update())
    if m is None:
        raise NotFound("Monitor not found.")
    m.is_paused = True
    m.paused_reason = PausedReason.ADMIN
    m.status = MonitorStatus.PAUSED
    m.lease_owner = m.lease_until = None
    audit(
        db,
        "admin.monitor_pause",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="monitor",
        target_id=m.id,
        url=m.url,
        reason=(body.reason or "")[:500],
    )
    await db.commit()
    return {"id": str(m.id), "is_paused": True, "paused_reason": "admin"}


@router.post("/monitors/{monitor_id}/resume")
async def admin_resume(monitor_id: uuid.UUID, ctx: CurrentAdmin, request: Request, db: DB) -> dict:
    m = await db.scalar(select(Monitor).where(Monitor.id == monitor_id).with_for_update())
    if m is None:
        raise NotFound("Monitor not found.")
    if m.paused_reason != PausedReason.ADMIN:
        # Respect the owner's own pause (or a plan-limit pause); only lift admin pauses.
        raise AppError(
            "Only monitors paused by an administrator can be resumed here.",
            code="not_admin_paused",
            status_code=409,
        )
    m.is_paused = False
    m.paused_reason = None
    m.status = MonitorStatus.PENDING
    m.consecutive_failures = m.consecutive_successes = 0
    m.next_check_at = datetime.now(UTC)
    audit(
        db,
        "admin.monitor_resume",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="monitor",
        target_id=m.id,
    )
    await db.commit()
    return {"id": str(m.id), "is_paused": False}


@router.get("/incidents/recent")
async def recent_incidents(db: DB, limit: int = Query(20, ge=1, le=100)) -> list[dict]:
    rows = (
        await db.execute(
            select(Incident, Monitor.name, User.email)
            .join(Monitor, Monitor.id == Incident.monitor_id)
            .join(User, User.id == Monitor.owner_id)
            .order_by(Incident.started_at.desc())
            .limit(limit)
        )
    ).all()
    now = datetime.now(UTC)
    return [
        {
            "id": str(i.id),
            "monitor_id": str(i.monitor_id),
            "monitor_name": name,
            "owner_email": email,
            "started_at": i.started_at.isoformat(),
            "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            "duration_seconds": int(((i.resolved_at or now) - i.started_at).total_seconds()),
            "cause": i.cause,
        }
        for i, name, email in rows
    ]
