"""Fixed-window rate limiting backed by the UNLOGGED ``rate_limit_buckets`` table.

Counting happens on its own connection/transaction so that a request which later fails and
rolls back still counts (otherwise failed logins would never be limited).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.errors import RateLimited

_UPSERT = text(
    """
    INSERT INTO rate_limit_buckets (key, window_start, count)
    VALUES (:key, :window_start, 1)
    ON CONFLICT (key, window_start) DO UPDATE SET count = rate_limit_buckets.count + 1
    RETURNING count
    """
)


def _key(scope: str, identity: str) -> str:
    # Hash identities (emails, IPs) so the table holds no personal data in clear text.
    digest = hashlib.sha256(identity.lower().encode("utf-8")).hexdigest()[:32]
    return f"{scope}:{digest}"


async def hit(scope: str, identity: str, *, limit: int, window_seconds: int) -> None:
    """Count one event; raise :class:`RateLimited` when ``limit`` is exceeded in the window."""
    if not get_settings().rate_limit_enabled:
        return
    now = datetime.now(UTC)
    epoch = int(now.timestamp())
    window_start = datetime.fromtimestamp(epoch - epoch % window_seconds, UTC)
    async with get_engine().begin() as conn:
        count = (
            await conn.execute(
                _UPSERT, {"key": _key(scope, identity), "window_start": window_start}
            )
        ).scalar_one()
    if count > limit:
        retry_after = int(window_start.timestamp()) + window_seconds - epoch
        raise RateLimited(
            "Too many attempts. Please wait a moment and try again.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


async def purge_expired(older_than_seconds: int = 86400) -> int:
    async with get_engine().begin() as conn:
        result = await conn.execute(
            text(
                "DELETE FROM rate_limit_buckets"
                " WHERE window_start < now() - make_interval(secs => :s)"
            ),
            {"s": older_than_seconds},
        )
    return result.rowcount or 0
