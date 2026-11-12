"""Notification preferences, alert contacts, test alerts, delivery log and unsubscribe."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.auth.deps import DB, AppSettings, CurrentUser
from app.auth.service import normalize_email
from app.core import ratelimit
from app.core.audit import audit
from app.core.errors import AppError, Conflict, NotFound
from app.core.requestctx import client_ip
from app.core.security import generate_token, hash_token
from app.models import (
    MAX_ALERT_CONTACTS,
    AlertContact,
    NotificationKind,
    NotificationOutbox,
    NotificationSettings,
    User,
)
from app.notifications import templates
from app.notifications.outbox import enqueue
from app.notifications.recipients import alert_recipients, recipient_key, verify_unsubscribe_token

router = APIRouter(tags=["notifications"])
CONFIRM_TTL = timedelta(hours=48)


# --- preferences ----------------------------------------------------------------------------


class NotificationPrefs(BaseModel):
    notify_down: bool = True
    notify_recovery: bool = True
    notify_ssl: bool = True
    ssl_warning_days: int = Field(default=14, ge=1, le=90)
    send_to_account_email: bool = True


@router.get("/api/account/notifications")
async def get_prefs(ctx: CurrentUser, db: DB) -> NotificationPrefs:
    prefs = await db.get(NotificationSettings, ctx.user.id)
    if prefs is None:
        return NotificationPrefs()
    return NotificationPrefs(
        notify_down=prefs.notify_down,
        notify_recovery=prefs.notify_recovery,
        notify_ssl=prefs.notify_ssl,
        ssl_warning_days=prefs.ssl_warning_days,
        send_to_account_email=prefs.send_to_account_email,
    )


@router.put("/api/account/notifications")
async def put_prefs(body: NotificationPrefs, ctx: CurrentUser, db: DB) -> NotificationPrefs:
    prefs = await db.get(NotificationSettings, ctx.user.id)
    if prefs is None:
        prefs = NotificationSettings(user_id=ctx.user.id)
        db.add(prefs)
    for key, value in body.model_dump().items():
        setattr(prefs, key, value)
    await db.commit()
    return body


# --- alert contacts -------------------------------------------------------------------------


class ContactIn(BaseModel):
    email: EmailStr


class ContactPatch(BaseModel):
    is_enabled: bool


def _contact_out(c: AlertContact) -> dict:
    return {
        "id": str(c.id),
        "email": c.email,
        "is_enabled": c.is_enabled,
        "status": "confirmed" if c.verified_at else "pending",
        "verified_at": c.verified_at.isoformat() if c.verified_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


async def _owned_contact(db, ctx, contact_id: uuid.UUID) -> AlertContact:
    contact = await db.scalar(
        select(AlertContact).where(
            AlertContact.id == contact_id, AlertContact.user_id == ctx.user.id
        )
    )
    if contact is None:
        raise NotFound("Alert contact not found.")
    return contact


async def _send_confirmation(db, settings, owner: User, contact: AlertContact) -> None:
    token = generate_token()
    contact.confirm_token_hash = hash_token(token)
    contact.confirm_expires_at = datetime.now(UTC) + CONFIRM_TTL
    mail = templates.confirm_alert_contact(
        owner.email, f"{settings.public_origin}/confirm-alerts#{token}"
    )
    await enqueue(
        db,
        kind=NotificationKind.ACCOUNT,
        recipient=contact.email,
        subject=mail.subject,
        body_text=mail.text,
        body_html=mail.html,
        dedupe_key=f"contact-confirm:{contact.id}:{hash_token(token).hex()[:16]}",
        user_id=owner.id,
    )


@router.get("/api/account/alert-contacts")
async def list_contacts(ctx: CurrentUser, db: DB) -> list[dict]:
    rows = (
        await db.scalars(
            select(AlertContact)
            .where(AlertContact.user_id == ctx.user.id)
            .order_by(AlertContact.created_at)
        )
    ).all()
    return [_contact_out(c) for c in rows]


@router.post("/api/account/alert-contacts", status_code=status.HTTP_201_CREATED)
async def add_contact(
    body: ContactIn, ctx: CurrentUser, request: Request, db: DB, settings: AppSettings
) -> dict:
    email = normalize_email(body.email)
    if email == ctx.user.email:
        raise AppError(
            "This is your account email — use the switch above instead.",
            status_code=422,
            fields={"email": "Already your account email"},
        )
    await ratelimit.hit("contact-add", str(ctx.user.id), limit=10, window_seconds=86400)
    count = await db.scalar(
        select(func.count()).select_from(AlertContact).where(AlertContact.user_id == ctx.user.id)
    )
    if count >= MAX_ALERT_CONTACTS:
        raise Conflict(f"You can add up to {MAX_ALERT_CONTACTS} alert contacts.")
    if await db.scalar(
        select(AlertContact.id).where(
            AlertContact.user_id == ctx.user.id, AlertContact.email == email
        )
    ):
        raise Conflict("This address is already in your list.", fields={"email": "Already added"})
    contact = AlertContact(user_id=ctx.user.id, email=email)
    db.add(contact)
    await db.flush()
    await _send_confirmation(db, settings, ctx.user, contact)
    audit(
        db,
        "alert_contact.add",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="alert_contact",
        target_id=contact.id,
    )
    await db.commit()
    await db.refresh(contact)
    return _contact_out(contact)


@router.post("/api/account/alert-contacts/{contact_id}/resend", status_code=202)
async def resend_confirmation(
    contact_id: uuid.UUID, ctx: CurrentUser, db: DB, settings: AppSettings
) -> dict:
    contact = await _owned_contact(db, ctx, contact_id)
    if contact.verified_at is not None:
        return {"status": "already_confirmed"}
    await ratelimit.hit("contact-resend", str(contact.id), limit=3, window_seconds=86400)
    await _send_confirmation(db, settings, ctx.user, contact)
    await db.commit()
    return {"status": "sent"}


@router.patch("/api/account/alert-contacts/{contact_id}")
async def patch_contact(
    contact_id: uuid.UUID, body: ContactPatch, ctx: CurrentUser, db: DB
) -> dict:
    contact = await _owned_contact(db, ctx, contact_id)
    contact.is_enabled = body.is_enabled
    await db.commit()
    return _contact_out(contact)


@router.delete("/api/account/alert-contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: uuid.UUID, ctx: CurrentUser, db: DB) -> Response:
    contact = await _owned_contact(db, ctx, contact_id)
    await db.delete(contact)
    await db.commit()
    return Response(status_code=204)


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@router.post("/api/alert-contacts/confirm")
async def confirm_contact(body: TokenIn, request: Request, db: DB) -> dict:
    """Public: the recipient (not necessarily an Uptivora user) confirms via the email link."""
    await ratelimit.hit("contact-confirm", client_ip(request), limit=30, window_seconds=3600)
    contact = await db.scalar(
        select(AlertContact)
        .where(
            AlertContact.confirm_token_hash == hash_token(body.token),
            AlertContact.confirm_expires_at > func.now(),
        )
        .with_for_update()
    )
    if contact is None:
        raise AppError("This confirmation link is invalid or has expired.", code="invalid_token")
    contact.verified_at = datetime.now(UTC)
    contact.is_enabled = True
    contact.confirm_token_hash = None
    contact.confirm_expires_at = None
    await db.commit()
    return {"status": "confirmed", "email": contact.email}


# --- unsubscribe (public, signed links) ----------------------------------------------------


class UnsubscribeIn(BaseModel):
    k: Literal["a", "c"]
    id: uuid.UUID
    t: str = Field(min_length=10, max_length=64)


async def _unsubscribe(db, settings, data: UnsubscribeIn) -> str:
    if data.k == "c":
        contact = await db.get(AlertContact, data.id)
        if contact is None or not verify_unsubscribe_token(
            settings, "c", contact.id, contact.email, data.t
        ):
            raise AppError("This unsubscribe link is invalid.", code="invalid_token")
        # The recipient's opt-out sticks: the owner must invite again and it must be re-confirmed.
        contact.is_enabled = False
        contact.verified_at = None
        email = contact.email
    else:
        user = await db.get(User, data.id)
        if user is None or not verify_unsubscribe_token(settings, "a", user.id, user.email, data.t):
            raise AppError("This unsubscribe link is invalid.", code="invalid_token")
        prefs = await db.get(NotificationSettings, user.id)
        if prefs is None:
            prefs = NotificationSettings(user_id=user.id)
            db.add(prefs)
        prefs.send_to_account_email = False
        email = user.email
    await db.commit()
    return email


@router.post("/api/notifications/unsubscribe")
async def unsubscribe(request: Request, db: DB, settings: AppSettings) -> dict:
    """Accepts JSON from our unsubscribe page, or an RFC 8058 one-click POST from a mail client
    (parameters in the query string, body ``List-Unsubscribe=One-Click``)."""
    await ratelimit.hit("unsubscribe", client_ip(request), limit=60, window_seconds=3600)
    params = dict(request.query_params)
    if not params and request.headers.get("content-type", "").startswith("application/json"):
        params = await request.json()
    try:
        data = UnsubscribeIn.model_validate(params)
    except ValueError as exc:
        raise AppError("This unsubscribe link is invalid.", code="invalid_token") from exc
    email = await _unsubscribe(db, settings, data)
    return {"status": "unsubscribed", "email": email}


# --- test alert & delivery log --------------------------------------------------------------


@router.post("/api/account/notifications/test", status_code=202)
async def send_test_alert(ctx: CurrentUser, db: DB, settings: AppSettings) -> dict:
    recipients = await alert_recipients(db, settings, ctx.user)
    if not recipients:
        raise Conflict(
            "No confirmed recipients yet. Confirm your email or an alert contact first.",
            code="no_recipients",
        )
    await ratelimit.hit("test-alert", str(ctx.user.id), limit=5, window_seconds=3600)
    batch = uuid.uuid4().hex[:12]
    for r in recipients:
        mail = templates.alert_test_email(
            ctx.user.email, f"{settings.public_origin}/dashboard", r.footer
        )
        await enqueue(
            db,
            kind=NotificationKind.TEST,
            recipient=r.email,
            subject=mail.subject,
            body_text=mail.text,
            body_html=mail.html,
            headers=mail.headers or None,
            dedupe_key=f"test:{batch}:{recipient_key(r.email)}",
            user_id=ctx.user.id,
        )
    await db.commit()
    return {"status": "queued", "recipients": [r.email for r in recipients]}


@router.get("/api/account/notifications/log")
async def delivery_log(ctx: CurrentUser, db: DB, limit: int = 50) -> list[dict]:
    rows = (
        await db.scalars(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.user_id == ctx.user.id,
                NotificationOutbox.kind != NotificationKind.ACCOUNT,
            )
            .order_by(NotificationOutbox.created_at.desc())
            .limit(min(max(limit, 1), 200))
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "recipient": r.recipient,
            "subject": r.subject,
            "status": r.status,
            "attempts": r.attempts,
            "last_error": r.last_error,
            "created_at": r.created_at.isoformat(),
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "incident_id": str(r.incident_id) if r.incident_id else None,
            "monitor_id": str(r.monitor_id) if r.monitor_id else None,
        }
        for r in rows
    ]
