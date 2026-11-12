"""Admin: plan catalogue, self-hosted licence products, runtime settings, logs and audit."""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.auth.deps import DB, AppSettings, CurrentAdmin, require_admin
from app.core.audit import audit
from app.core.errors import Conflict, NotFound
from app.core.requestctx import client_ip
from app.models import AppSetting, AuditLog, LicenseProduct, Plan, Subscription, SystemEvent, User
from app.models.billing import LIVE_SUBSCRIPTION_STATUSES

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")


def _hosted_only(settings) -> None:
    if not settings.is_hosted:
        raise NotFound("Plans and licence sales exist only in the hosted edition.")


# --- subscription plans ---------------------------------------------------------------------


class PlanFields(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=500)
    price_cents: int = Field(ge=0, le=10_000_000)
    currency: str = Field(default="CHF", pattern=r"^[A-Z]{3}$")
    max_monitors: int = Field(ge=1, le=100_000)
    min_interval_seconds: int = Field(ge=30, le=86_400)
    is_active: bool = True
    is_public: bool = True
    sort_order: int = Field(default=0, ge=0, le=10_000)


class PlanCreate(PlanFields):
    code: str

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        if not CODE_RE.match(v):
            raise ValueError("2–32 lowercase letters, digits or dashes")
        return v


def _plan_out(p: Plan, subscribers: int = 0) -> dict:
    return {
        "id": str(p.id),
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "price_cents": p.price_cents,
        "currency": p.currency,
        "interval": p.interval,
        "max_monitors": p.max_monitors,
        "min_interval_seconds": p.min_interval_seconds,
        "is_active": p.is_active,
        "is_public": p.is_public,
        "sort_order": p.sort_order,
        "subscribers": subscribers,
    }


async def _subscriber_counts(db) -> dict:
    rows = (
        await db.execute(
            select(Subscription.plan_id, func.count())
            .where(Subscription.status.in_(LIVE_SUBSCRIPTION_STATUSES))
            .group_by(Subscription.plan_id)
        )
    ).all()
    return {pid: n for pid, n in rows}


@router.get("/plans")
async def list_plans(db: DB, settings: AppSettings) -> list[dict]:
    _hosted_only(settings)
    counts = await _subscriber_counts(db)
    plans = (await db.scalars(select(Plan).order_by(Plan.sort_order, Plan.price_cents))).all()
    return [_plan_out(p, counts.get(p.id, 0)) for p in plans]


@router.post("/plans", status_code=201)
async def create_plan(
    body: PlanCreate, ctx: CurrentAdmin, request: Request, db: DB, settings: AppSettings
) -> dict:
    _hosted_only(settings)
    if await db.scalar(select(Plan.id).where(Plan.code == body.code)):
        raise Conflict("A plan with this code already exists.", fields={"code": "Already used"})
    plan = Plan(**body.model_dump())
    db.add(plan)
    await db.flush()
    audit(
        db,
        "admin.plan_create",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="plan",
        target_id=plan.id,
        plan=body.model_dump(),
    )
    await db.commit()
    await db.refresh(plan)
    return _plan_out(plan)


@router.put("/plans/{code}")
async def update_plan(
    code: str, body: PlanFields, ctx: CurrentAdmin, request: Request, db: DB, settings: AppSettings
) -> dict:
    """Edit price and limits. Limit changes apply to existing subscribers immediately;
    price changes apply from their next renewal."""
    _hosted_only(settings)
    plan = await db.scalar(select(Plan).where(Plan.code == code))
    if plan is None:
        raise NotFound("Plan not found.")
    before = _plan_out(plan)
    for key, value in body.model_dump().items():
        setattr(plan, key, value)
    changed = {k: [before[k], v] for k, v in body.model_dump().items() if before.get(k) != v}
    audit(
        db,
        "admin.plan_update",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="plan",
        target_id=plan.id,
        changes=changed,
    )
    await db.commit()
    await db.refresh(plan)
    return _plan_out(plan, (await _subscriber_counts(db)).get(plan.id, 0))


# --- self-hosted licence products -----------------------------------------------------------


class LicenceLimitsIn(BaseModel):
    max_monitors: int = Field(ge=0, le=1_000_000)
    max_users: int = Field(ge=0, le=100_000)
    min_interval_seconds: int = Field(ge=30, le=86_400)


class LicenceProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=500)
    price_cents: int = Field(ge=0, le=10_000_000)
    currency: str = Field(default="CHF", pattern=r"^[A-Z]{3}$")
    limits: LicenceLimitsIn
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0, le=10_000)


def _product_out(p: LicenseProduct) -> dict:
    return {
        "id": str(p.id),
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "edition": p.edition,
        "price_cents": p.price_cents,
        "currency": p.currency,
        "limits": p.limits,
        "is_active": p.is_active,
        "sort_order": p.sort_order,
    }


@router.get("/licence-products")
async def list_products(db: DB, settings: AppSettings) -> list[dict]:
    _hosted_only(settings)
    rows = (await db.scalars(select(LicenseProduct).order_by(LicenseProduct.sort_order))).all()
    return [_product_out(p) for p in rows]


@router.put("/licence-products/{code}")
async def update_product(
    code: str,
    body: LicenceProductIn,
    ctx: CurrentAdmin,
    request: Request,
    db: DB,
    settings: AppSettings,
) -> dict:
    _hosted_only(settings)
    product = await db.scalar(select(LicenseProduct).where(LicenseProduct.code == code))
    if product is None:
        raise NotFound("Licence product not found.")
    data = body.model_dump()
    for key, value in data.items():
        setattr(product, key, value)
    audit(
        db,
        "admin.licence_product_update",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="licence_product",
        target_id=product.id,
        values=data,
    )
    await db.commit()
    await db.refresh(product)
    return _product_out(product)


# --- runtime settings -----------------------------------------------------------------------

# Only these keys may be stored (never secrets: those live in environment variables).
SETTING_DEFAULTS: dict[str, Any] = {"public_signup": False}


class SettingsIn(BaseModel):
    public_signup: bool | None = None


@router.get("/settings")
async def get_settings_values(db: DB, settings: AppSettings) -> dict:
    rows = {r.key: r.value for r in (await db.scalars(select(AppSetting))).all()}
    values = {k: rows.get(k, v) for k, v in SETTING_DEFAULTS.items()}
    return {
        "values": values,
        "notes": {
            "public_signup": "Hosted: sign-up is always open. Self-hosted: allow anyone "
            "who can reach this installation to create an account (within licence "
            "limits)."
        },
        "edition": settings.edition,
    }


@router.put("/settings")
async def put_settings_values(
    body: SettingsIn, ctx: CurrentAdmin, request: Request, db: DB
) -> dict:
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        row = await db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value, updated_by=ctx.user.id))
        else:
            row.value = value
            row.updated_by = ctx.user.id
    audit(db, "admin.settings_update", actor_id=ctx.user.id, ip=client_ip(request), changes=changes)
    await db.commit()
    return {"status": "saved", "changes": changes}


# --- logs & audit ---------------------------------------------------------------------------


@router.get("/logs")
async def system_logs(
    db: DB,
    level: Literal["all", "info", "warning", "error"] = "all",
    source: str | None = Query(None, max_length=32),
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    stmt = select(SystemEvent)
    if level == "warning":
        stmt = stmt.where(SystemEvent.level.in_(["warning", "error", "critical"]))
    elif level == "error":
        stmt = stmt.where(SystemEvent.level.in_(["error", "critical"]))
    elif level == "info":
        stmt = stmt.where(SystemEvent.level == "info")
    if source:
        stmt = stmt.where(SystemEvent.source == source)
    rows = (await db.scalars(stmt.order_by(SystemEvent.created_at.desc()).limit(limit))).all()
    return [
        {
            "id": r.id,
            "level": r.level,
            "source": r.source,
            "message": r.message,
            "details": r.details,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/audit")
async def audit_log(
    db: DB,
    action: str | None = Query(None, max_length=64),
    actor: str | None = Query(None, max_length=254),
    limit: int = Query(100, ge=1, le=500),
) -> list[dict]:
    stmt = select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.actor_user_id)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    if actor:
        stmt = stmt.where(User.email == actor.strip().lower())
    rows = (await db.execute(stmt.order_by(AuditLog.created_at.desc()).limit(limit))).all()
    return [
        {
            "id": a.id,
            "action": a.action,
            "actor": email,
            "target_type": a.target_type,
            "target_id": a.target_id,
            "ip": a.ip_address,
            "details": a.details,
            "created_at": a.created_at.isoformat(),
        }
        for a, email in rows
    ]
