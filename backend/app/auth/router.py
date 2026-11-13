from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import text

from app.auth import service
from app.auth.deps import DB, AppSettings, CurrentUser
from app.core import ratelimit
from app.core.audit import audit
from app.core.errors import AppError, Conflict, Forbidden, Unauthorized
from app.core.requestctx import client_ip, user_agent
from app.core.security import (
    PasswordPolicyError,
    check_password_policy,
    hash_password,
    verify_password,
)
from app.limits import instance_limits, limits_for, monitor_usage
from app.models import AppSetting, AuthTokenPurpose, UserRole

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --- schemas --------------------------------------------------------------------------------


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)
    full_name: str = Field(default="", max_length=120)

    @field_validator("full_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return " ".join(v.split())


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetPasswordIn(TokenIn):
    password: str = Field(max_length=256)


def _check_policy(password: str, email: str) -> None:
    try:
        check_password_policy(password, email=email)
    except PasswordPolicyError as exc:
        raise AppError(
            str(exc), code="weak_password", status_code=422, fields={"password": str(exc)}
        ) from exc


def _set_session_cookie(response: Response, settings, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_absolute_days * 86400,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response, settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


async def me_payload(db, settings, ctx: service.AuthContext) -> dict:
    user = ctx.user
    limits = await limits_for(db, settings, user)
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value if hasattr(user.role, "value") else user.role,
            "email_verified": user.email_verified_at is not None,
            "timezone": user.timezone,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "csrf_token": ctx.session.csrf_token,
        "limits": limits.to_dict(),
        "usage": {"active_monitors": await monitor_usage(db, user, limits)},
    }


async def _registration_allowed(db, settings) -> tuple[bool, str]:
    """Hosted: open sign-up. Self-hosted: first user becomes admin; then admin-controlled."""
    if settings.is_hosted:
        return True, UserRole.USER
    # Serialise self-hosted sign-ups until commit: two people opening a fresh installation at
    # the same moment must not both become administrator, nor exceed the licence's user limit.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('uptivora.registration'))"))
    if await service.count_users(db) == 0:
        return True, UserRole.ADMIN
    setting = await db.get(AppSetting, "public_signup")
    if not (setting and setting.value is True):
        return False, UserRole.USER
    limits = await instance_limits(db, settings)
    if limits.max_users is not None and await service.count_users(db) >= limits.max_users:
        return False, UserRole.USER
    return True, UserRole.USER


# --- endpoints ------------------------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn, request: Request, response: Response, db: DB, settings: AppSettings
) -> dict:
    ip = client_ip(request)
    await ratelimit.hit("register:ip", ip, limit=5, window_seconds=3600)
    email = service.normalize_email(body.email)
    _check_policy(body.password, email)

    allowed, role = await _registration_allowed(db, settings)
    if not allowed:
        raise Forbidden(
            "Registration is closed. Ask your administrator for an account.",
            code="registration_closed",
        )
    if await service.get_user_by_email(db, email):
        raise Conflict(
            "An account with this email address already exists.",
            fields={"email": "Already registered — try signing in instead."},
        )

    user = await service.create_user(
        db, email=email, password=body.password, full_name=body.full_name, role=role
    )
    await service.send_verification_email(db, settings, user)
    token, session = await service.create_session(
        db, settings, user, ip=ip, user_agent=user_agent(request)
    )
    user.last_login_at = datetime.now(UTC)
    audit(db, "user.register", actor_id=user.id, ip=ip, target_type="user", target_id=user.id)
    await db.commit()
    await db.refresh(user)
    _set_session_cookie(response, settings, token)
    return await me_payload(db, settings, service.AuthContext(user, session))


@router.post("/login")
async def login(
    body: LoginIn, request: Request, response: Response, db: DB, settings: AppSettings
) -> dict:
    ip = client_ip(request)
    email = service.normalize_email(body.email)
    await ratelimit.hit("login:ip", ip, limit=30, window_seconds=300)
    await ratelimit.hit("login:email", email, limit=10, window_seconds=900)

    user = await service.get_user_by_email(db, email)
    valid, needs_rehash = verify_password(body.password, user.password_hash if user else None)
    if not user or not valid:
        audit(db, "auth.login_failed", actor_id=user.id if user else None, ip=ip)
        await db.commit()
        raise Unauthorized("Incorrect email or password.", code="invalid_credentials")
    if not user.is_active:
        raise Forbidden(
            "This account has been suspended. Please contact support.", code="account_suspended"
        )
    if needs_rehash:
        user.password_hash = hash_password(body.password)
    user.last_login_at = datetime.now(UTC)
    token, session = await service.create_session(
        db, settings, user, ip=ip, user_agent=user_agent(request)
    )
    audit(db, "auth.login", actor_id=user.id, ip=ip)
    await db.commit()
    _set_session_cookie(response, settings, token)
    return await me_payload(db, settings, service.AuthContext(user, session))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(ctx: CurrentUser, response: Response, db: DB, settings: AppSettings) -> None:
    ctx.session.revoked_at = datetime.now(UTC)
    await db.commit()
    _clear_session_cookie(response, settings)


