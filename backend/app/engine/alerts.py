"""Queue alert emails for monitor events, respecting user preferences.

Alerts are written to the outbox inside the same transaction as the state change, with a
deterministic ``dedupe_key`` — a crash or retry can never produce a second email.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Incident, Monitor, NotificationKind, NotificationSettings, User
from app.notifications import templates
from app.notifications.outbox import enqueue


def format_local(dt: datetime, tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 — unknown zone → UTC
        tz = ZoneInfo("UTC")
    return dt.astimezone(tz).strftime("%d %b %Y, %H:%M %Z")


async def _recipient(
    db: AsyncSession,
    monitor: Monitor,
    pref: Literal["notify_down", "notify_recovery", "notify_ssl"],
) -> tuple[User, str] | None:
    if not monitor.notifications_enabled:
        return None
    user = await db.get(User, monitor.owner_id)
    # Only confirmed addresses receive alerts (prevents abuse to spam arbitrary inboxes).
    if user is None or not user.is_active or user.email_verified_at is None:
        return None
    prefs = await db.get(NotificationSettings, user.id)
    if prefs is not None and not getattr(prefs, pref):
        return None
    return user, user.email


async def queue_down_alert(
    db: AsyncSession, settings: Settings, monitor: Monitor, incident: Incident
) -> bool:
    found = await _recipient(db, monitor, "notify_down")
    if not found:
        return False
    user, email = found
    link = f"{settings.public_origin}/monitors/{monitor.id}"
    mail = templates.monitor_down(
        monitor.name,
        monitor.url,
        incident.cause or "Unreachable",
        format_local(incident.started_at, user.timezone),
        link,
    )
    return await enqueue(
        db,
        kind=NotificationKind.MONITOR_DOWN,
        recipient=email,
        subject=mail.subject,
        body_text=mail.text,
        body_html=mail.html,
        dedupe_key=f"incident:{incident.id}:down",
        user_id=user.id,
        monitor_id=monitor.id,
        incident_id=incident.id,
    )


async def queue_up_alert(
    db: AsyncSession, settings: Settings, monitor: Monitor, incident: Incident
) -> bool:
    found = await _recipient(db, monitor, "notify_recovery")
    if not found or incident.resolved_at is None:
        return False
    user, email = found
    link = f"{settings.public_origin}/monitors/{monitor.id}"
    duration = int((incident.resolved_at - incident.started_at).total_seconds())
    mail = templates.monitor_up(monitor.name, monitor.url, duration, incident.cause, link)
    return await enqueue(
        db,
        kind=NotificationKind.MONITOR_UP,
        recipient=email,
        subject=mail.subject,
        body_text=mail.text,
        body_html=mail.html,
        dedupe_key=f"incident:{incident.id}:up",
        user_id=user.id,
        monitor_id=monitor.id,
        incident_id=incident.id,
    )


async def queue_ssl_alert(
    db: AsyncSession, settings: Settings, monitor: Monitor, *, days_left: int, bucket: str
) -> bool:
    found = await _recipient(db, monitor, "notify_ssl")
    if not found or monitor.ssl_expires_at is None:
        return False
    user, email = found
    link = f"{settings.public_origin}/monitors/{monitor.id}"
    mail = templates.ssl_expiring(
        monitor.name,
        monitor.url,
        days_left,
        format_local(monitor.ssl_expires_at, user.timezone),
        link,
    )
    key = f"ssl:{monitor.id}:{monitor.ssl_expires_at:%Y%m%d}:{bucket}"
    return await enqueue(
        db,
        kind=NotificationKind.SSL_EXPIRING,
        recipient=email,
        subject=mail.subject,
        body_text=mail.text,
        body_html=mail.html,
        dedupe_key=key,
        user_id=user.id,
        monitor_id=monitor.id,
    )
