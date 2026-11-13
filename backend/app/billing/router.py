"""Customer billing API (hosted edition) and the payment-provider webhook endpoint."""

from __future__ import annotations

import json
import uuid
from typing import Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.auth.deps import DB, AppSettings, CurrentUser
from app.billing import licences, service
from app.billing.providers import WebhookSignatureError, verify_stripe_signature
from app.core import ratelimit
from app.core.audit import audit
from app.core.errors import AppError, NotFound
from app.core.requestctx import client_ip
from app.limits import limits_for, live_subscription, monitor_usage
from app.models import (
    LicenseOrder,
    LicenseOrderStatus,
    LicenseProduct,
    Plan,
    WebhookEvent,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])
Simulate = Literal["success", "decline"]


def _simulate(settings, value: Simulate) -> Simulate:
    # Only the TEST MODE simulator honours a requested outcome.
    return value if settings.billing_test_mode else "success"


def _plan_out(p: Plan) -> dict:
    return {
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "price_cents": p.price_cents,
        "currency": p.currency,
        "interval": p.interval,
        "max_monitors": p.max_monitors,
        "min_interval_seconds": p.min_interval_seconds,
    }


async def _plan(db, code: str) -> Plan:
    plan = await db.scalar(select(Plan).where(Plan.code == code))
    if plan is None:
        raise NotFound("Plan not found.")
    return plan


@router.get("")
async def billing_summary(ctx: CurrentUser, db: DB, settings: AppSettings) -> dict:
    if not settings.is_hosted:
        raise NotFound("Billing is not available in the self-hosted edition.")
    found = await live_subscription(db, ctx.user.id)
    sub = None
    if found:
        s, plan = found
        pending = await db.get(Plan, s.pending_plan_id) if s.pending_plan_id else None
        sub = {
            "plan": _plan_out(plan),
            "status": s.status,
            "is_test": s.is_test,
            "provider": s.provider,
            "current_period_start": s.current_period_start.isoformat(),
            "current_period_end": s.current_period_end.isoformat(),
            "cancel_at_period_end": s.cancel_at_period_end,
            "pending_plan": _plan_out(pending) if pending else None,
            "simulate_failure": s.simulate_failure,
            "grace_until": (s.current_period_end + service.PAST_DUE_GRACE).isoformat()
            if s.status == "past_due"
            else None,
        }
    plans = (
        await db.scalars(
            select(Plan)
            .where(Plan.is_active.is_(True), Plan.is_public.is_(True))
            .order_by(Plan.sort_order)
        )
    ).all()
    payments = await service.payment_history(db, ctx.user)
    orders = (
        await db.execute(
            select(LicenseOrder, LicenseProduct.name)
            .join(LicenseProduct, LicenseProduct.id == LicenseOrder.product_id)
            .where(LicenseOrder.user_id == ctx.user.id)
            .order_by(LicenseOrder.created_at.desc())
        )
    ).all()
    products = (
        await db.scalars(
            select(LicenseProduct)
            .where(LicenseProduct.is_active.is_(True))
            .order_by(LicenseProduct.sort_order)
        )
    ).all()
    limits = await limits_for(db, settings, ctx.user)
    return {
        "enabled": settings.billing_provider != "disabled",
        "test_mode": settings.billing_test_mode,
        "subscription": sub,
        "usage": {"active_monitors": await monitor_usage(db, ctx.user, limits)},
        "plans": [_plan_out(p) for p in plans],
        "payments": [
            {
                "id": str(p.id),
                "amount_cents": p.amount_cents,
                "currency": p.currency,
                "status": p.status,
                "description": p.description,
                "is_test": p.is_test,
                "created_at": p.created_at.isoformat(),
            }
            for p in payments
        ],
        "licence_products": [
            {
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "edition": p.edition,
                "price_cents": p.price_cents,
                "currency": p.currency,
                "limits": p.limits,
            }
            for p in products
        ],
        "licence_orders": [
            {
                "id": str(o.id),
                "product": name,
                "status": o.status,
                "price_cents": o.price_cents,
                "currency": o.currency,
                "is_test": o.is_test,
                "licensee_name": o.licensee_name,
                "created_at": o.created_at.isoformat(),
                "fulfilled_at": o.fulfilled_at.isoformat() if o.fulfilled_at else None,
            }
            for o, name in orders
        ],
    }


@router.get("/quote")
async def get_quote(
    ctx: CurrentUser, db: DB, settings: AppSettings, plan: str = Query(max_length=32)
) -> dict:
    service.ensure_billing(settings)
    q = await service.quote(db, ctx.user, await _plan(db, plan))
    return {
        "action": q.action,
        "amount_cents": q.amount_cents,
        "currency": q.currency,
        "effective_at": q.effective_at.isoformat(),
        "plan": _plan_out(q.plan),
        "current_plan": _plan_out(q.current_plan) if q.current_plan else None,
        "test_mode": settings.billing_test_mode,
    }


class SubscribeIn(BaseModel):
    plan_code: str = Field(max_length=32)
    simulate: Simulate = "success"


@router.post("/subscribe")
async def subscribe(
    body: SubscribeIn, ctx: CurrentUser, request: Request, db: DB, settings: AppSettings
) -> dict:
    await ratelimit.hit("billing", str(ctx.user.id), limit=20, window_seconds=3600)
    plan = await _plan(db, body.plan_code)
    try:
        result = await service.change_plan(
            db, settings, ctx.user, plan, _simulate(settings, body.simulate)
        )
    except service.PaymentDeclined:
        audit(
            db,
            "billing.payment_declined",
            actor_id=ctx.user.id,
            ip=client_ip(request),
            target_type="plan",
            target_id=plan.code,
        )
        await db.commit()
        raise
    audit(
        db,
        "billing.change_plan",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="plan",
        target_id=plan.code,
        change=result["action"],
        charged_cents=result["charged_cents"],
    )
    await db.commit()
    return result


