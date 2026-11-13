from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPrimaryKey, str_enum

# Absolute engine floor; plans/licences impose stricter minimums.
ENGINE_MIN_INTERVAL_SECONDS = 30


class MonitorStatus(enum.StrEnum):
    PENDING = "pending"  # never checked yet
    UP = "up"
    DOWN = "down"
    PAUSED = "paused"


class HttpMethod(enum.StrEnum):
    GET = "GET"
    HEAD = "HEAD"


class PausedReason(enum.StrEnum):
    USER = "user"
    PLAN_LIMIT = "plan_limit"
    ADMIN = "admin"


class Monitor(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "monitors"
    __table_args__ = (
        CheckConstraint(f"interval_seconds >= {ENGINE_MIN_INTERVAL_SECONDS}", name="interval_min"),
        CheckConstraint("interval_seconds <= 86400", name="interval_max"),
        CheckConstraint("timeout_seconds BETWEEN 1 AND 60", name="timeout_range"),
        CheckConstraint("down_threshold BETWEEN 1 AND 10", name="down_threshold_range"),
        CheckConstraint("recovery_threshold BETWEEN 1 AND 10", name="recovery_threshold_range"),
        CheckConstraint("ssl_warning_days BETWEEN 1 AND 90", name="ssl_warning_days_range"),
        # The scheduler's hot path: due, unpaused monitors.
        Index(
            "ix_monitors_due",
            "next_check_at",
            postgresql_where=text("is_paused = false"),
        ),
    )

    __mapper_args__ = {"eager_defaults": True}  # load the generated ``seq`` after INSERT

    # Compact 4-byte key used by the high-volume time-series tables instead of the UUID.
    seq: Mapped[int] = mapped_column(Identity(), unique=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(2048))
    method: Mapped[HttpMethod] = mapped_column(
        str_enum(HttpMethod, "http_method"), default=HttpMethod.GET
    )
    interval_seconds: Mapped[int] = mapped_column(default=300)
    timeout_seconds: Mapped[int] = mapped_column(SmallInteger, default=10)
    expected_status: Mapped[str] = mapped_column(String(64), default="200-399")
    keyword: Mapped[str | None] = mapped_column(String(200))
    follow_redirects: Mapped[bool] = mapped_column(default=True)
    verify_tls: Mapped[bool] = mapped_column(default=True)
    down_threshold: Mapped[int] = mapped_column(SmallInteger, default=2)
    recovery_threshold: Mapped[int] = mapped_column(SmallInteger, default=1)
    notifications_enabled: Mapped[bool] = mapped_column(default=True)

    is_paused: Mapped[bool] = mapped_column(default=False)
    paused_reason: Mapped[PausedReason | None] = mapped_column(
        str_enum(PausedReason, "paused_reason")
    )

    # Live state maintained by the worker
    status: Mapped[MonitorStatus] = mapped_column(
        str_enum(MonitorStatus, "monitor_status"), default=MonitorStatus.PENDING
    )
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    consecutive_successes: Mapped[int] = mapped_column(default=0)
    last_checked_at: Mapped[datetime | None]
    next_check_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_status_change_at: Mapped[datetime | None]
    last_response_ms: Mapped[int | None]
    last_status_code: Mapped[int | None] = mapped_column(SmallInteger)
    last_error: Mapped[str | None] = mapped_column(String(500))

    # Worker lease (crash-safe claim of a due check)
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None]

    # TLS certificate tracking (https monitors only)
    ssl_check_enabled: Mapped[bool] = mapped_column(default=True)
    ssl_warning_days: Mapped[int] = mapped_column(SmallInteger, default=14)
    ssl_expires_at: Mapped[datetime | None]
    ssl_issuer: Mapped[str | None] = mapped_column(String(255))
    ssl_last_checked_at: Mapped[datetime | None]
    ssl_error: Mapped[str | None] = mapped_column(String(500))


class _CheckColumns:
    """Columns shared by recent results and retained (failed / incident) results.

    Deliberately lean: no surrogate id, no worker name, an int monitor key. Rows are never
    updated, so the ORM identity is (monitor_seq, checked_at) without a database constraint.
    """

    monitor_seq: Mapped[int] = mapped_column(
        ForeignKey("monitors.seq", ondelete="CASCADE"), primary_key=True
    )
    checked_at: Mapped[datetime] = mapped_column(primary_key=True, server_default=func.now())
    is_up: Mapped[bool]
    status_code: Mapped[int | None] = mapped_column(SmallInteger)
    response_ms: Mapped[int | None]
    error_kind: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(String(500))


class CheckResult(_CheckColumns, Base):
    """Every check of the last ``raw_retention_days`` (3 by default).

    Partitioned by day (``check_results_pYYYYMMDD`` plus a default partition), created ahead
    of time by the worker and dropped whole when they expire — see engine.partitions. The
    primary key below exists only in the ORM; the database has a plain index instead.
    """

    __tablename__ = "check_results"
    __table_args__ = (
        Index("ix_check_results_monitor_time", "monitor_seq", text("checked_at DESC")),
        Index("ix_check_results_checked_at", "checked_at", postgresql_using="brin"),
        {"postgresql_partition_by": "RANGE (checked_at)"},
    )


class RetainedCheck(_CheckColumns, Base):
    """Failed checks, and the checks around each incident, kept ``failed_check_retention_days``
    (30) after their day partition of ``check_results`` has been dropped."""

    __tablename__ = "retained_checks"
    __table_args__ = (
        Index("ix_retained_checks_monitor_time", "monitor_seq", text("checked_at DESC")),
        Index("ix_retained_checks_checked_at", "checked_at"),
    )


class CheckRollup(Base):
    """Hourly aggregates used for 7/30/90-day uptime and latency charts (400 days)."""

    __tablename__ = "check_rollups"
    __table_args__ = (Index("ix_check_rollups_bucket_start", "bucket_start"),)

    monitor_seq: Mapped[int] = mapped_column(
        ForeignKey("monitors.seq", ondelete="CASCADE"), primary_key=True
    )
    bucket_start: Mapped[datetime] = mapped_column(primary_key=True)
    checks_total: Mapped[int]
    checks_up: Mapped[int]
    response_ms_avg: Mapped[int | None]
    response_ms_min: Mapped[int | None]
    response_ms_max: Mapped[int | None]
    response_ms_p95: Mapped[int | None]


class Incident(UUIDPrimaryKey, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        # At most one open incident per monitor — the core of "no duplicate outages".
        Index(
            "uq_incidents_one_open_per_monitor",
            "monitor_id",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
        Index("ix_incidents_monitor_started", "monitor_id", text("started_at DESC")),
        Index("ix_incidents_started_at", "started_at"),
    )

    monitor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    started_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]
    cause: Mapped[str] = mapped_column(String(500), default="")
    error_kind: Mapped[str | None] = mapped_column(String(32))
    status_code: Mapped[int | None] = mapped_column(SmallInteger)
    # Team workflow: someone acknowledges the outage and can leave a note.
    acknowledged_at: Mapped[datetime | None]
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
