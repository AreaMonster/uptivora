from __future__ import annotations

import asyncio
import ipaddress
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(REPO / "tools" / "licensegen"))

ADMIN_DB_URL = os.environ.get(
    "UPTIVORA_TEST_ADMIN_DSN", "postgresql://uptivora:uptivora@localhost:5433/postgres"
)
TEST_DB_NAME = "uptivora_test"
TEST_DB_URL = f"postgresql+asyncpg://uptivora:uptivora@localhost:5433/{TEST_DB_NAME}"
PUBLIC_URL = "http://localhost:3000"

# Tests are configured explicitly; values from a developer's backend/.env never apply
# because environment variables take precedence over the .env file.
os.environ.update(
    {
        "UPTIVORA_ENV": "test",
        "UPTIVORA_EDITION": "hosted",
        "UPTIVORA_PUBLIC_URL": PUBLIC_URL,
        "UPTIVORA_DATABASE_URL": TEST_DB_URL,
        "UPTIVORA_BILLING_PROVIDER": "test",
        "UPTIVORA_RATE_LIMIT_ENABLED": "false",
        "UPTIVORA_SMTP_HOST": "localhost",
        "UPTIVORA_SMTP_PORT": "1025",
        "UPTIVORA_SMTP_SECURITY": "none",
        "UPTIVORA_SMTP_FROM": "Uptivora Test <alerts@uptivora.test>",
    }
)


async def _recreate_database() -> None:
    import asyncpg

    conn = await asyncpg.connect(ADMIN_DB_URL, timeout=3)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def migrated_db_url() -> str:
    """Fresh database with all migrations applied. Skips if PostgreSQL is not running."""
    try:
        asyncio.run(_recreate_database())
    except (OSError, TimeoutError) as exc:
        pytest.skip(f"PostgreSQL not reachable ({exc}); run deploy/docker-compose.dev.yml")

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.attributes["database_url"] = TEST_DB_URL
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    return TEST_DB_URL


# --- API fixtures ---------------------------------------------------------------------------


@pytest.fixture
def settings():
    from app.core.config import get_settings

    return get_settings()


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch: pytest.MonkeyPatch):
    """No real DNS in tests: hosts containing 'private' resolve to 10.0.0.1, others public."""
    from app.core import netguard

    async def resolve(host: str, port: int, *, dns_timeout: float = 5.0):
        literal = netguard._parse_ip_literal(host)
        if literal is not None:
            if not netguard.is_public_ip(literal):
                raise netguard.UnsafeURLError("blocked_address", "Private address")
            return [literal]
        if "nxdomain" in host:
            raise netguard.UnsafeURLError("dns_error", f"DNS lookup for {host} failed")
        ip = ipaddress.ip_address("10.0.0.1" if "private" in host else "93.184.215.14")
        if not netguard.is_public_ip(ip):
            raise netguard.UnsafeURLError(
                "blocked_address", f"{host} resolves to a private or reserved address"
            )
        return [ip]

    monkeypatch.setattr(netguard, "resolve_public_addresses", resolve)


@pytest.fixture
async def db(migrated_db_url: str):
    from app.core.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        yield session


@pytest.fixture
async def client(migrated_db_url: str):
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app, client=("203.0.113.50", 50000))
    async with httpx.AsyncClient(transport=transport, base_url=PUBLIC_URL) as c:
        yield c


@pytest.fixture
def make_client(migrated_db_url: str):
    """Factory for additional independent browser-like clients (separate cookie jars)."""
    import httpx

    from app.main import app

    clients: list[httpx.AsyncClient] = []

    def factory() -> httpx.AsyncClient:
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=PUBLIC_URL)
        clients.append(c)
        return c

    yield factory
    for c in clients:
        asyncio.get_event_loop().create_task(c.aclose())


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


PASSWORD = "Correct-Horse-42!"


async def register(client, email: str | None = None, password: str = PASSWORD) -> dict:
    resp = await client.post(
        "/api/auth/register",
        json={"email": email or unique_email(), "password": password, "full_name": "Test User"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    client.headers["X-CSRF-Token"] = data["csrf_token"]
    return data


async def give_plan(db, user_id: str, code: str) -> None:
    from sqlalchemy import select

    from app.models import Plan, Subscription, SubscriptionStatus

    plan = await db.scalar(select(Plan).where(Plan.code == code))
    now = datetime.now(UTC)
    db.add(
        Subscription(
            user_id=uuid.UUID(user_id),
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            provider="test",
            is_test=True,
        )
    )
    await db.commit()
