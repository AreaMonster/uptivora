"""Development seed data: ``python -m app.devseed``.

Creates a demo account with a TEST subscription and synthetic monitoring history so the UI
can be explored before real checks exist. Refuses to run outside development.

Demo login: demo@example.com / value of UPTIVORA_DEV_DEMO_PASSWORD
(default: ``uptivora-demo-password``).
Admin login: admin@example.com / value of UPTIVORA_DEV_ADMIN_PASSWORD
(default: ``uptivora-dev-operator-2026``). Development databases only.
"""

from __future__ import annotations

import asyncio
import math
import os
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.auth.service import create_user, get_user_by_email
from app.core.config import get_settings
from app.core.db import get_engine, get_sessionmaker
from app.models import (
    CheckResult,
    Incident,
    Monitor,
    MonitorStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    UserRole,
)

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = os.environ.get("UPTIVORA_DEV_DEMO_PASSWORD", "uptivora-demo-password")
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = os.environ.get("UPTIVORA_DEV_ADMIN_PASSWORD", "uptivora-dev-operator-2026")

SITES = [
    ("Online shop", "https://shop.example.com/", 180, None),
    ("Marketing website", "https://www.example.com/", 95, None),
    ("Customer API", "https://api.example.net/health", 240, "down"),
    ("Status page", "https://status.example.org/", 70, "ssl"),
]


async def ensure_admin() -> None:
    """Create the development administrator account if it does not exist (idempotent)."""
    if get_settings().env != "development":
        raise SystemExit("devseed only runs with UPTIVORA_ENV=development")
    async with get_sessionmaker()() as db:
        if await get_user_by_email(db, ADMIN_EMAIL) is None:
            admin = await create_user(
                db,
                email=ADMIN_EMAIL,
                password=ADMIN_PASSWORD,
                full_name="Dev Admin",
                role=UserRole.ADMIN,
            )
            admin.email_verified_at = datetime.now(UTC)
            await db.commit()
            print(f"Created development admin {ADMIN_EMAIL}")


async def seed() -> None:
    settings = get_settings()
    if settings.env != "development":
        raise SystemExit("devseed only runs with UPTIVORA_ENV=development")
    rng = random.Random(42)  # noqa: S311 — synthetic data, not security relevant
    now = datetime.now(UTC).replace(second=0, microsecond=0)

    async with get_sessionmaker()() as db:
        user = await get_user_by_email(db, DEMO_EMAIL)
        if user is None:
            user = await create_user(
                db, email=DEMO_EMAIL, password=DEMO_PASSWORD, full_name="Demo User"
            )
            user.email_verified_at = now
            user.timezone = "Europe/Zurich"
            plan = await db.scalar(select(Plan).where(Plan.code == "pro"))
            db.add(
                Subscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    status=SubscriptionStatus.ACTIVE,
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30),
                    provider="test",
                    is_test=True,
                )
            )
        await db.execute(delete(Monitor).where(Monitor.owner_id == user.id))
        await db.flush()

        for name, url, base_ms, scenario in SITES:
            m = Monitor(
                owner_id=user.id,
                name=name,
                url=url,
                interval_seconds=300,
                status=MonitorStatus.UP,
                next_check_at=now + timedelta(days=365),
            )
            db.add(m)
            await db.flush()
            rows = []
            for i in range(7 * 24 * 12):  # 7 days at 5-minute intervals
                t = now - timedelta(minutes=5 * i)
                daily = 1 + 0.25 * math.sin((t.hour + t.minute / 60) / 24 * 2 * math.pi)
                ms = int(base_ms * daily * rng.uniform(0.85, 1.25))
                is_up = True
                if scenario == "down" and (i < 4 or 400 <= i < 412):
                    is_up = False
                elif rng.random() < 0.002:
                    is_up = False
                rows.append(
                    CheckResult(
                        monitor_seq=m.seq,
                        checked_at=t,
                        is_up=is_up,
                        status_code=200 if is_up else 503,
                        response_ms=ms if is_up else None,
                        error_kind=None if is_up else "http_status",
                        error_message=None if is_up else "HTTP 503 Service Unavailable",
                    )
                )
            db.add_all(rows)
            m.last_checked_at = now
            m.last_response_ms = int(base_ms * rng.uniform(0.9, 1.1))
            m.last_status_code = 200
            m.ssl_issuer = "Let's Encrypt R11"
            m.ssl_last_checked_at = now
            m.ssl_expires_at = now + timedelta(days=9 if scenario == "ssl" else 64)
            if scenario == "down":
                m.status = MonitorStatus.DOWN
                m.last_status_code = 503
                m.last_response_ms = None
                m.last_error = "HTTP 503 Service Unavailable (expected 200-399)"
                m.last_status_change_at = now - timedelta(minutes=20)
                db.add(
                    Incident(
                        monitor_id=m.id,
                        started_at=now - timedelta(minutes=20),
                        cause="HTTP 503 Service Unavailable",
                        status_code=503,
                        error_kind="http_status",
                    )
                )
                db.add(
                    Incident(
                        monitor_id=m.id,
                        started_at=now - timedelta(minutes=5 * 411),
                        resolved_at=now - timedelta(minutes=5 * 400),
                        cause="Connection timed out after 10 s",
                        error_kind="timeout",
                    )
                )
        await db.commit()
    await ensure_admin()
    await get_engine().dispose()
    print(f"Seeded demo account {DEMO_EMAIL} with {len(SITES)} monitors and 7 days of history.")


if __name__ == "__main__":
    asyncio.run(seed())
