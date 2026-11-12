"""Who receives alerts, plus signed one-click unsubscribe links.

Recipients of a user's alerts:
* the account email — if confirmed and ``send_to_account_email`` is on;
* every alert contact that confirmed via its emailed link and is enabled.

Unsubscribe links carry an HMAC (keyed with ``UPTIVORA_SECRET_KEY``) over the target, so no
token has to be stored and links cannot be forged for other addresses.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import AlertContact, NotificationSettings, User
from app.notifications.templates import Footer

UnsubKind = Literal["a", "c"]  # a = account email, c = alert contact


@dataclass(frozen=True, slots=True)
class Recipient:
    email: str
    footer: Footer
    contact_id: uuid.UUID | None = None


def unsubscribe_token(settings: Settings, kind: UnsubKind, target_id: uuid.UUID, email: str) -> str:
    msg = f"unsubscribe:{kind}:{target_id}:{email.lower()}".encode()
    digest = hmac.new(settings.secret_key.get_secret_value().encode(), msg, hashlib.sha256)
    return base64.urlsafe_b64encode(digest.digest()).rstrip(b"=").decode()[:32]


def verify_unsubscribe_token(
    settings: Settings, kind: UnsubKind, target_id: uuid.UUID, email: str, token: str
) -> bool:
    expected = unsubscribe_token(settings, kind, target_id, email)
    return hmac.compare_digest(expected.encode(), (token or "").encode())


def _query(settings: Settings, kind: UnsubKind, target_id: uuid.UUID, email: str) -> str:
    return urlencode(
        {"k": kind, "id": str(target_id), "t": unsubscribe_token(settings, kind, target_id, email)}
    )


def unsubscribe_page_url(
    settings: Settings, kind: UnsubKind, target_id: uuid.UUID, email: str
) -> str:
    # The page asks for a click before unsubscribing, so link scanners can't trigger it.
    return f"{settings.public_origin}/unsubscribe?{_query(settings, kind, target_id, email)}"


def one_click_url(settings: Settings, kind: UnsubKind, target_id: uuid.UUID, email: str) -> str:
    """RFC 8058 endpoint used in the List-Unsubscribe header (mail clients POST to it)."""
    q = _query(settings, kind, target_id, email)
    return f"{settings.public_origin}/api/notifications/unsubscribe?{q}"


def account_footer(settings: Settings, user: User) -> Footer:
    return Footer(
        manage_url=f"{settings.public_origin}/settings#notifications",
        unsubscribe_url=unsubscribe_page_url(settings, "a", user.id, user.email),
        one_click_url=one_click_url(settings, "a", user.id, user.email),
    )


def contact_footer(settings: Settings, owner: User, contact: AlertContact) -> Footer:
    return Footer(
        unsubscribe_url=unsubscribe_page_url(settings, "c", contact.id, contact.email),
        one_click_url=one_click_url(settings, "c", contact.id, contact.email),
        reason=f"You receive this email because {owner.email} added you as an alert "
        "recipient on Uptivora and you confirmed it.",
    )


async def alert_recipients(db: AsyncSession, settings: Settings, user: User) -> list[Recipient]:
    if not user.is_active:
        return []
    prefs = await db.get(NotificationSettings, user.id)
    recipients: list[Recipient] = []
    seen: set[str] = set()
    if user.email_verified_at is not None and (prefs is None or prefs.send_to_account_email):
        recipients.append(Recipient(user.email, account_footer(settings, user)))
        seen.add(user.email)
    contacts = (
        await db.scalars(
            select(AlertContact)
            .where(
                AlertContact.user_id == user.id,
                AlertContact.verified_at.is_not(None),
                AlertContact.is_enabled.is_(True),
            )
            .order_by(AlertContact.created_at)
        )
    ).all()
    for c in contacts:
        if c.email not in seen:
            recipients.append(Recipient(c.email, contact_footer(settings, user, c), c.id))
            seen.add(c.email)
    return recipients


def recipient_key(email: str) -> str:
    """Short stable hash used in outbox dedupe keys (one alert per event AND recipient)."""
    return hashlib.sha256(email.lower().encode()).hexdigest()[:12]
