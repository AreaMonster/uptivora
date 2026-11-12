"""Authentication domain logic: users, sessions, single-use email tokens."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import generate_token, hash_password, hash_token
from app.models import AuthToken, AuthTokenPurpose, NotificationKind, NotificationSettings, User
from app.models import Session as UserSession
from app.notifications import templates
from app.notifications.outbox import enqueue

SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
TOKEN_TTL = {
    AuthTokenPurpose.VERIFY_EMAIL: timedelta(hours=48),
    AuthTokenPurpose.RESET_PASSWORD: timedelta(hours=1),
    AuthTokenPurpose.INVITE: timedelta(days=7),
}


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(slots=True)
class AuthContext:
    user: User
    session: UserSession


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == normalize_email(email)))


async def create_user(
    db: AsyncSession, *, email: str, password: str, full_name: str = "", role: str = "user"
) -> User:
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        role=role,
    )
    db.add(user)
    await db.flush()
    db.add(NotificationSettings(user_id=user.id))
    await db.flush()
    return user


async def count_users(db: AsyncSession) -> int:
    return int(await db.scalar(select(func.count()).select_from(User)) or 0)


# --- sessions -------------------------------------------------------------------------------


async def create_session(
    db: AsyncSession, settings: Settings, user: User, *, ip: str | None, user_agent: str | None
) -> tuple[str, UserSession]:
    token = generate_token()
    now = datetime.now(UTC)
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=generate_token(24),
        expires_at=now + timedelta(days=settings.session_absolute_days),
        last_seen_at=now,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(session)
    await db.flush()
    return token, session


async def resolve_session(db: AsyncSession, settings: Settings, token: str) -> AuthContext | None:
    if not token or len(token) > 200:
        return None
    now = datetime.now(UTC)
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.token_hash == hash_token(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
                UserSession.last_seen_at > now - timedelta(days=settings.session_idle_days),
                User.is_active.is_(True),
            )
        )
    ).first()
    if row is None:
        return None
    session, user = row
    if now - session.last_seen_at > SESSION_TOUCH_INTERVAL:
        session.last_seen_at = now
        await db.commit()
    return AuthContext(user=user, session=session)


async def revoke_sessions(
    db: AsyncSession, user_id: uuid.UUID, *, except_session_id: uuid.UUID | None = None
) -> None:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    if except_session_id is not None:
        stmt = stmt.where(UserSession.id != except_session_id)
    await db.execute(stmt)


# --- single-use email tokens ---------------------------------------------------------------


async def issue_token(db: AsyncSession, user: User, purpose: AuthTokenPurpose) -> str:
    # Invalidate older unused tokens of the same purpose: only the newest link works.
    await db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=func.now())
    )
    token = generate_token()
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + TOKEN_TTL[purpose],
        )
    )
    await db.flush()
    return token


async def consume_token(db: AsyncSession, token: str, purpose: AuthTokenPurpose) -> User | None:
    if not token or len(token) > 200:
        return None
    row = await db.scalar(
        select(AuthToken)
        .where(
            AuthToken.token_hash == hash_token(token),
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.expires_at > func.now(),
        )
        .with_for_update()
    )
    if row is None:
        return None
    row.used_at = datetime.now(UTC)
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return user


# --- account emails ------------------------------------------------------------------------


async def send_verification_email(db: AsyncSession, settings: Settings, user: User) -> None:
    token = await issue_token(db, user, AuthTokenPurpose.VERIFY_EMAIL)
    mail = templates.verify_email(user.full_name, f"{settings.public_origin}/verify-email#{token}")
    await enqueue(
        db,
        kind=NotificationKind.ACCOUNT,
        recipient=user.email,
        subject=mail.subject,
        body_text=mail.text,
        body_html=mail.html,
        dedupe_key=f"verify:{user.id}:{hash_token(token).hex()[:16]}",
        user_id=user.id,
    )


async def send_password_reset_email(db: AsyncSession, settings: Settings, user: User) -> None:
    token = await issue_token(db, user, AuthTokenPurpose.RESET_PASSWORD)
    mail = templates.reset_password(
        user.full_name, f"{settings.public_origin}/reset-password#{token}"
    )
    await enqueue(
        db,
        kind=NotificationKind.ACCOUNT,
        recipient=user.email,
        subject=mail.subject,
        body_text=mail.text,
        body_html=mail.html,
        dedupe_key=f"reset:{user.id}:{hash_token(token).hex()[:16]}",
        user_id=user.id,
    )


async def send_password_changed_email(db: AsyncSession, settings: Settings, user: User) -> None:
    mail = templates.password_changed(user.full_name, f"{settings.public_origin}/forgot-password")
    await enqueue(
        db,
        kind=NotificationKind.ACCOUNT,
        recipient=user.email,
        subject=mail.subject,
        body_text=mail.text,
        body_html=mail.html,
        dedupe_key=f"pwchanged:{user.id}:{uuid.uuid4().hex}",
        user_id=user.id,
    )
