"""Database-level invariants enforced by the schema itself (requires PostgreSQL)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import (
    Incident,
    LicenseProduct,
    Monitor,
    NotificationKind,
    NotificationOutbox,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
)


@pytest.fixture
async def db(migrated_db_url: str):
    engine = create_async_engine(migrated_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def _user(db: AsyncSession, email: str | None = None) -> User:
    user = User(email=email or f"u{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    db.add(user)
    await db.flush()
    return user


async def _monitor(db: AsyncSession, owner: User, **kw) -> Monitor:
    m = Monitor(owner_id=owner.id, name="Site", url="https://example.com/", **kw)
    db.add(m)
    await db.flush()
    return m


async def _expect_integrity_error(db: AsyncSession, coro) -> None:
    sp = await db.begin_nested()
    with pytest.raises(IntegrityError):
        await coro
    await sp.rollback()


async def test_seed_catalogue(db: AsyncSession) -> None:
    seeded = ("starter", "pro", "business")  # other tests may add plans
    plans = (
        await db.scalars(select(Plan).where(Plan.code.in_(seeded)).order_by(Plan.sort_order))
    ).all()
    assert [(p.code, p.price_cents, p.max_monitors, p.currency) for p in plans] == [
        ("starter", 500, 3, "CHF"),
        ("pro", 1200, 15, "CHF"),
        ("business", 2500, 50, "CHF"),
    ]
    products = (await db.scalars(select(LicenseProduct).order_by(LicenseProduct.sort_order))).all()
    assert [(p.code, p.price_cents) for p in products] == [
        ("selfhosted-starter", 9900),
        ("selfhosted-professional", 19900),
    ]


async def test_email_must_be_lowercase(db: AsyncSession) -> None:
    await _expect_integrity_error(db, _user(db, "Mixed@Example.com"))


async def test_email_unique(db: AsyncSession) -> None:
    await _user(db, "dup@example.com")
    await _expect_integrity_error(db, _user(db, "dup@example.com"))


async def test_monitor_defaults_and_interval_floor(db: AsyncSession) -> None:
    owner = await _user(db)
    m = await _monitor(db, owner)
    await db.refresh(m)
    assert m.status == "pending" and m.next_check_at is not None and m.interval_seconds == 300
    await _expect_integrity_error(db, _monitor(db, owner, interval_seconds=10))
    await _expect_integrity_error(db, _monitor(db, owner, timeout_seconds=120))


async def test_only_one_open_incident_per_monitor(db: AsyncSession) -> None:
    owner = await _user(db)
    m = await _monitor(db, owner)
    now = datetime.now(UTC)
    db.add(
        Incident(
            monitor_id=m.id,
            started_at=now - timedelta(hours=2),
            resolved_at=now - timedelta(hours=1),
        )
    )
    db.add(Incident(monitor_id=m.id, started_at=now))
    await db.flush()  # one resolved + one open: fine

    async def second_open():
        db.add(Incident(monitor_id=m.id, started_at=now))
        await db.flush()

    await _expect_integrity_error(db, second_open())


async def test_outbox_dedupe_key_prevents_duplicate_alerts(db: AsyncSession) -> None:
    owner = await _user(db)

    def alert() -> NotificationOutbox:
        return NotificationOutbox(
            user_id=owner.id,
            kind=NotificationKind.MONITOR_DOWN,
            recipient=owner.email,
            subject="Down",
            body_text="x",
            dedupe_key=f"incident:{owner.id}:down",
        )

    db.add(alert())
    await db.flush()

    async def again():
        db.add(alert())
        await db.flush()

    await _expect_integrity_error(db, again())


async def test_one_live_subscription_per_user(db: AsyncSession) -> None:
    owner = await _user(db)
    plan = await db.scalar(select(Plan).where(Plan.code == "pro"))
    now = datetime.now(UTC)

    def sub(status: SubscriptionStatus) -> Subscription:
        return Subscription(
            user_id=owner.id,
            plan_id=plan.id,
            status=status,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            provider="test",
            is_test=True,
        )

    db.add(sub(SubscriptionStatus.EXPIRED))
    db.add(sub(SubscriptionStatus.ACTIVE))
    await db.flush()

    async def second_live():
        db.add(sub(SubscriptionStatus.PAST_DUE))
        await db.flush()

    await _expect_integrity_error(db, second_live())


async def test_enum_values_enforced_by_check_constraint(db: AsyncSession) -> None:
    owner = await _user(db)
    m = await _monitor(db, owner)
    sp = await db.begin_nested()
    with pytest.raises(IntegrityError):
        await db.execute(text("UPDATE monitors SET status = 'bogus' WHERE id = :id"), {"id": m.id})
    await sp.rollback()


async def test_user_delete_cascades_to_monitors(db: AsyncSession) -> None:
    owner = await _user(db)
    await _monitor(db, owner)
    await db.delete(owner)
    await db.flush()
    count = await db.scalar(
        select(func.count()).select_from(Monitor).where(Monitor.owner_id == owner.id)
    )
    assert count == 0


async def test_rate_limit_table_is_unlogged(db: AsyncSession) -> None:
    persistence = await db.scalar(
        text("SELECT relpersistence::text FROM pg_class WHERE relname = 'rate_limit_buckets'")
    )
    assert persistence == "u"
