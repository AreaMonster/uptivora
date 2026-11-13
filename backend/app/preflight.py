"""Production readiness checks: ``python -m app.cli preflight [--smtp]``.

Run on the server (``docker compose run --rm api python -m app.cli preflight``) before going
live and after configuration changes. Exit code 1 if any check FAILs.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from app.core.config import Settings
from app.core.db import get_sessionmaker
from app.engine.partitions import partition_name
from app.licensing.keys import PRODUCTION_PUBLIC_KEYS


@dataclass
class Result:
    level: str  # PASS | WARN | FAIL
    name: str
    detail: str


def _alembic_head() -> str | None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    return ScriptDirectory.from_config(cfg).get_current_head()


async def run_checks(settings: Settings, *, smtp: bool = False) -> list[Result]:
    r: list[Result] = []

    def add(ok: bool, name: str, good: str, bad: str, *, fail: bool = True) -> None:
        r.append(Result("PASS" if ok else ("FAIL" if fail else "WARN"), name, good if ok else bad))

    prod = settings.is_production
    add(prod, "Environment", "production", f"UPTIVORA_ENV={settings.env}", fail=False)
    add(
        settings.public_url.startswith("https://"),
        "Public URL",
        settings.public_url,
        f"{settings.public_url} is not HTTPS",
    )
    add(
        len(settings.secret_key.get_secret_value()) >= 32,
        "Secret key",
        "set, 32+ characters",
        "too short — generate one with install.sh",
    )
    broad = [
        c for c in settings.trusted_proxies if ipaddress.ip_network(c, strict=False).prefixlen == 0
    ]
    add(
        not broad,
        "Trusted proxies",
        ", ".join(settings.trusted_proxies),
        f"{broad} trusts every address: client IPs (rate limits) can be spoofed",
    )

    # Database
    maker = get_sessionmaker()
    try:
        async with maker() as db:
            current = await db.scalar(text("SELECT version_num FROM alembic_version"))
            head = _alembic_head()
            add(
                current == head,
                "Database schema",
                f"at {current}",
                f"at {current}, expected {head}: run migrations",
            )
            today = datetime.now(UTC).date()
            missing = [
                partition_name(d)
                for d in (today, today + timedelta(days=1))
                if await db.scalar(text("SELECT to_regclass(:n)"), {"n": partition_name(d)}) is None
            ]
            add(
                not missing,
                "Check partitions",
                "today and tomorrow exist",
                f"missing {missing}: is the worker running?",
            )
            workers = await db.scalar(
                text(
                    "SELECT count(*) FROM worker_heartbeats "
                    "WHERE last_seen_at > now() - interval '60 seconds'"
                )
            )
            add(
                bool(workers),
                "Monitoring worker",
                f"{workers} running",
                "no worker heartbeat in the last minute",
                fail=False,
            )
            admins = await db.scalar(
                text("SELECT count(*) FROM users WHERE role = 'admin' AND is_active")
            )
            add(
                bool(admins),
                "Administrator",
                f"{admins} active",
                "no administrator account yet",
                fail=False,
            )
    except Exception as exc:  # noqa: BLE001
        r.append(Result("FAIL", "Database", f"not reachable: {type(exc).__name__}: {exc}"))

    # Email
    add(
        bool(settings.smtp_host),
        "SMTP",
        settings.smtp_host or "-",
        "UPTIVORA_SMTP_HOST is empty: no alert can be sent",
    )
    if smtp and settings.smtp_host:
        from app.notifications.mailer import MailerError, test_connection

        try:
            await test_connection(settings)
            r.append(Result("PASS", "SMTP login", f"{settings.smtp_host}:{settings.smtp_port}"))
        except MailerError as exc:
            r.append(Result("FAIL", "SMTP login", str(exc)))

    # Edition-specific
    if settings.is_hosted:
        r.append(
            Result(
                "WARN" if settings.billing_test_mode else "PASS",
                "Billing",
                "TEST MODE: payments are simulated"
                if settings.billing_test_mode
                else settings.billing_provider,
            )
        )
        from app.billing.signer_client import health as signer_health

        signer = await signer_health(settings)
        add(
            signer == "ok",
            "Licence signer",
            f"ready ({settings.signer_key_id})",
            f"{signer}: self-hosted licences are not signed automatically "
            "(docs/LICENSE_KEY_OPERATIONS.md)",
            fail=False,
        )
        add(
            bool(settings.network_canaries),
            "Alert-storm guard",
            f"{len(settings.network_canaries)} canary URL(s)",
            "UPTIVORA_NETWORK_CANARIES is empty: a network outage of this server would email "
            "every customer",
            fail=False,
        )
    else:
        add(
            bool(PRODUCTION_PUBLIC_KEYS),
            "Licence keys",
            f"{len(PRODUCTION_PUBLIC_KEYS)} key(s)",
            "this build contains no production public key: licences cannot be verified",
        )

    add(
        bool(settings.heartbeat_url),
        "External heartbeat",
        "UPTIVORA_HEARTBEAT_URL is set",
        "nothing alerts you if this server stops (set UPTIVORA_HEARTBEAT_URL or check "
        "/api/health/service from outside)",
        fail=False,
    )
    return r


def render(results: list[Result]) -> str:
    width = max(len(x.name) for x in results)
    lines = [f"{x.level:<4}  {x.name:<{width}}  {x.detail}" for x in results]
    fails = sum(x.level == "FAIL" for x in results)
    warns = sum(x.level == "WARN" for x in results)
    lines.append(f"\n{fails} failed, {warns} warning(s), {len(results) - fails - warns} passed")
    return "\n".join(lines)
