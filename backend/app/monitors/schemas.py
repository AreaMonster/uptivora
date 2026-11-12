from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import HttpMethod, MonitorStatus, PausedReason
from app.monitors.status_spec import normalize_status_spec

INTERVAL_CHOICES = (30, 60, 120, 300, 600, 900, 1800, 3600)


def _clean_name(v: str) -> str:
    v = " ".join(v.split())
    if not v:
        raise ValueError("Name is required")
    return v


class MonitorFields(BaseModel):
    method: HttpMethod = HttpMethod.GET
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    expected_status: str = Field(default="200-399", max_length=64)
    keyword: str | None = Field(default=None, max_length=200)
    follow_redirects: bool = True
    verify_tls: bool = True
    down_threshold: int = Field(default=2, ge=1, le=10)
    recovery_threshold: int = Field(default=1, ge=1, le=10)
    ssl_check_enabled: bool = True
    ssl_warning_days: int = Field(default=14, ge=1, le=90)
    notifications_enabled: bool = True


class MonitorCreate(MonitorFields):
    name: str = Field(max_length=120)
    url: str = Field(max_length=2048)
    interval_seconds: int = Field(default=300, ge=30, le=86400)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return _clean_name(v)

    @field_validator("expected_status")
    @classmethod
    def _status(cls, v: str) -> str:
        return normalize_status_spec(v)

    @field_validator("keyword")
    @classmethod
    def _keyword(cls, v: str | None) -> str | None:
        return (v.strip() or None) if v is not None else None

    @model_validator(mode="after")
    def _consistency(self) -> MonitorCreate:
        if self.timeout_seconds >= self.interval_seconds:
            raise ValueError("Timeout must be shorter than the check interval")
        if self.keyword and self.method == HttpMethod.HEAD:
            raise ValueError("Keyword checks need the GET method (HEAD has no body)")
        return self


class MonitorUpdate(BaseModel):
    """PATCH: only provided fields change."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    url: str | None = Field(default=None, max_length=2048)
    interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    method: HttpMethod | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    expected_status: str | None = Field(default=None, max_length=64)
    keyword: str | None = Field(default=None, max_length=200)
    follow_redirects: bool | None = None
    verify_tls: bool | None = None
    down_threshold: int | None = Field(default=None, ge=1, le=10)
    recovery_threshold: int | None = Field(default=None, ge=1, le=10)
    ssl_check_enabled: bool | None = None
    ssl_warning_days: int | None = Field(default=None, ge=1, le=90)
    notifications_enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return _clean_name(v) if v is not None else None

    @field_validator("expected_status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        return normalize_status_spec(v) if v is not None else None


class MonitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    method: HttpMethod
    interval_seconds: int
    timeout_seconds: int
    expected_status: str
    keyword: str | None
    follow_redirects: bool
    verify_tls: bool
    down_threshold: int
    recovery_threshold: int
    notifications_enabled: bool
    ssl_check_enabled: bool
    ssl_warning_days: int
    is_paused: bool
    paused_reason: PausedReason | None
    status: MonitorStatus
    last_checked_at: datetime | None
    last_status_change_at: datetime | None
    last_response_ms: int | None
    last_status_code: int | None
    last_error: str | None
    ssl_expires_at: datetime | None
    ssl_issuer: str | None
    ssl_error: str | None
    created_at: datetime
    uptime_24h: float | None = None


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    monitor_id: uuid.UUID
    started_at: datetime
    resolved_at: datetime | None
    cause: str
    error_kind: str | None
    status_code: int | None
    duration_seconds: int | None = None
