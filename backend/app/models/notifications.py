from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKey, str_enum


class NotificationSettings(Base):
    """Per-user notification preferences. Security/account emails are always sent."""

    __tablename__ = "notification_settings"
    __table_args__ = (
        CheckConstraint("ssl_warning_days BETWEEN 1 AND 90", name="ssl_warning_days_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    notify_down: Mapped[bool] = mapped_column(default=True)
    notify_recovery: Mapped[bool] = mapped_column(default=True)
    notify_ssl: Mapped[bool] = mapped_column(default=True)
    ssl_warning_days: Mapped[int] = mapped_column(SmallInteger, default=14)
    alert_email: Mapped[str | None] = mapped_column(String(254))  # defaults to account email
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class NotificationKind(enum.StrEnum):
    MONITOR_DOWN = "monitor_down"
    MONITOR_UP = "monitor_up"
    SSL_EXPIRING = "ssl_expiring"
    SSL_ERROR = "ssl_error"
    ACCOUNT = "account"


class OutboxStatus(enum.StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"  # gave up after max attempts
    CANCELLED = "cancelled"


class NotificationOutbox(UUIDPrimaryKey, Base):
    """Transactional outbox. ``dedupe_key`` is UNIQUE so an alert can never be queued twice."""

    __tablename__ = "notification_outbox"
    __table_args__ = (
        Index(
            "ix_notification_outbox_due",
            "next_attempt_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    monitor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("monitors.id", ondelete="SET NULL")
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL")
    )
    kind: Mapped[NotificationKind] = mapped_column(str_enum(NotificationKind, "notification_kind"))
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(255))
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[OutboxStatus] = mapped_column(
        str_enum(OutboxStatus, "outbox_status"), default=OutboxStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    sent_at: Mapped[datetime | None]
