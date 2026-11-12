"""FastAPI dependencies for authentication, CSRF and authorization."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthContext, resolve_session
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import constant_time_equals
from app.models import UserRole

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "x-csrf-token"

DB = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def optional_auth(request: Request, db: DB, settings: AppSettings) -> AuthContext | None:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return await resolve_session(db, settings, token)


async def require_user(
    request: Request, ctx: Annotated[AuthContext | None, Depends(optional_auth)]
) -> AuthContext:
    if ctx is None:
        raise Unauthorized("Please sign in to continue.")
    # Every state-changing request from a cookie session must carry the session's CSRF token.
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not constant_time_equals(sent, ctx.session.csrf_token):
            raise Forbidden("Missing or invalid CSRF token.", code="csrf_failed")
    return ctx


async def require_admin(ctx: Annotated[AuthContext, Depends(require_user)]) -> AuthContext:
    if ctx.user.role != UserRole.ADMIN:
        raise Forbidden("Administrator access required.")
    return ctx


CurrentUser = Annotated[AuthContext, Depends(require_user)]
CurrentAdmin = Annotated[AuthContext, Depends(require_admin)]
