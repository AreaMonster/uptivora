"""Admin: payments, licence order fulfilment, manual plan assignment."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import DB, AppSettings, CurrentAdmin, require_admin
from app.billing import licences, service
from app.core.audit import audit
from app.core.errors import NotFound
from app.core.requestctx import client_ip
from app.models import LicenseOrder, LicenseProduct, Payment, Plan, User

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _hosted(settings) -> None:
    if not settings.is_hosted:
        raise NotFound("Only available in the hosted edition.")


@router.get("/payments")
async def list_payments(
    db: DB, settings: AppSettings, limit: int = Query(100, ge=1, le=500)
) -> list[dict]:
    _hosted(settings)
    rows = (
        await db.execute(
            select(Payment, User.email)
            .outerjoin(User, User.id == Payment.user_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(p.id),
            "user_email": email,
            "amount_cents": p.amount_cents,
            "currency": p.currency,
            "status": p.status,
            "provider": p.provider,
            "is_test": p.is_test,
            "description": p.description,
            "created_at": p.created_at.isoformat(),
        }
        for p, email in rows
    ]


def _order_out(o: LicenseOrder, product: LicenseProduct, email: str | None) -> dict:
    return {
        "id": str(o.id),
        "status": o.status,
        "product": product.name,
        "product_code": product.code,
        "edition": product.edition,
        "price_cents": o.price_cents,
        "currency": o.currency,
        "is_test": o.is_test,
        "licensee_name": o.licensee_name,
        "licensee_email": o.licensee_email,
        "customer_email": email,
        "license_id": str(o.license_id) if o.license_id else None,
        "created_at": o.created_at.isoformat(),
        "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        "fulfilled_at": o.fulfilled_at.isoformat() if o.fulfilled_at else None,
    }


@router.get("/licence-orders")
async def list_orders(
    db: DB,
    settings: AppSettings,
    state: Literal["all", "paid", "fulfilled", "refunded", "cancelled"] = Query(
        "all", alias="status"
    ),
) -> list[dict]:
    _hosted(settings)
    stmt = (
        select(LicenseOrder, LicenseProduct, User.email)
        .join(LicenseProduct, LicenseProduct.id == LicenseOrder.product_id)
        .outerjoin(User, User.id == LicenseOrder.user_id)
    )
    if state != "all":
        stmt = stmt.where(LicenseOrder.status == state)
    rows = (await db.execute(stmt.order_by(LicenseOrder.created_at.desc()).limit(200))).all()
    return [_order_out(o, p, e) for o, p, e in rows]


async def _order(db, order_id: uuid.UUID) -> LicenseOrder:
    order = await db.scalar(
        select(LicenseOrder).where(LicenseOrder.id == order_id).with_for_update()
    )
    if order is None:
        raise NotFound("Order not found.")
    return order


class FulfilIn(BaseModel):
    licence_text: str = Field(min_length=50, max_length=32_768)


@router.post("/licence-orders/{order_id}/fulfil")
async def fulfil(
    order_id: uuid.UUID,
    body: FulfilIn,
    ctx: CurrentAdmin,
    request: Request,
    db: DB,
    settings: AppSettings,
) -> dict:
    _hosted(settings)
    order = await licences.fulfil_order(db, settings, await _order(db, order_id), body.licence_text)
    audit(
        db,
        "admin.licence_fulfil",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="licence_order",
        target_id=order.id,
        license_id=str(order.license_id),
    )
    await db.commit()
    return {"id": str(order.id), "status": order.status, "license_id": str(order.license_id)}


@router.post("/licence-orders/{order_id}/refund")
async def refund(
    order_id: uuid.UUID, ctx: CurrentAdmin, request: Request, db: DB, settings: AppSettings
) -> dict:
    _hosted(settings)
    order = await licences.refund_order(db, await _order(db, order_id))
    audit(
        db,
        "admin.licence_refund",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="licence_order",
        target_id=order.id,
    )
    await db.commit()
    return {"id": str(order.id), "status": order.status}


class AssignPlanIn(BaseModel):
    plan_code: str = Field(max_length=32)
    months: int = Field(default=1, ge=1, le=36)


@router.post("/users/{user_id}/subscription")
async def assign_plan(
    user_id: uuid.UUID,
    body: AssignPlanIn,
    ctx: CurrentAdmin,
    request: Request,
    db: DB,
    settings: AppSettings,
) -> dict:
    """Give a customer a plan without payment (complimentary / invoiced offline)."""
    _hosted(settings)
    user = await db.get(User, user_id)
    if user is None:
        raise NotFound("User not found.")
    plan = await db.scalar(select(Plan).where(Plan.code == body.plan_code))
    if plan is None:
        raise NotFound("Plan not found.")
    sub = await service.assign_manual(db, settings, user, plan, body.months)
    audit(
        db,
        "admin.assign_plan",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="user",
        target_id=user.id,
        plan=plan.code,
        months=body.months,
    )
    await db.commit()
    return {
        "plan": plan.code,
        "ends_at": sub.current_period_end.isoformat(),
        "provider": sub.provider,
    }
