"""Invitations (self-hosted): an administrator adds a colleague by email.

The invited account exists immediately (so it counts against the licence's user limit) but
has no usable password until the invitation link is accepted. The password hash then starts
with ``PENDING``, which is not a valid Argon2 hash, so the account cannot sign in.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import get_user_by_email, issue_token, normalize_email
from app.core.config import Settings
from app.core.errors import AppError, Conflict, NotFound
from app.core.security import generate_token, hash_token
from app.limits import instance_limits
from app.models import AuthTokenPurpose, NotificationKind, NotificationSettings, User, UserRole
from app.notifications import templates
from app.notifications.outbox import enqueue

PENDING = "!pending-invitation:"


def is_pending(user: User) -> bool:
    return user.password_hash.startswith(PENDING)


async def ensure_user_capacity(db: AsyncSession, settings: Settings) -> None:
    limits = await instance_limits(db, settings)
    users = int(await db.scalar(select(func.count()).select_from(User)) or 0)
    if limits.max_users is not None and users >= limits.max_users:
        raise AppError(
            f"Your licence allows {limits.max_users} user account(s). Remove an account or "
            "upgrade the licence to add more.",
            code="user_limit",
            status_code=402,
        )


async def send_invite(db: AsyncSession, settings: Settings, inviter: User, user: User) -> None:
    token = await issue_token(db, user, AuthTokenPurpose.INVITE)
    mail = templates.invitation(
        inviter.full_name or inviter.email, f"{settings.public_origin}/accept-invite#{token}"
    )
    await enqueue(
        db,
        kind=NotificationKind.ACCOUNT,
        recipient=user.email,
        subject=mail.subject,
        body_text=mail.text,
        body_html=mail.html,
        dedupe_key=f"invite:{user.id}:{hash_token(token).hex()[:16]}",
        user_id=user.id,
    )


async def invite(
    db: AsyncSession, settings: Settings, inviter: User, email: str, role: UserRole
) -> User:
    email = normalize_email(email)
    if await get_user_by_email(db, email):
        raise Conflict(
            "An account with this email already exists.", fields={"email": "Already has an account"}
        )
    await ensure_user_capacity(db, settings)
    user = User(email=email, password_hash=PENDING + generate_token(8), role=role)
    db.add(user)
    await db.flush()
    db.add(NotificationSettings(user_id=user.id))
    await send_invite(db, settings, inviter, user)
    return user


async def pending_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None or not is_pending(user):
        raise NotFound("Invitation not found.")
    return user
