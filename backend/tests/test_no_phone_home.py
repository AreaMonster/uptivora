"""Uptivora must never contact anything except the monitored websites and the configured SMTP
server — no licence server, no telemetry, no analytics, no update checks.

Two complementary checks:
* static: network clients are only used where they belong (the checker and the mailer), and
  the web frontend contains no trackers, analytics or third-party scripts/fonts;
* runtime: a full self-hosted session (setup, licence install, monitors, admin pages, worker
  housekeeping) opens connections to nothing but the local database.
"""

from __future__ import annotations

import ast
import asyncio
import re
import socket
from pathlib import Path

import pytest
from licensegen.core import build_payload, sign_payload

from app.licensing import Edition
from tests.conftest import register
from tests.test_selfhosted_api import NEW, selfhosted  # noqa: F401 - pytest fixture

BACKEND_APP = Path(__file__).resolve().parents[1] / "app"
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"

# module prefix -> files allowed to import it
ALLOWED_NETWORK_IMPORTS = {
    # deadman.py: the opt-in UPTIVORA_HEARTBEAT_URL ping, off unless the operator sets a URL.
    # billing/signer_client.py: hosted-only internal signing service (UPTIVORA_SIGNER_URL).
    "httpx": {
        "engine/netclient.py",
        "engine/checker.py",
        "engine/deadman.py",
        "billing/signer_client.py",
    },
    "httpcore": {"engine/netclient.py"},
    "aiosmtplib": {"notifications/mailer.py"},
}
FORBIDDEN_IMPORTS = (
    "requests",
    "aiohttp",
    "urllib.request",
    "urllib3",
    "http.client",
    "ftplib",
    "smtplib",
    "websockets",
    "grpc",
    "sentry_sdk",
    "posthog",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_backend_network_clients_only_where_expected() -> None:
    problems = []
    for path in BACKEND_APP.rglob("*.py"):
        rel = path.relative_to(BACKEND_APP).as_posix()
        for name in _imports(path):
            for forbidden in FORBIDDEN_IMPORTS:
                if name == forbidden or name.startswith(forbidden + "."):
                    problems.append(f"{rel} imports {name}")
            for module, allowed in ALLOWED_NETWORK_IMPORTS.items():
                if (name == module or name.startswith(module + ".")) and rel not in allowed:
                    problems.append(f"{rel} imports {name} (only allowed in {sorted(allowed)})")
    assert problems == []


FRONTEND_FORBIDDEN = [
    r"googletagmanager",
    r"google-analytics",
    r"\bgtag\(",
    r"plausible\.io",
    r"segment\.(com|io)",
    r"sentry",
    r"posthog",
    r"hotjar",
    r"mixpanel",
    r"sendBeacon",
    r"fonts\.googleapis",
    r"fonts\.gstatic",
    r"new WebSocket\(",
    r"<script[^>]+src=[\"']https?://",
    r"fetch\(\s*[\"'`]https?://",
    r"next/font/google",
]


def test_frontend_has_no_trackers_or_external_resources() -> None:
    hits = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".mjs", ".css"}:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in FRONTEND_FORBIDDEN:
            if re.search(pattern, text, flags=re.IGNORECASE):
                hits.append(f"{path.relative_to(FRONTEND_SRC).as_posix()}: {pattern}")
    assert hits == []


def test_frontend_build_tooling_telemetry_disabled() -> None:
    package = (FRONTEND_SRC.parent / "package.json").read_text(encoding="utf-8")
    launcher = (FRONTEND_SRC.parent / "scripts" / "next.mjs").read_text(encoding="utf-8")
    for script in ("dev", "build", "start"):
        assert f'"{script}": "node scripts/next.mjs {script}"' in package
    assert 'NEXT_TELEMETRY_DISABLED: "1"' in launcher


@pytest.fixture
async def connection_spy(monkeypatch):
    """Record every outgoing TCP connection and DNS lookup made by the backend."""
    seen: list[tuple[str, object]] = []
    loop = asyncio.get_running_loop()

    real_create = loop.create_connection
    real_getaddrinfo = loop.getaddrinfo
    real_socket_create = socket.create_connection

    async def create_connection(*args, **kwargs):
        host = kwargs.get("host", args[1] if len(args) > 1 else None)
        port = kwargs.get("port", args[2] if len(args) > 2 else None)
        seen.append(("connect", (host, port)))
        return await real_create(*args, **kwargs)

    async def getaddrinfo(host, *args, **kwargs):
        seen.append(("dns", host))
        return await real_getaddrinfo(host, *args, **kwargs)

    def socket_create(address, *args, **kwargs):
        seen.append(("connect", address))
        return real_socket_create(address, *args, **kwargs)

    monkeypatch.setattr(loop, "create_connection", create_connection)
    monkeypatch.setattr(loop, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "create_connection", socket_create)
    return seen


LOCAL = {"localhost", "127.0.0.1", "::1", None}


async def test_selfhosted_session_contacts_nothing_external(
    selfhosted,
    client,
    settings,
    monkeypatch,
    connection_spy,  # noqa: F811
) -> None:
    from app.core.db import get_engine, get_sessionmaker
    from app.enforcement import enforce_instance_job
    from app.engine import housekeeping as hk
    from app.notifications.outbox import drain_outbox

    monkeypatch.setattr(settings, "smtp_host", "")  # no SMTP configured in this scenario
    await get_engine().dispose()  # force fresh DB connections so they are observed too
    maker = get_sessionmaker()

    await register(client)
    licence = sign_payload(
        selfhosted,
        build_payload(
            key_id="dev",
            edition=Edition.PROFESSIONAL,
            licensee_name="Offline AG",
            licensee_email="it@offline.example",
        ),
    )
    assert (
        await client.post("/api/admin/licence", json={"licence_text": licence})
    ).status_code == 200
    assert (await client.post("/api/monitors", json=NEW)).status_code == 201
    for path in (
        "/api/auth/me",
        "/api/public/config",
        "/api/admin/overview",
        "/api/admin/health",
        "/api/admin/licence",
        "/api/admin/setup",
        "/api/monitors",
        "/api/incidents",
    ):
        assert (await client.get(path)).status_code == 200, path
    await hk.rollup_hours(maker, settings)
    await hk.purge_old_data(maker, settings)
    await hk.ssl_warning_sweep(maker, settings)
    await enforce_instance_job(maker, settings)
    await drain_outbox(maker, settings)

    external = [
        (kind, target)
        for kind, target in connection_spy
        if (target[0] if isinstance(target, tuple) else target) not in LOCAL
    ]
    assert external == [], f"unexpected outbound traffic: {external}"
    assert any(kind == "connect" for kind, _ in connection_spy)  # the spy really observed traffic