@router.post("/cancel")
async def cancel(ctx: CurrentUser, request: Request, db: DB, settings: AppSettings) -> dict:
    sub = await service.cancel(db, settings, ctx.user)
    audit(db, "billing.cancel", actor_id=ctx.user.id, ip=client_ip(request))
    await db.commit()
    return {"status": sub.status, "ends_at": sub.current_period_end.isoformat()}


@router.post("/resume")
async def resume(ctx: CurrentUser, request: Request, db: DB, settings: AppSettings) -> dict:
    sub = await service.resume(db, settings, ctx.user)
    audit(db, "billing.resume", actor_id=ctx.user.id, ip=client_ip(request))
    await db.commit()
    return {"status": sub.status}


@router.post("/cancel-change")
async def cancel_change(ctx: CurrentUser, db: DB, settings: AppSettings) -> dict:
    await service.cancel_pending_change(db, settings, ctx.user)
    return {"status": "ok"}


class RetryIn(BaseModel):
    simulate: Simulate = "success"


@router.post("/retry")
async def retry(body: RetryIn, ctx: CurrentUser, db: DB, settings: AppSettings) -> dict:
    await ratelimit.hit("billing-retry", str(ctx.user.id), limit=10, window_seconds=3600)
    return {
        "status": await service.retry_payment(
            db, settings, ctx.user, _simulate(settings, body.simulate)
        )
    }


class TestSettingsIn(BaseModel):
    simulate_renewal_failure: bool


@router.put("/test-settings")
async def test_settings(
    body: TestSettingsIn, ctx: CurrentUser, db: DB, settings: AppSettings
) -> dict:
    service.ensure_billing(settings)
    if not settings.billing_test_mode:
        raise NotFound("Not found.")
    found = await live_subscription(db, ctx.user.id)
    if found is None:
        raise AppError("You have no subscription.", code="no_subscription", status_code=409)
    found[0].simulate_failure = body.simulate_renewal_failure
    await db.commit()
    return {"simulate_renewal_failure": body.simulate_renewal_failure}


# --- self-hosted licence store --------------------------------------------------------------


class LicenceOrderIn(BaseModel):
    product_code: str = Field(max_length=32)
    licensee_name: str = Field(min_length=2, max_length=200)
    licensee_email: EmailStr
    simulate: Simulate = "success"


@router.post("/licence-orders", status_code=201)
async def order_licence(
    body: LicenceOrderIn, ctx: CurrentUser, request: Request, db: DB, settings: AppSettings
) -> dict:
    await ratelimit.hit("licence-order", str(ctx.user.id), limit=10, window_seconds=3600)
    product = await db.scalar(
        select(LicenseProduct).where(LicenseProduct.code == body.product_code)
    )
    if product is None:
        raise NotFound("Licence product not found.")
    order = await licences.create_order(
        db,
        settings,
        ctx.user,
        product,
        licensee_name=body.licensee_name,
        licensee_email=str(body.licensee_email),
        simulate=_simulate(settings, body.simulate),
    )
    audit(
        db,
        "billing.licence_order",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="licence_order",
        target_id=order.id,
        product=product.code,
    )
    await db.commit()
    # Signed within seconds when the signing service runs; otherwise the worker retries.
    await licences.auto_fulfil(db, settings, order)
    return {"id": str(order.id), "status": order.status}


@router.get("/licence-orders/{order_id}/download")
async def download_licence(order_id: uuid.UUID, ctx: CurrentUser, db: DB) -> Response:
    order = await db.scalar(
        select(LicenseOrder).where(LicenseOrder.id == order_id, LicenseOrder.user_id == ctx.user.id)
    )
    if order is None:
        raise NotFound("Order not found.")
    if order.status != LicenseOrderStatus.FULFILLED or not order.license_text:
        raise AppError("The licence file is not ready yet.", code="not_ready", status_code=409)
    filename = f"uptivora-{str(order.license_id)[:8]}.uptivora-license"
    return Response(
        order.license_text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- payment provider webhooks --------------------------------------------------------------


async def record_webhook_event(
    db, provider: str, event_id: str, event_type: str, payload: dict
) -> bool:
    """Store an incoming event once. Returns False for duplicates (already processed)."""
    result = await db.execute(
        insert(WebhookEvent)
        .values(
            id=uuid.uuid4(),
            provider=provider,
            event_id=event_id[:255],
            event_type=event_type[:100],
            payload=payload,
        )
        .on_conflict_do_nothing(constraint="uq_webhook_events_provider_event")
    )
    return bool(result.rowcount)


@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request, db: DB, settings: AppSettings) -> dict:
    """Ready for the real integration; inactive while the Stripe provider is disabled."""
    if settings.billing_provider != "stripe":
        raise NotFound("Not found.")
    payload = await request.body()
    try:
        verify_stripe_signature(
            payload,
            request.headers.get("stripe-signature", ""),
            settings.stripe_webhook_secret.get_secret_value(),
        )
    except WebhookSignatureError as exc:
        raise AppError("Invalid signature.", code="bad_signature", status_code=400) from exc
    event = json.loads(payload)
    is_new = await record_webhook_event(
        db, "stripe", str(event.get("id", "")), str(event.get("type", "")), event
    )
    await db.commit()
    return {"received": True, "duplicate": not is_new}
