"""Personal data export (right of access / data portability, revDSG Art. 25 / GDPR Art. 15, 20).

Everything stored about the signed-in user, as JSON. Secrets are left out (password hash,
session and email-link token hashes, CSRF tokens). Individual check results are not included:
they describe the monitored websites rather than the person and are summarised in the
monitor statistics.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect, or_, select

from app.models import (
    AlertContact,
    AuditLog,
    Incident,
    LicenseOrder,
    Monitor,
    NotificationOutbox,
    NotificationSettings,
    Payment,
    Subscription,
    User,
)
from app.models import Session as UserSession

EXCLUDED = {
    "password_hash",
    "token_hash",
    "csrf_token",
    "confirm_token_hash",
    "lease_owner",
    "lease_until",
    "body_text",
    "body_html",
    "headers",
    "dedupe_key",
}


def _value(v: Any) -> Any:
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, uuid.UUID | Decimal):
        return str(v)
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, bytes):
        return None
    return v


def _row(obj: Any) -> dict[str, Any]:
    return {
        attr.key: _value(getattr(obj, attr.key))
        for attr in inspect(obj).mapper.column_attrs
        if attr.key not in EXCLUDED
    }


async def collect(db, user: User) -> dict[str, Any]:
    async def rows(stmt) -> list[dict[str, Any]]:
        return [_row(o) for o in (await db.scalars(stmt)).all()]

    monitor_ids = select(Monitor.id).where(Monitor.owner_id == user.id)
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "account": _row(user),
        "notification_settings": await rows(
            select(NotificationSettings).where(NotificationSettings.user_id == user.id)
        ),
        "alert_recipients": await rows(select(AlertContact).where(AlertContact.user_id == user.id)),
        "monitors": await rows(
            select(Monitor).where(Monitor.owner_id == user.id).order_by(Monitor.created_at)
        ),
        "incidents": await rows(
            select(Incident)
            .where(Incident.monitor_id.in_(monitor_ids))
            .order_by(Incident.started_at)
        ),
        "emails": await rows(
            select(NotificationOutbox)
            .where(NotificationOutbox.user_id == user.id)
            .order_by(NotificationOutbox.created_at)
        ),
        "sessions": await rows(select(UserSession).where(UserSession.user_id == user.id)),
        "subscriptions": await rows(select(Subscription).where(Subscription.user_id == user.id)),
        "payments": await rows(select(Payment).where(Payment.user_id == user.id)),
        "licence_orders": await rows(select(LicenseOrder).where(LicenseOrder.user_id == user.id)),
        "activity_log": await rows(
            select(AuditLog)
            .where(
                or_(
                    AuditLog.actor_user_id == user.id,
                    (AuditLog.target_type == "user") & (AuditLog.target_id == str(user.id)),
                )
            )
            .order_by(AuditLog.created_at)
        ),
    }
