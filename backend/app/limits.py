"""Usage limits — the single place where the two editions differ for the core product.

* Hosted: limits come from the user's live subscription plan (per user).
* Self-hosted: limits come from the installed licence (per installation).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.licensing import UNLICENSED_LIMITS
from app.models import Monitor, Plan, Subscription, SubscriptionStatus, User, UserRole
from app.models.billing import LIVE_SUBSCRIPTION_STATUSES
from app.models.monitors import ENGINE_MIN_INTERVAL_SECONDS
from app.selfhosted.licence import licence_status

NO_PLAN_MIN_INTERVAL = 300
# Past-due subscriptions keep working this long after the period ended (payment retries).
PAST_DUE_GRACE = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class Limits:
    max_monitors: int | None  # None = unlimited
    min_interval_seconds: int
    max_users: int | None
    scope: Literal["user", "instance"]
    source: Literal["plan", "no_plan", "admin", "licence", "unlicensed"]
    plan_code: str | None = None
    plan_name: str | None = None
    licensee: str | None = None
    edition: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _unlimited_if_zero(value: int) -> int | None:
    return None if value == 0 else value


async def live_subscription(db: AsyncSession, user_id) -> tuple[Subscription, Plan] | None:
    row = (
        await db.execute(
            select(Subscription, Plan)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(
                Subscription.user_id == user_id,
                Subscription.status.in_(LIVE_SUBSCRIPTION_STATUSES),
                or_(
                    Subscription.current_period_end > datetime.now(UTC),
                    and_(
                        Subscription.status == SubscriptionStatus.PAST_DUE,
                        Subscription.current_period_end > datetime.now(UTC) - PAST_DUE_GRACE,
                    ),
                ),
            )
        )
    ).first()
    return (row[0], row[1]) if row else None


async def limits_for(db: AsyncSession, settings: Settings, user: User) -> Limits:
    if settings.is_hosted:
        if user.role == UserRole.ADMIN:
            return Limits(None, ENGINE_MIN_INTERVAL_SECONDS, None, "user", "admin")
        found = await live_subscription(db, user.id)
        if found is None:
            return Limits(0, NO_PLAN_MIN_INTERVAL, 1, "user", "no_plan")
        _, plan = found
        return Limits(
            plan.max_monitors, plan.min_interval_seconds, 1, "user", "plan", plan.code, plan.name
        )

    return await instance_limits(db, settings)


async def instance_limits(db: AsyncSession, settings: Settings) -> Limits:
    """Self-hosted: limits of the whole installation, from the installed licence."""
    status = await licence_status(db, settings)
    if status.licence is None:
        lim = UNLICENSED_LIMITS
        return Limits(
            lim.max_monitors, lim.min_interval_seconds, lim.max_users, "instance", "unlicensed"
        )
    lic = status.licence
    return Limits(
        _unlimited_if_zero(lic.limits.max_monitors),
        lic.limits.min_interval_seconds,
        _unlimited_if_zero(lic.limits.max_users),
        "instance",
        "licence",
        licensee=lic.licensee_name,
        edition=lic.edition.value,
    )


async def monitor_usage(db: AsyncSession, user: User, limits: Limits) -> int:
    stmt = select(func.count()).select_from(Monitor).where(Monitor.is_paused.is_(False))
    if limits.scope == "user":
        stmt = stmt.where(Monitor.owner_id == user.id)
    return int(await db.scalar(stmt) or 0)


async def lock_usage_scope(db: AsyncSession, user: User, limits: Limits) -> None:
    """Serialise limit checks so two parallel requests cannot both pass the last free slot."""
    if limits.scope == "user":
        await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    else:
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('uptivora.monitor-limit'))"))