@router.get("/me")
async def me(ctx: CurrentUser, db: DB, settings: AppSettings) -> dict:
    return await me_payload(db, settings, ctx)


@router.post("/verify-email")
async def verify_email(body: TokenIn, request: Request, db: DB) -> dict:
    await ratelimit.hit("verify:ip", client_ip(request), limit=20, window_seconds=3600)
    user = await service.consume_token(db, body.token, AuthTokenPurpose.VERIFY_EMAIL)
    if user is None:
        raise AppError("This confirmation link is invalid or has expired.", code="invalid_token")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    audit(db, "user.email_verified", actor_id=user.id, ip=client_ip(request))
    await db.commit()
    return {"status": "verified"}


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(ctx: CurrentUser, db: DB, settings: AppSettings) -> dict:
    if ctx.user.email_verified_at is not None:
        return {"status": "already_verified"}
    await ratelimit.hit("resend-verify", str(ctx.user.id), limit=3, window_seconds=3600)
    await service.send_verification_email(db, settings, ctx.user)
    await db.commit()
    return {"status": "sent"}


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(body: EmailIn, request: Request, db: DB, settings: AppSettings) -> dict:
    email = service.normalize_email(body.email)
    await ratelimit.hit("forgot:ip", client_ip(request), limit=10, window_seconds=3600)
    await ratelimit.hit("forgot:email", email, limit=3, window_seconds=3600)
    user = await service.get_user_by_email(db, email)
    if user and user.is_active:
        await service.send_password_reset_email(db, settings, user)
        audit(db, "auth.password_reset_requested", actor_id=user.id, ip=client_ip(request))
        await db.commit()
    # Same response whether or not the account exists (no user enumeration).
    return {"status": "If an account exists for this address, we sent a reset link."}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordIn, request: Request, db: DB, settings: AppSettings
) -> dict:
    await ratelimit.hit("reset:ip", client_ip(request), limit=20, window_seconds=3600)
    user = await service.consume_token(db, body.token, AuthTokenPurpose.RESET_PASSWORD)
    if user is None:
        raise AppError("This reset link is invalid or has expired.", code="invalid_token")
    _check_policy(body.password, user.email)
    user.password_hash = hash_password(body.password)
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)  # they proved control of the inbox
    await service.revoke_sessions(db, user.id)
    await service.send_password_changed_email(db, settings, user)
    audit(db, "auth.password_reset", actor_id=user.id, ip=client_ip(request))
    await db.commit()
    return {"status": "password_changed"}


class AcceptInviteIn(TokenIn):
    password: str = Field(max_length=256)
    full_name: str = Field(default="", max_length=120)


@router.post("/accept-invite")
async def accept_invite(
    body: AcceptInviteIn, request: Request, response: Response, db: DB, settings: AppSettings
) -> dict:
    """Self-hosted invitations: choose a password, confirm the email and sign in."""
    from app.selfhosted.invites import is_pending

    ip = client_ip(request)
    await ratelimit.hit("invite:ip", ip, limit=20, window_seconds=3600)
    user = await service.consume_token(db, body.token, AuthTokenPurpose.INVITE)
    if user is None or not is_pending(user):
        raise AppError("This invitation is invalid, expired or already used.", code="invalid_token")
    _check_policy(body.password, user.email)
    user.password_hash = hash_password(body.password)
    if body.full_name.strip():
        user.full_name = " ".join(body.full_name.split())
    user.email_verified_at = datetime.now(UTC)  # the link proved control of the inbox
    user.last_login_at = datetime.now(UTC)
    token, session = await service.create_session(
        db, settings, user, ip=ip, user_agent=user_agent(request)
    )
    audit(
        db, "user.invite_accepted", actor_id=user.id, ip=ip, target_type="user", target_id=user.id
    )
    await db.commit()
    _set_session_cookie(response, settings, token)
    return await me_payload(db, settings, service.AuthContext(user, session))
