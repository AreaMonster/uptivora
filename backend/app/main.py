"""API process entry point: ``uvicorn app.main:app``."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.account.router import router as account_router
from app.admin import catalog as admin_catalog
from app.admin import devtools as admin_devtools
from app.admin import overview as admin_overview
from app.admin import users as admin_users
from app.auth.router import router as auth_router
from app.core import eventlog
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Flush buffered warnings/errors to ``system_events`` every 10 s while the API runs."""
    eventlog.install()
    stop = asyncio.Event()

    async def flusher() -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=10)
            except TimeoutError:
                pass
            await eventlog.flush_events(get_sessionmaker())

    task = asyncio.create_task(flusher())
    yield
    stop.set()
    await task


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(
        lifespan=lifespan,
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
    app.include_router(admin_overview.router)
    app.include_router(admin_users.router)
    app.include_router(admin_catalog.router)
    if settings.env in admin_devtools.DEV_ENVIRONMENTS:  # never mounted in production
        app.include_router(admin_devtools.router)
    return app


app = create_app()
