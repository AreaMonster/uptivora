from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, String, Text, false, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKey


class InstalledLicense(UUIDPrimaryKey, Base):
    """Self-hosted: licence files installed through the admin UI.

    The raw signed text is stored and **re-verified on every load**; the parsed columns are
    only a cache for display. Editing them in the database grants nothing.
    """

    __tablename__ = "installed_licenses"
    __table_args__ = (
        Index(
            "uq_installed_licenses_one_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    license_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    edition: Mapped[str] = mapped_column(String(32))
    licensee_name: Mapped[str] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    installed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    installed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255))
    pid: Mapped[int]
    version: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    checks_total: Mapped[int] = mapped_column(BigInteger, default=0)
    checks_failed: Mapped[int] = mapped_column(BigInteger, default=0)
    in_flight: Mapped[int] = mapped_column(default=0)
    network_held: Mapped[bool] = mapped_column(default=False, server_default=false())


class AuditLog(Base):
    """Security-relevant actions (logins, admin changes, plan edits, licence installs)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class SystemEvent(Base):
    """Operational log shown in the admin dashboard (worker errors, SMTP failures, ...)."""

    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    level: Mapped[str] = mapped_column(String(10))  # debug|info|warning|error|critical
    source: Mapped[str] = mapped_column(String(32))  # api|worker|mailer|scheduler|...
    message: Mapped[str] = mapped_column(String(1000))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class AppSetting(Base):
    """Admin-editable runtime settings (e.g. public sign-up on/off). Never secrets."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class RateLimitBucket(Base):
    """Fixed-window rate-limit counters. UNLOGGED in the migration: fast, loss on crash is fine."""

    __tablename__ = "rate_limit_buckets"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(primary_key=True)
    count: Mapped[int] = mapped_column(default=0)
