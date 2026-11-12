"""Account self-service: profile, password, sessions, notification preferences, deletion."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from zoneinfo import available_timezones

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.auth import service
from app.auth.deps import DB, AppSettings, CurrentUser
from app.auth.router import _check_policy, _clear_session_cookie, me_payload
from app.core import ratelimit
from app.core.audit import audit
from app.core.errors import AppError, Conflict, NotFound
from app.core.requestctx import client_ip
from app.core.security import hash_password, verify_password
from app.models import Session as UserSession
from app.models import User, UserRole

router = APIRouter(prefix="/api/account", tags=["account"])
_TIMEZONES = frozenset(available_timezones())


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is not None and v not in _TIMEZONES:
            raise ValueError("Unknown time zone")
        return v


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class DeleteAccountIn(BaseModel):
    password: str = Field(max_length=256)


async def _verify_current_password(user: User, password: str) -> None:
    await ratelimit.hit("reauth", str(user.id), limit=10, window_seconds=900)
    valid, _ = verify_password(password, user.password_hash)
    if not valid:
        raise AppError(
            "Your current password is incorrect.",
            code="invalid_password",
            status_code=403,
            fields={"current_password": "Incorrect password"},
        )


@router.patch("")
async def update_profile(body: ProfileIn, ctx: CurrentUser, db: DB, settings: AppSettings) -> dict:
    if body.full_name is not None:
        ctx.user.full_name = " ".join(body.full_name.split())
    if body.timezone is not None:
        ctx.user.timezone = body.timezone
    await db.commit()
    await db.refresh(ctx.user)
    return await me_payload(db, settings, ctx)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChangeIn, ctx: CurrentUser, request: Request, db: DB, settings: AppSettings
) -> Response:
    await _verify_current_password(ctx.user, body.current_password)
    _check_policy(body.new_password, ctx.user.email)
    ctx.user.password_hash = hash_password(body.new_password)
    await service.revoke_sessions(db, ctx.user.id, except_session_id=ctx.session.id)
    await service.send_password_changed_email(db, settings, ctx.user)
    audit(db, "auth.password_changed", actor_id=ctx.user.id, ip=client_ip(request))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions")
async def list_sessions(ctx: CurrentUser, db: DB) -> list[dict]:
    rows = (
        await db.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == ctx.user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > func.now(),
            )
            .order_by(UserSession.last_seen_at.desc())
        )
    ).all()
    return [
        {
            "id": str(s.id),
            "created_at": s.created_at.isoformat(),
            "last_seen_at": s.last_seen_at.isoformat(),
            "ip_address": s.ip_address,
            "user_agent": s.user_agent,
            "current": s.id == ctx.session.id,
        }
        for s in rows
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(session_id: uuid.UUID, ctx: CurrentUser, db: DB) -> Response:
    session = await db.scalar(
        select(UserSession).where(UserSession.id == session_id, UserSession.user_id == ctx.user.id)
    )
    if session is None:
        raise NotFound("Session not found.")
    session.revoked_at = datetime.now(UTC)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountIn,
    ctx: CurrentUser,
    request: Request,
    response: Response,
    db: DB,
    settings: AppSettings,
) -> Response:
    await _verify_current_password(ctx.user, body.password)
    if ctx.user.role == UserRole.ADMIN:
        admins = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
        if admins <= 1:
            raise Conflict("You are the last administrator. Promote someone else first.")
    audit(
        db,
        "user.delete_self",
        actor_id=None,
        ip=client_ip(request),
        target_type="user",
        target_id=ctx.user.id,
    )
    await db.delete(ctx.user)
    await db.commit()
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(out, settings)
    return out
