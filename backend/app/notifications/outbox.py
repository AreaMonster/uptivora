"""Transactional email outbox.

``enqueue`` writes into the caller's transaction, so an email exists if and only if the
state change that caused it was committed. ``drain_outbox`` (run by the worker) delivers.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import NotificationKind, NotificationOutbox, OutboxStatus
from app.notifications.mailer import EmailMessageData, MailerError, send_email

log = logging.getLogger("uptivora.mailer")

MAX_ATTEMPTS = 10
SENDING_LEASE = timedelta(minutes=10)


async def enqueue(
    db: AsyncSession,
    *,
    kind: NotificationKind,
    recipient: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    dedupe_key: str,
    user_id: uuid.UUID | None = None,
    monitor_id: uuid.UUID | None = None,
    incident_id: uuid.UUID | None = None,
) -> bool:
    """Queue an email. Returns False if an email with ``dedupe_key`` was already queued."""
    stmt = (
        insert(NotificationOutbox)
        .values(
            id=uuid.uuid4(),
            kind=kind,
            recipient=recipient,
            subject=subject[:255],
            body_text=body_text,
            body_html=body_html,
            dedupe_key=dedupe_key[:200],
            user_id=user_id,
            monitor_id=monitor_id,
            incident_id=incident_id,
            status=OutboxStatus.PENDING,
            attempts=0,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )
    result = await db.execute(stmt)
    return bool(result.rowcount)


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(60 * 2 ** max(attempts - 1, 0), 6 * 3600))


async def drain_outbox(
    maker: async_sessionmaker[AsyncSession], settings: Settings, *, batch: int = 20
) -> int:
    """Send due emails. Safe to run from several workers concurrently. Returns #sent."""
    now = datetime.now(UTC)
    async with maker() as db, db.begin():
        rows = (
            await db.scalars(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.status.in_([OutboxStatus.PENDING, OutboxStatus.SENDING]),
                    NotificationOutbox.next_attempt_at <= now,
                )
                .order_by(NotificationOutbox.next_attempt_at)
                .limit(batch)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in rows:  # lease: if we crash, another worker retries after SENDING_LEASE
            row.status = OutboxStatus.SENDING
            row.attempts += 1
            row.next_attempt_at = now + SENDING_LEASE
        claimed = [
            (r.id, r.attempts, r.recipient, r.subject, r.body_text, r.body_html) for r in rows
        ]

    sent = 0
    for row_id, attempts, recipient, subject, text_body, html_body in claimed:
        values: dict
        try:
            await send_email(settings, EmailMessageData(recipient, subject, text_body, html_body))
        except MailerError as exc:
            final = attempts >= MAX_ATTEMPTS
            log.warning("Email %s to %s failed (attempt %s): %s", row_id, recipient, attempts, exc)
            values = {
                "status": OutboxStatus.FAILED if final else OutboxStatus.PENDING,
                "last_error": str(exc)[:500],
                "next_attempt_at": datetime.now(UTC) + backoff(attempts),
            }
        else:
            sent += 1
            values = {"status": OutboxStatus.SENT, "sent_at": datetime.now(UTC), "last_error": None}
        async with maker() as db, db.begin():
            await db.execute(
                update(NotificationOutbox).where(NotificationOutbox.id == row_id).values(**values)
            )
    return sent
