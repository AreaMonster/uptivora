"""Queue alert emails for monitor events.

* Written to the outbox in the same transaction as the state change.
* One email per event and recipient, enforced by a deterministic ``dedupe_key``.
* Respects per-monitor mute and per-user preferences; only confirmed addresses receive alerts.
* Flapping protection: a monitor that opens more than ``FLAP_LIMIT`` incidents within an hour
  stops emailing until it calms down (incidents are still recorded).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Incident, Monitor, NotificationKind, NotificationSettings, SystemEvent, User
from app.notifications import templates
from app.notifications.outbox import enqueue
from app.notifications.recipients import Recipient, alert_recipients, recipient_key

log = logging.getLogger("uptivora.alerts")

FLAP_LIMIT = 5
FLAP_WINDOW = timedelta(hours=1)
Pref = Literal["notify_down", "notify_recovery", "notify_ssl"]


def format_local(dt: datetime, tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 — unknown zone → UTC
        tz = ZoneInfo("UTC")
    return dt.astimezone(tz).strftime("%d %b %Y, %H:%M %Z")


async def _audience(
    db: AsyncSession, settings: Settings, monitor: Monitor, pref: Pref
) -> tuple[User, list[Recipient]] | None:
    if not monitor.notifications_enabled:
        return None
    user = await db.get(User, monitor.owner_id)
    if user is None:
        return None
    prefs = await db.get(NotificationSettings, user.id)
    if prefs is not None and not getattr(prefs, pref):
        return None
    recipients = await alert_recipients(db, settings, user)
    return (user, recipients) if recipients else None


async def is_flapping(db: AsyncSession, monitor: Monitor, incident: Incident) -> bool:
    """True if this incident is beyond the per-hour alert budget of its monitor."""
    since = incident.started_at - FLAP_WINDOW
    earlier = await db.scalar(
        select(func.count())
        .select_from(Incident)
        .where(
            Incident.monitor_id == monitor.id,
            Incident.started_at >= since,
            Incident.started_at < incident.started_at,
        )
    )
    return int(earlier or 0) >= FLAP_LIMIT


async def _note_flapping(db: AsyncSession, monitor: Monitor) -> None:
    db.add(
        SystemEvent(
            level="warning",
            source="alerts",
            message=f"Alerts suppressed for flapping monitor {monitor.id}",
            details={"monitor_id": str(monitor.id)},
        )
    )


async def _send_all(
    db: AsyncSession,
    recipients: list[Recipient],
    render,
    *,
    kind: NotificationKind,
    key_prefix: str,
    user: User,
    monitor: Monitor,
    incident: Incident | None = None,
) -> int:
    queued = 0
    for r in recipients:
        mail = render(r)
        if await enqueue(
            db,
            kind=kind,
            recipient=r.email,
            subject=mail.subject,
            body_text=mail.text,
            body_html=mail.html,
            headers=mail.headers or None,
            # The account email keeps the original key format (stable across upgrades, so
            # already-sent alerts are never repeated); extra contacts get a per-address suffix.
            dedupe_key=key_prefix
            if r.contact_id is None
            else f"{key_prefix}:{recipient_key(r.email)}",
            user_id=user.id,
            monitor_id=monitor.id,
            incident_id=incident.id if incident else None,
        ):
            queued += 1
    return queued


async def queue_down_alert(
    db: AsyncSession, settings: Settings, monitor: Monitor, incident: Incident
) -> int:
    audience = await _audience(db, settings, monitor, "notify_down")
    if audience is None:
        return 0
    if await is_flapping(db, monitor, incident):
        await _note_flapping(db, monitor)
        return 0
    user, recipients = audience
    link = f"{settings.public_origin}/incidents/{incident.id}"
    started = format_local(incident.started_at, user.timezone)
    return await _send_all(
        db,
        recipients,
        lambda r: templates.monitor_down(
            monitor.name, monitor.url, incident.cause or "Unreachable", started, link, r.footer
        ),
        kind=NotificationKind.MONITOR_DOWN,
        key_prefix=f"incident:{incident.id}:down",
        user=user,
        monitor=monitor,
        incident=incident,
    )


async def queue_up_alert(
    db: AsyncSession, settings: Settings, monitor: Monitor, incident: Incident
) -> int:
    if incident.resolved_at is None:
        return 0
    audience = await _audience(db, settings, monitor, "notify_recovery")
    if audience is None or await is_flapping(db, monitor, incident):
        return 0
    user, recipients = audience
    link = f"{settings.public_origin}/incidents/{incident.id}"
    duration = int((incident.resolved_at - incident.started_at).total_seconds())
    return await _send_all(
        db,
        recipients,
        lambda r: templates.monitor_up(
            monitor.name, monitor.url, duration, incident.cause, link, r.footer
        ),
        kind=NotificationKind.MONITOR_UP,
        key_prefix=f"incident:{incident.id}:up",
        user=user,
        monitor=monitor,
        incident=incident,
    )


async def queue_ssl_alert(
    db: AsyncSession, settings: Settings, monitor: Monitor, *, days_left: int, bucket: str
) -> int:
    if monitor.ssl_expires_at is None:
        return 0
    audience = await _audience(db, settings, monitor, "notify_ssl")
    if audience is None:
        return 0
    user, recipients = audience
    link = f"{settings.public_origin}/monitors/{monitor.id}"
    expires = format_local(monitor.ssl_expires_at, user.timezone)
    return await _send_all(
        db,
        recipients,
        lambda r: templates.ssl_expiring(
            monitor.name, monitor.url, days_left, expires, link, r.footer
        ),
        kind=NotificationKind.SSL_EXPIRING,
        key_prefix=f"ssl:{monitor.id}:{monitor.ssl_expires_at:%Y%m%d}:{bucket}",
        user=user,
        monitor=monitor,
    )
