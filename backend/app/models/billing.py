"""Hosted-edition commerce: subscription plans, subscriptions, payments, licence sales.

Self-hosted installations create these tables (one schema for both editions) but never use them.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey, str_enum


class BillingInterval(enum.StrEnum):
    MONTH = "month"
    YEAR = "year"


class Plan(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="price_non_negative"),
        CheckConstraint("max_monitors >= 1", name="max_monitors_positive"),
        CheckConstraint("min_interval_seconds >= 30", name="min_interval_floor"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso"),
    )

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(500), default="")
    price_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), default="CHF")
    interval: Mapped[BillingInterval] = mapped_column(
        str_enum(BillingInterval, "billing_interval"), default=BillingInterval.MONTH
    )
    max_monitors: Mapped[int]
    min_interval_seconds: Mapped[int]
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True)  # can be subscribed to
    is_public: Mapped[bool] = mapped_column(default=True)  # shown on pricing page
    sort_order: Mapped[int] = mapped_column(default=0)


class SubscriptionStatus(enum.StrEnum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"  # user cancelled; stays usable until current_period_end
    EXPIRED = "expired"  # period ended without renewal


LIVE_SUBSCRIPTION_STATUSES = (
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAST_DUE,
    SubscriptionStatus.CANCELLED,
)


class Subscription(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        # One live subscription per user.
        Index(
            "uq_subscriptions_one_live_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'past_due', 'cancelled')"),
        ),
        Index("ix_subscriptions_period_end", "current_period_end"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    status: Mapped[SubscriptionStatus] = mapped_column(
        str_enum(SubscriptionStatus, "subscription_status")
    )
    current_period_start: Mapped[datetime]
    current_period_end: Mapped[datetime]
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False)
    cancelled_at: Mapped[datetime | None]
    # Downgrades are scheduled for the period end.
    pending_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(32))  # "test" | "manual" | "stripe"
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255))
    is_test: Mapped[bool]
    # TEST MODE only: make the next simulated renewal charge fail (ignored by real providers).
    simulate_failure: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    last_payment_attempt_at: Mapped[datetime | None]


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(UUIDPrimaryKey, Base):
    """Payment record. ``is_test`` rows come from the TEST MODE simulator: no money moved."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="amount_non_negative"),
        UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_ref"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    license_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("license_orders.id", ondelete="SET NULL")
    )
    amount_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[PaymentStatus] = mapped_column(str_enum(PaymentStatus, "payment_status"))
    provider: Mapped[str] = mapped_column(String(32))
    provider_payment_id: Mapped[str | None] = mapped_column(String(255))
    is_test: Mapped[bool]
    description: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class LicenseProduct(UUIDPrimaryKey, Timestamps, Base):
    """A self-hosted licence product sold on the hosted site (e.g. Starter CHF 99 one-time)."""

    __tablename__ = "license_products"
    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="price_non_negative"),
        CheckConstraint("edition IN ('starter', 'professional')", name="edition_valid"),
    )

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(500), default="")
    edition: Mapped[str] = mapped_column(String(32))
    price_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3), default="CHF")
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)


class LicenseOrderStatus(enum.StrEnum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"  # awaiting offline signing by an operator
    FULFILLED = "fulfilled"  # signed licence attached, customer can download
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class LicenseOrder(UUIDPrimaryKey, Base):
    __tablename__ = "license_orders"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("license_products.id", ondelete="RESTRICT")
    )
    status: Mapped[LicenseOrderStatus] = mapped_column(
        str_enum(LicenseOrderStatus, "license_order_status")
    )
    price_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3))
    is_test: Mapped[bool]
    licensee_name: Mapped[str] = mapped_column(String(200))
    licensee_email: Mapped[str] = mapped_column(String(254))
    license_id: Mapped[uuid.UUID | None] = mapped_column(unique=True)
    license_text: Mapped[str | None] = mapped_column(Text)  # signed file (public data, no key)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    paid_at: Mapped[datetime | None]
    fulfilled_at: Mapped[datetime | None]


class WebhookEvent(UUIDPrimaryKey, Base):
    """Idempotency log for payment-provider webhooks (each event processed once)."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event"),
    )

    provider: Mapped[str] = mapped_column(String(32))
    event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    processed_at: Mapped[datetime | None]
