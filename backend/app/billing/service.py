"""Subscription lifecycle. All money movements go through a :class:`PaymentProvider`.

Rules
* New subscription: charged the full monthly price, period = one calendar month.
* Upgrade (more expensive plan): immediate; the price difference for the rest of the current
  period is charged (prorated). A cancelled subscription is reactivated by an upgrade.
* Downgrade (same or cheaper plan): scheduled for the end of the period, no charge.
* Cancel: keeps working until the period ends, then expires. Resume is possible until then.
* Renewal: charged at period end. On failure the subscription becomes past due and keeps
  working for ``PAST_DUE_GRACE`` while payment is retried daily; then it expires.
* Whenever limits change, monitors over the limit are paused (newest first, never deleted) and
  monitors paused for that reason are resumed again when there is room.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.billing.providers import ChargeResult, Simulation, get_provider
from app.core.config import Settings
from app.core.errors import AppError, Conflict
from app.limits import PAST_DUE_GRACE, limits_for, live_subscription
from app.models import (
    NotificationKind,
    Payment,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.notifications import templates
from app.notifications.outbox import enqueue

log = logging.getLogger("uptivora.billing")

RETRY_INTERVAL = timedelta(hours=24)
Action = Literal["subscribe", "upgrade", "downgrade", "none"]


class PaymentDeclined(AppError):
    status_code = 402
    code = "payment_declined"


def add_month(dt: datetime) -> datetime:
    month = dt.month % 12 + 1
    year = dt.year + (1 if dt.month == 12 else 0)
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def prorate(old_cents: int, new_cents: int, start: datetime, end: datetime, now: datetime) -> int:
    """Charge for the rest of the period at the price difference (never negative)."""
    total = (end - start).total_seconds()
    remaining = max(0.0, min(1.0, (end - now).total_seconds() / total)) if total > 0 else 0.0
    return max(0, round((new_cents - old_cents) * remaining))


def money(cents: int, currency: str) -> str:
    return f"{currency} {cents / 100:.2f}"


def ensure_billing(settings: Settings) -> None:
    if not settings.is_hosted:
        raise AppError(
            "Billing is not available in the self-hosted edition.",
            code="not_found",
            status_code=404,
        )
    if settings.billing_provider == "disabled":
        raise AppError(
            "Online payments are not enabled yet. Please contact support.",
            code="billing_disabled",
            status_code=409,
        )


@dataclass(frozen=True, slots=True)
class Quote:
    action: Action
    amount_cents: int
    currency: str
    effective_at: datetime
    plan: Plan
    current_plan: Plan | None


async def quote(db: AsyncSession, user: User, plan: Plan, now: datetime | None = None) -> Quote:
    now = now or datetime.now(UTC)
    found = await live_subscription(db, user.id)
    if found is None:
        return Quote("subscribe", plan.price_cents, plan.currency, now, plan, None)
    sub, current = found
    if current.id == plan.id:
        return Quote("none", 0, plan.currency, now, plan, current)
    if plan.price_cents > current.price_cents:
        amount = prorate(
            current.price_cents,
            plan.price_cents,
            sub.current_period_start,
            sub.current_period_end,
            now,
        )
        return Quote("upgrade", amount, plan.currency, now, plan, current)
    return Quote("downgrade", 0, plan.currency, sub.current_period_end, plan, current)


async def _charge(
    db: AsyncSession,
    settings: Settings,
    user: User,
    *,
    amount_cents: int,
    currency: str,
    description: str,
    simulate: Simulation,
    subscription_id=None,
    license_order_id=None,
) -> tuple[ChargeResult, Payment]:
    provider = get_provider(settings.billing_provider)
    result = await provider.charge(
        amount_cents=amount_cents,
        currency=currency,
        description=description,
        customer_ref=str(user.id),
        simulate=simulate,
    )
    payment = Payment(
        user_id=user.id,
        subscription_id=subscription_id,
        license_order_id=license_order_id,
        amount_cents=amount_cents,
        currency=currency,
        status=PaymentStatus.SUCCEEDED if result.ok else PaymentStatus.FAILED,
        provider=provider.name,
        provider_payment_id=result.provider_payment_id,
        is_test=provider.is_test,
        description=description[:255],
    )
    db.add(payment)
    await db.flush()
    return result, payment


async def _email(db: AsyncSession, user: User, mail: templates.RenderedEmail, key: str) -> None:
    await enqueue(
        db,
        kind=NotificationKind.ACCOUNT,
        recipient=user.email,
        subject=mail.subject,
        body_text=mail.text,
        body_html=mail.html,
        dedupe_key=key,
        user_id=user.id,
    )


def _fmt(dt: datetime, user: User) -> str:
    from app.engine.alerts import format_local

    return format_local(dt, user.timezone)


async def _lock_user(db: AsyncSession, user: User) -> None:
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())


async def change_plan(
    db: AsyncSession, settings: Settings, user: User, plan: Plan, simulate: Simulation = "success"
) -> dict:
    """Subscribe, upgrade or schedule a downgrade. Commits on success."""
    ensure_billing(settings)
    if not plan.is_active:
        raise AppError("This plan is not available.", code="plan_unavailable", status_code=422)
    await _lock_user(db, user)
    now = datetime.now(UTC)
    q = await quote(db, user, plan, now)
    link = f"{settings.public_origin}/billing"

    if q.action == "none":
        found = await live_subscription(db, user.id)
        if found and found[0].pending_plan_id:  # choosing the current plan undoes a downgrade
            found[0].pending_plan_id = None
            await db.commit()
        return {"action": "none", "charged_cents": 0}

    if q.action == "subscribe":
        result, payment = await _charge(
            db,
            settings,
            user,
            amount_cents=q.amount_cents,
            currency=q.currency,
            description=f"{plan.name} plan — first month",
            simulate=simulate,
        )
        if not result.ok:
            await db.commit()  # keep the failed payment record
            raise PaymentDeclined(result.error or "Payment declined.")
        sub = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=add_month(now),
            provider=payment.provider,
            is_test=payment.is_test,
            last_payment_attempt_at=now,
        )
        db.add(sub)
        await db.flush()
        payment.subscription_id = sub.id
        await _email(
            db,
            user,
            templates.billing_receipt(
                plan.name,
                money(q.amount_cents, q.currency),
                "First month",
                _fmt(sub.current_period_end, user),
                link,
                payment.is_test,
            ),
            f"receipt:{payment.id}",
        )
        await rebalance_monitors(db, settings, user)
        await db.commit()
        return {"action": "subscribe", "charged_cents": q.amount_cents}

    sub, current = await live_subscription(db, user.id)  # type: ignore[misc]
    if sub.status == SubscriptionStatus.PAST_DUE:
        raise Conflict(
            "Your last payment failed. Please retry it before changing plans.", code="past_due"
        )

    if q.action == "upgrade":
        if q.amount_cents > 0:
            result, payment = await _charge(
                db,
                settings,
                user,
                amount_cents=q.amount_cents,
                currency=q.currency,
                description=f"Upgrade {current.name} → {plan.name} (prorated)",
                simulate=simulate,
                subscription_id=sub.id,
            )
            if not result.ok:
                await db.commit()
                raise PaymentDeclined(result.error or "Payment declined.")
            await _email(
                db,
                user,
                templates.billing_receipt(
                    plan.name,
                    money(q.amount_cents, q.currency),
                    "Upgrade (rest of current period)",
                    _fmt(sub.current_period_end, user),
                    link,
                    payment.is_test,
                ),
                f"receipt:{payment.id}",
            )
        sub.plan_id = plan.id
        sub.pending_plan_id = None
        sub.status = SubscriptionStatus.ACTIVE
        sub.cancel_at_period_end = False
        sub.cancelled_at = None
        await db.flush()
        await rebalance_monitors(db, settings, user)
        await db.commit()
        return {"action": "upgrade", "charged_cents": q.amount_cents}

    # downgrade
    if sub.status == SubscriptionStatus.CANCELLED:
        raise Conflict(
            "Resume your subscription before scheduling a plan change.", code="cancelled"
        )
    sub.pending_plan_id = plan.id
    await db.commit()
    return {
        "action": "downgrade",
        "charged_cents": 0,
        "effective_at": sub.current_period_end.isoformat(),
    }


async def cancel(db: AsyncSession, settings: Settings, user: User) -> Subscription:
    ensure_billing(settings)
    await _lock_user(db, user)
    found = await live_subscription(db, user.id)
    if found is None:
        raise Conflict("You have no active subscription.", code="no_subscription")
    sub, _ = found
    if sub.status == SubscriptionStatus.PAST_DUE:
        # Nothing more will be charged; access ends now.
        await _expire(db, settings, user, sub, notify=False)
    else:
        sub.status = SubscriptionStatus.CANCELLED
        sub.cancel_at_period_end = True
        sub.cancelled_at = datetime.now(UTC)
        sub.pending_plan_id = None
    await db.commit()
    return sub


async def resume(db: AsyncSession, settings: Settings, user: User) -> Subscription:
    ensure_billing(settings)
    await _lock_user(db, user)
    found = await live_subscription(db, user.id)
    if found is None or found[0].status != SubscriptionStatus.CANCELLED:
        raise Conflict("There is no cancelled subscription to resume.", code="not_cancelled")
    sub, _ = found
    sub.status = SubscriptionStatus.ACTIVE
    sub.cancel_at_period_end = False
    sub.cancelled_at = None
    await db.commit()
    return sub


async def cancel_pending_change(db: AsyncSession, settings: Settings, user: User) -> None:
    ensure_billing(settings)
    found = await live_subscription(db, user.id)
    if found and found[0].pending_plan_id:
        found[0].pending_plan_id = None
        await db.commit()


async def assign_manual(
    db: AsyncSession, settings: Settings, user: User, plan: Plan, months: int
) -> Subscription:
    """Admin: complimentary / offline-invoiced plan. No charge, provider ``manual``."""
    await _lock_user(db, user)
    now = datetime.now(UTC)
    found = await live_subscription(db, user.id)
    if found:
        await _expire(db, settings, user, found[0], notify=False, rebalance=False)
        await db.flush()
    end = now
    for _ in range(months):
        end = add_month(end)
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.CANCELLED,
        cancel_at_period_end=True,
        current_period_start=now,
        current_period_end=end,
        provider="manual",
        is_test=False,
    )
    db.add(sub)
    await db.flush()
    await rebalance_monitors(db, settings, user)
    return sub


# --- renewals & expiry (worker job) ---------------------------------------------------------


async def _expire(
    db: AsyncSession,
    settings: Settings,
    user: User,
    sub: Subscription,
    *,
    notify: bool = True,
    rebalance: bool = True,
) -> None:
    sub.status = SubscriptionStatus.EXPIRED
    sub.cancel_at_period_end = False
    sub.pending_plan_id = None
    await db.flush()
    if rebalance:
        await rebalance_monitors(db, settings, user)
    if notify:
        plan = await db.get(Plan, sub.plan_id)
        await _email(
            db,
            user,
            templates.billing_subscription_ended(
                plan.name if plan else "your", f"{settings.public_origin}/billing", sub.is_test
            ),
            f"expired:{sub.id}",
        )


async def renew(
    db: AsyncSession,
    settings: Settings,
    sub: Subscription,
    now: datetime,
    *,
    force: bool = False,
    simulate: Simulation | None = None,
) -> str:
    """Process one due subscription. Returns what happened.

    ``force`` skips the daily retry spacing (user clicked "retry now"); ``simulate`` overrides
    the stored TEST MODE outcome for this one attempt."""
    user = await db.get(User, sub.user_id)
    if user is None:
        return "skipped"
    link = f"{settings.public_origin}/billing"
    if sub.status == SubscriptionStatus.CANCELLED:
        await _expire(db, settings, user, sub, notify=sub.provider != "manual")
        return "expired"
    if sub.status == SubscriptionStatus.PAST_DUE:
        if now > sub.current_period_end + PAST_DUE_GRACE:
            await _expire(db, settings, user, sub)
            return "expired"
        recent = sub.last_payment_attempt_at and now - sub.last_payment_attempt_at < RETRY_INTERVAL
        if recent and not force:
            return "waiting"
    if sub.pending_plan_id:  # scheduled downgrade takes effect with the new period
        sub.plan_id = sub.pending_plan_id
        sub.pending_plan_id = None
    plan = await db.get(Plan, sub.plan_id)
    if settings.billing_provider == "disabled" or plan is None:
        await _expire(db, settings, user, sub)
        return "expired"
    result, payment = await _charge(
        db,
        settings,
        user,
        amount_cents=plan.price_cents,
        currency=plan.currency,
        description=f"{plan.name} plan — renewal",
        simulate=simulate or ("decline" if sub.simulate_failure else "success"),
        subscription_id=sub.id,
    )
    sub.last_payment_attempt_at = now
    if result.ok:
        new_start = sub.current_period_end
        sub.current_period_start = new_start
        sub.current_period_end = add_month(new_start)
        while sub.current_period_end <= now:  # long outage of the worker: catch up
            sub.current_period_end = add_month(sub.current_period_end)
        sub.status = SubscriptionStatus.ACTIVE
        await _email(
            db,
            user,
            templates.billing_receipt(
                plan.name,
                money(plan.price_cents, plan.currency),
                "Monthly renewal",
                _fmt(sub.current_period_end, user),
                link,
                payment.is_test,
            ),
            f"receipt:{payment.id}",
        )
        await rebalance_monitors(db, settings, user)
        return "renewed"
    sub.status = SubscriptionStatus.PAST_DUE
    await _email(
        db,
        user,
        templates.billing_payment_failed(
            plan.name,
            money(plan.price_cents, plan.currency),
            _fmt(sub.current_period_end + PAST_DUE_GRACE, user),
            link,
            payment.is_test,
        ),
        f"payment-failed:{payment.id}",
    )
    await rebalance_monitors(db, settings, user)  # e.g. a downgrade applied above
    return "past_due"


async def retry_payment(
    db: AsyncSession, settings: Settings, user: User, simulate: Simulation = "success"
) -> str:
    ensure_billing(settings)
    await _lock_user(db, user)
    found = await live_subscription(db, user.id)
    if found is None or found[0].status != SubscriptionStatus.PAST_DUE:
        raise Conflict("There is no failed payment to retry.", code="not_past_due")
    sub = found[0]
    outcome = await renew(db, settings, sub, datetime.now(UTC), force=True, simulate=simulate)
    await db.commit()
    if outcome != "renewed":
        raise PaymentDeclined("The payment was declined again.")
    return outcome


async def process_due_subscriptions(
    maker: async_sessionmaker[AsyncSession], settings: Settings
) -> dict[str, int]:
    """Worker job: renew, retry or expire every subscription whose period has ended."""
    now = datetime.now(UTC)
    stats: dict[str, int] = {}
    async with maker() as db:
        due_ids = (
            await db.scalars(
                select(Subscription.id)
                .where(
                    Subscription.status.in_(
                        [
                            SubscriptionStatus.ACTIVE,
                            SubscriptionStatus.CANCELLED,
                            SubscriptionStatus.PAST_DUE,
                        ]
                    ),
                    Subscription.current_period_end <= now,
                )
                .limit(500)
            )
        ).all()
    for sub_id in due_ids:
        async with maker() as db, db.begin():
            sub = await db.scalar(
                select(Subscription)
                .where(Subscription.id == sub_id)
                .with_for_update(skip_locked=True)
            )
            if sub is None or sub.current_period_end > now:
                continue
            try:
                outcome = await renew(db, settings, sub, now)
            except Exception:
                log.exception("Renewal of subscription %s failed", sub_id)
                raise
            stats[outcome] = stats.get(outcome, 0) + 1
    if stats:
        log.info("Billing run: %s", stats)
    return stats


# --- keep monitors within the plan ----------------------------------------------------------


async def rebalance_monitors(db: AsyncSession, settings: Settings, user: User) -> dict[str, int]:
    """Keep the user's monitors within their plan (see :mod:`app.enforcement`)."""
    from app.enforcement import enforce_limits

    limits = await limits_for(db, settings, user)
    return await enforce_limits(db, limits, owner_id=user.id if limits.scope == "user" else None)


async def payment_history(db: AsyncSession, user: User, limit: int = 24) -> list[Payment]:
    return list(
        (
            await db.scalars(
                select(Payment)
                .where(Payment.user_id == user.id)
                .order_by(Payment.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
