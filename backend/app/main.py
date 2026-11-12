"""API process entry point: ``uvicorn app.main:app``.

Phase 1 exposes only health endpoints; feature routers are added from Phase 2 onwards.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    # The API only returns JSON; nothing should ever be rendered or framed from it.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Uptivora API",
        version=settings.version,
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.is_production:
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

    return app


app = create_app()
