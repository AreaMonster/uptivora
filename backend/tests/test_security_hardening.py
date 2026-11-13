"""Phase 9 security tests: sessions, CSRF binding, mass assignment, proxies, client IPs.

Complements test_api_auth (CSRF/origin/rate limit basics), test_netguard and
test_engine_checker (SSRF matrix), test_admin (RBAC) and the *_private IDOR tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update
from starlette.requests import Request

from app.core import requestctx
from app.engine.netclient import build_clients
from app.models import Session as UserSession
from app.models import User
from tests.conftest import PASSWORD, PUBLIC_URL, register, unique_email


def _session_cookie(client: httpx.AsyncClient) -> tuple[str, str]:
    for name in ("uptivora_session", "__Host-uptivora_session"):
        if name in client.cookies:
            return name, client.cookies[name]
    raise AssertionError("no session cookie")


async def _user_sessions(db, email: str):
    user = await db.scalar(select(User).where(User.email == email))
    return user, (await db.scalars(select(UserSession).where(UserSession.user_id == user.id))).all()


# --- sessions ---------------------------------------------------------------------------------


async def test_idle_session_expires(client, db, settings) -> None:
    me = await register(client)
    user, _ = await _user_sessions(db, me["user"]["email"])
    stale = datetime.now(UTC) - timedelta(days=settings.session_idle_days, minutes=1)
    await db.execute(
        update(UserSession).where(UserSession.user_id == user.id).values(last_seen_at=stale)
    )
    await db.commit()
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_absolute_session_lifetime_is_enforced(client, db) -> None:
    me = await register(client)
    user, _ = await _user_sessions(db, me["user"]["email"])
    past = datetime.now(UTC) - timedelta(minutes=1)
    await db.execute(
        update(UserSession).where(UserSession.user_id == user.id).values(expires_at=past)
    )
    await db.commit()
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_revokes_the_token_server_side(client, make_client) -> None:
    await register(client)
    name, value = _session_cookie(client)
    assert (await client.post("/api/auth/logout")).status_code == 204
    replay = make_client()
    replay.cookies.set(name, value)
    assert (await replay.get("/api/auth/me")).status_code == 401


async def test_session_token_is_stored_hashed(client, db) -> None:
    me = await register(client)
    _, value = _session_cookie(client)
    _, sessions = await _user_sessions(db, me["user"]["email"])
    stored = {str(getattr(s, c.key)) for s in sessions for c in UserSession.__table__.columns}
    assert value not in stored


async def test_login_issues_a_new_session_token(client, make_client) -> None:
    """No session fixation: a cookie planted before login is not carried over."""
    email = unique_email()
    await register(make_client(), email)
    planted = "attacker-chosen-value-0123456789abcdef"
    client.cookies.set("uptivora_session", planted)
    resp = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    issued = resp.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
    assert issued and issued != planted
    attacker = httpx.AsyncClient(transport=client._transport, base_url=PUBLIC_URL)  # noqa: SLF001
    attacker.cookies.set("uptivora_session", planted)
    async with attacker:
        assert (await attacker.get("/api/auth/me")).status_code == 401


async def test_csrf_token_is_bound_to_its_session(client, make_client) -> None:
    alice = await register(client)
    bob_client = make_client()
    await register(bob_client)
    resp = await bob_client.post("/api/auth/logout", headers={"X-CSRF-Token": alice["csrf_token"]})
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "csrf_failed"


async def test_https_deployment_uses_host_prefixed_secure_cookie(
    client, settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "public_url", "https://localhost:3000")
    resp = await client.post(
        "/api/auth/register",
        headers={"Origin": "https://localhost:3000"},
        json={"email": unique_email(), "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith("__Host-uptivora_session=")
    low = cookie.lower()
    assert "secure" in low and "httponly" in low and "domain=" not in low and "path=/" in low
    assert "max-age=63072000" in resp.headers["strict-transport-security"]


# --- mass assignment --------------------------------------------------------------------------


async def test_registration_ignores_privileged_fields(client) -> None:
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": unique_email(),
            "password": PASSWORD,
            "role": "admin",
            "is_active": True,
            "email_verified": True,
            "email_verified_at": "2020-01-01T00:00:00Z",
        },
    )
    assert resp.status_code == 201
    user = resp.json()["user"]
    assert user["role"] == "user" and user["email_verified"] is False


async def test_profile_update_cannot_change_role_or_email(client) -> None:
    me = await register(client)
    resp = await client.patch(
        "/api/account",
        json={"role": "admin", "email": "takeover@example.com", "full_name": "Still Me"},
    )
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["role"] == "user" and user["email"] == me["user"]["email"]
    assert user["full_name"] == "Still Me"


# --- network clients and client IPs -----------------------------------------------------------


async def test_monitor_clients_ignore_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.attacker.example:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.attacker.example:3128")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.attacker.example:3128")
    clients = build_clients()
    try:
        for c in (clients.verified, clients.unverified):
            assert c._trust_env is False  # noqa: SLF001
            assert not c._mounts  # noqa: SLF001 — no proxy transports were configured
    finally:
        await clients.aclose()


def _request(peer: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


@pytest.mark.parametrize(
    ("peer", "xff", "expected"),
    [
        ("203.0.113.9", None, "203.0.113.9"),
        # Untrusted peers cannot choose their address (rate limits, audit log).
        ("203.0.113.9", "1.2.3.4", "203.0.113.9"),
        # Trusted proxy: the right-most untrusted hop wins, spoofed left entries are ignored.
        ("127.0.0.1", "6.6.6.6, 198.51.100.20", "198.51.100.20"),
        ("127.0.0.1", "198.51.100.20, 127.0.0.1", "198.51.100.20"),
        ("127.0.0.1", "not-an-ip", "127.0.0.1"),
        ("127.0.0.1", None, "127.0.0.1"),
    ],
)
def test_client_ip_only_trusts_configured_proxies(
    peer: str, xff: str | None, expected: str
) -> None:
    assert requestctx.client_ip(_request(peer, xff)) == expected


async def test_forgot_password_is_rate_limited_per_address(
    client, settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    email = unique_email()
    codes = [
        (await client.post("/api/auth/forgot-password", json={"email": email})).status_code
        for _ in range(4)
    ]
    assert codes == [202, 202, 202, 429]


async def test_api_errors_do_not_leak_internals(client) -> None:
    resp = await client.post(
        "/api/auth/login", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert resp.status_code in (400, 422)
    text = resp.text.lower()
    assert "traceback" not in text and "sqlalchemy" not in text and "asyncpg" not in text


# --- email header injection -------------------------------------------------------------------


def test_email_headers_cannot_be_injected(settings) -> None:
    from app.notifications.mailer import EmailMessageData, build_message

    msg = build_message(
        settings,
        EmailMessageData(
            to="victim@example.com",
            subject="DOWN: shop\r\nBcc: everyone@example.com",
            text="body",
            headers={
                "Bcc": "everyone@example.com",
                "List-Unsubscribe": "<https://x.example/u>\r\nBcc: everyone@example.com",
                "X-Uptivora-Kind": "down",
            },
        ),
    )
    header_block = msg.as_string().split("\n\n", 1)[0]
    assert not any(line.lower().startswith("bcc:") for line in header_block.splitlines())
    assert msg["Subject"] == "DOWN: shop  Bcc: everyone@example.com"  # one line, inert text
    assert "List-Unsubscribe" not in msg and msg["X-Uptivora-Kind"] == "down"
    with pytest.raises(ValueError):
        build_message(
            settings,
            EmailMessageData(to="a@example.com\r\nBcc: b@example.com", subject="s", text="t"),
        )
