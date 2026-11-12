from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(REPO / "tools" / "licensegen"))

# Tests never read the developer's .env; configure explicitly.
os.environ.setdefault("UPTIVORA_ENV", "test")
os.environ.setdefault("UPTIVORA_PUBLIC_URL", "http://localhost:3000")
ADMIN_DB_URL = os.environ.get(
    "UPTIVORA_TEST_ADMIN_DSN", "postgresql://uptivora:uptivora@localhost:5433/postgres"
)
TEST_DB_NAME = "uptivora_test"
TEST_DB_URL = f"postgresql+asyncpg://uptivora:uptivora@localhost:5433/{TEST_DB_NAME}"


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
