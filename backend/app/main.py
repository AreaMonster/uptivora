"""API process entry point: ``uvicorn app.main:app``."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.account.router import router as account_router
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import install_error_handlers
from app.incidents.router import router as incidents_router
from app.monitors.router import router as monitors_router
from app.notifications.router import router as notifications_router
from app.public.router import router as public_router

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    # The API only returns JSON; nothing should ever be rendered or framed from it.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(
        title="Uptivora API",
        version=settings.version,
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def origin_guard(request: Request, call_next) -> Response:
        """Reject cross-site state-changing requests (CSRF defence for all endpoints,
        including login/register which have no session yet)."""
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            fetch_site = request.headers.get("sec-fetch-site")
            if (origin and origin != settings.public_origin) or (
                not origin and fetch_site == "cross-site"
            ):
                return JSONResponse(
                    {"error": {"code": "bad_origin", "message": "Cross-site request blocked."}},
                    status_code=403,
                )
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.secure_cookies:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response

    @app.get("/api/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/health/ready", tags=["health"])
    async def ready(response: Response) -> dict[str, str]:
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 — any DB failure means "not ready"
            response.status_code = 503
            return {"status": "unavailable", "database": "down"}
        return {"status": "ok", "database": "up", "edition": settings.edition}

    app.include_router(public_router)
    app.include_router(auth_router)
    app.include_router(account_router)
    app.include_router(monitors_router)
    app.include_router(incidents_router)
    app.include_router(notifications_router)
    return app


app = create_app()
