from __future__ import annotations

import re

import pytest
from sqlalchemy import select, update

from app.models import NotificationOutbox, User
from tests.conftest import PASSWORD, register, unique_email


async def _latest_link(db, email: str, path: str) -> str:
    """Read the token from the queued email (tokens are only stored hashed in the DB)."""
    rows = (
        await db.scalars(
            select(NotificationOutbox.body_text)
            .where(NotificationOutbox.recipient == email)
            .order_by(NotificationOutbox.created_at.desc())
        )
    ).all()
    for body in rows:
        m = re.search(rf"/{path}#([A-Za-z0-9_-]+)", body)
        if m:
            return m.group(1)
    raise AssertionError(f"no {path} email for {email}")


async def test_register_sets_secure_session(client) -> None:
    email = unique_email("Reg").replace("Reg", "REG")
    resp = await client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": " Ada  L "}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == email.lower()
    assert body["user"]["full_name"] == "Ada L"
    assert body["user"]["role"] == "user" and body["user"]["email_verified"] is False
    assert body["limits"]["source"] == "no_plan" and body["limits"]["max_monitors"] == 0
    cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_duplicate_and_weak_password(client) -> None:
    email = unique_email()
    await register(client, email)
    dup = await client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert dup.status_code == 409 and "email" in dup.json()["error"]["fields"]
    weak = await client.post(
        "/api/auth/register", json={"email": unique_email(), "password": "short"}
    )
    assert weak.status_code == 422 and "password" in weak.json()["error"]["fields"]
    bad = await client.post(
        "/api/auth/register", json={"email": "not-an-email", "password": PASSWORD}
    )
    assert bad.status_code == 422 and "email" in bad.json()["error"]["fields"]


async def test_login_errors_are_uniform(client, make_client) -> None:
    email = unique_email()
    await register(make_client(), email)
    wrong = await client.post(
        "/api/auth/login", json={"email": email, "password": "Wrong-pass-123"}
    )
    unknown = await client.post(
        "/api/auth/login", json={"email": unique_email(), "password": "Wrong-pass-123"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    ok = await client.post("/api/auth/login", json={"email": email.upper(), "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["user"]["email"] == email


async def test_csrf_required_for_mutations(client) -> None:
    me = await register(client)
    del client.headers["X-CSRF-Token"]
    assert (await client.post("/api/auth/logout")).json()["error"]["code"] == "csrf_failed"
    bad = await client.post("/api/auth/logout", headers={"X-CSRF-Token": "x" * 32})
    assert bad.status_code == 403
    ok = await client.post("/api/auth/logout", headers={"X-CSRF-Token": me["csrf_token"]})
    assert ok.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_cross_site_requests_blocked(client) -> None:
    resp = await client.post(
        "/api/auth/login",
        headers={"Origin": "https://evil.example"},
        json={"email": unique_email(), "password": PASSWORD},
    )
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "bad_origin"
    resp = await client.post(
        "/api/auth/login",
        headers={"Sec-Fetch-Site": "cross-site"},
        json={"email": unique_email(), "password": PASSWORD},
    )
    assert resp.status_code == 403
    same = await client.post(
        "/api/auth/login",
        headers={"Origin": "http://localhost:3000"},
        json={"email": unique_email(), "password": PASSWORD},
    )
    assert same.status_code == 401


async def test_email_verification(client, db) -> None:
    me = await register(client)
    token = await _latest_link(db, me["user"]["email"], "verify-email")
    assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 200
    assert (await client.get("/api/auth/me")).json()["user"]["email_verified"] is True
    again = await client.post("/api/auth/verify-email", json={"token": token})
    assert again.status_code == 400 and again.json()["error"]["code"] == "invalid_token"


async def test_password_reset_flow(client, make_client, db) -> None:
    email = unique_email()
    await register(client, email)
    other = make_client()
    unknown = await other.post("/api/auth/forgot-password", json={"email": unique_email()})
    known = await other.post("/api/auth/forgot-password", json={"email": email})
    assert unknown.status_code == known.status_code == 202 and unknown.json() == known.json()

    token = await _latest_link(db, email, "reset-password")
    weak = await other.post("/api/auth/reset-password", json={"token": token, "password": "weak"})
    assert weak.status_code == 422  # token NOT consumed by a failed attempt
    new_pw = "Brand-New-Secret-77"
    ok = await other.post("/api/auth/reset-password", json={"token": token, "password": new_pw})
    assert ok.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 401  # old sessions revoked
    reuse = await other.post("/api/auth/reset-password", json={"token": token, "password": new_pw})
    assert reuse.status_code == 400
    old = await other.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert old.status_code == 401
    login = await other.post("/api/auth/login", json={"email": email, "password": new_pw})
    assert login.status_code == 200 and login.json()["user"]["email_verified"] is True


async def test_suspended_user_cannot_login_or_use_session(client, make_client, db) -> None:
    email = unique_email()
    await register(client, email)
    await db.execute(update(User).where(User.email == email).values(is_active=False))
    await db.commit()
    assert (await client.get("/api/auth/me")).status_code == 401
    resp = await make_client().post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "account_suspended"


async def test_rate_limit(client, settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    email = unique_email()
    codes = [
        (await client.post("/api/auth/login", json={"email": email, "password": "Wrong-pass-1"}))
        for _ in range(11)
    ]
    assert [r.status_code for r in codes[:10]] == [401] * 10
    assert codes[10].status_code == 429 and int(codes[10].headers["retry-after"]) >= 1


async def test_security_headers(client) -> None:
    resp = await client.get("/api/health/live")
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["cache-control"] == "no-store"


async def test_public_config_and_plans(client) -> None:
    cfg = (await client.get("/api/public/config")).json()
    assert cfg["edition"] == "hosted" and cfg["billing_test_mode"] is True
    plans = (await client.get("/api/public/plans")).json()
    assert [p["code"] for p in plans["plans"]] == ["starter", "pro", "business"]
    assert [p["price_cents"] for p in plans["licences"]] == [9900, 19900]


async def test_unknown_route_json_404(client) -> None:
    resp = await client.get("/api/nope")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"
