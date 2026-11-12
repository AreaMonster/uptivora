"""Administrator API: access control on every route, plus each feature."""

from __future__ import annotations

import logging
import re
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text, update

from app.core import eventlog
from app.core.db import get_sessionmaker
from app.licensing import trusted_keys, verify_license
from app.main import app as fastapi_app
from app.models import SystemEvent, User, UserRole
from tests.conftest import PASSWORD, give_plan, register, unique_email

NEW = {"name": "Shop", "url": "https://shop.example.com", "interval_seconds": 300}


async def make_admin(client, db) -> dict:
    me = await register(client)
    await db.execute(
        update(User).where(User.id == uuid.UUID(me["user"]["id"])).values(role=UserRole.ADMIN)
    )
    await db.commit()
    return me


def _admin_routes() -> list[tuple[str, str]]:
    routes = []
    for path, ops in fastapi_app.openapi()["paths"].items():
        if path.startswith("/api/admin"):
            for method in ops:
                concrete = re.sub(r"\{[^}]*_id\}", str(uuid.uuid4()), path)
                concrete = concrete.replace("{code}", "starter")
                routes.append((method.upper(), concrete))
    return routes


async def test_every_admin_route_requires_admin(client, make_client) -> None:
    routes = _admin_routes()
    assert len(routes) >= 18
    anonymous = make_client()
    await register(client)  # regular user (with CSRF header set)
    for method, path in routes:
        anon = await anonymous.request(method, path, json={})
        assert anon.status_code == 401, (method, path, anon.status_code)
        user = await client.request(method, path, json={})
        assert user.status_code == 403, (method, path, user.status_code)


async def test_overview_and_health(client, db) -> None:
    await make_admin(client, db)
    ov = (await client.get("/api/admin/overview")).json()
    assert ov["edition"] == "hosted" and ov["users"]["total"] >= 1
    assert {"active", "cancelled", "mrr"} <= set(ov["subscriptions"])
    assert "per_minute" in ov["checks"] and isinstance(ov["checks_by_hour"], list)
    health = (await client.get("/api/admin/health")).json()
    assert health["database"]["ok"] and health["database"]["latency_ms"] >= 0
    assert health["database"]["size_bytes"] > 0
    assert health["status"] in ("ok", "degraded") and isinstance(health["issues"], list)


async def test_user_search_and_detail(client, make_client, db) -> None:
    await make_admin(client, db)
    customer = make_client()
    email = unique_email("findme")
    me = await register(customer, email)
    await give_plan(db, me["user"]["id"], "pro")
    await customer.post("/api/monitors", json=NEW)

    found = (await client.get("/api/admin/users", params={"q": "FINDME"})).json()
    assert [u["email"] for u in found["items"]] == [email]
    assert found["items"][0]["plan"] == "Pro" and found["items"][0]["monitors"] == 1
    assert (await client.get("/api/admin/users", params={"q": "%"})).json()["total"] >= 0

    detail = (await client.get(f"/api/admin/users/{me['user']['id']}")).json()
    assert detail["subscription"]["plan_code"] == "pro" and detail["subscription"]["is_test"]
    assert detail["monitors"][0]["name"] == "Shop"
    assert any(a["action"] == "user.register" for a in detail["audit"])
    assert (await client.get(f"/api/admin/users/{uuid.uuid4()}")).status_code == 404


async def test_suspend_user_revokes_sessions(client, make_client, db) -> None:
    await make_admin(client, db)
    customer = make_client()
    email = unique_email()
    me = await register(customer, email)
    r = await client.patch(f"/api/admin/users/{me['user']['id']}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert (await customer.get("/api/auth/me")).status_code == 401
    login = await make_client().post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 403
    await client.patch(f"/api/admin/users/{me['user']['id']}", json={"is_active": True})
    login = await make_client().post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200


async def test_admin_cannot_lock_themselves_out(client, db) -> None:
    me = await make_admin(client, db)
    for body in ({"is_active": False}, {"role": "user"}):
        r = await client.patch(f"/api/admin/users/{me['user']['id']}", json=body)
        assert r.status_code == 409
    r = await client.post(f"/api/admin/users/{me['user']['id']}/revoke-sessions")
    assert r.status_code == 409


async def test_last_admin_cannot_be_removed(client, make_client, db) -> None:
    await db.execute(update(User).where(User.role == UserRole.ADMIN).values(role=UserRole.USER))
    await db.commit()
    first = await make_admin(client, db)
    second_client = make_client()
    second = await make_admin(second_client, db)
    # Two admins: the first may demote the second ...
    assert (
        await client.patch(f"/api/admin/users/{second['user']['id']}", json={"role": "user"})
    ).status_code == 200
    # ... then promote them again and be demoted by them, leaving one admin.
    await client.patch(f"/api/admin/users/{second['user']['id']}", json={"role": "admin"})
    r = await second_client.patch(f"/api/admin/users/{first['user']['id']}", json={"role": "user"})
    assert r.status_code == 200
    # Now `second` is the only admin and cannot be demoted by anyone.
    await db.execute(
        update(User)
        .where(User.id == uuid.UUID(first["user"]["id"]))
        .values(role=UserRole.ADMIN, is_active=False)
    )
    await db.commit()
    assert (
        await second_client.patch(f"/api/admin/users/{second['user']['id']}", json={"role": "user"})
    ).status_code == 409


async def test_monitor_moderation(client, make_client, db) -> None:
    await make_admin(client, db)
    owner = make_client()
    me = await register(owner)
    await give_plan(db, me["user"]["id"], "pro")
    mid = (
        await owner.post("/api/monitors", json={**NEW, "url": "https://abusive.example.com"})
    ).json()["id"]

    listed = (await client.get("/api/admin/monitors", params={"q": "abusive"})).json()
    assert [m["id"] for m in listed["items"]] == [mid]
    assert listed["items"][0]["owner_email"] == me["user"]["email"]

    paused = await client.post(f"/api/admin/monitors/{mid}/pause", json={"reason": "Hammering"})
    assert paused.json()["paused_reason"] == "admin"
    owner_resume = await owner.post(f"/api/monitors/{mid}/resume")
    assert (
        owner_resume.status_code == 403 and owner_resume.json()["error"]["code"] == "admin_paused"
    )
    admin_paused = (
        await client.get("/api/admin/monitors", params={"status": "admin_paused"})
    ).json()
    assert mid in [m["id"] for m in admin_paused["items"]]
    assert (await client.post(f"/api/admin/monitors/{mid}/resume")).status_code == 200

    await owner.post(f"/api/monitors/{mid}/pause")  # owner's own pause is respected
    assert (await client.post(f"/api/admin/monitors/{mid}/resume")).status_code == 409


async def test_plan_editor(client, make_client, db) -> None:
    await make_admin(client, db)
    plans = (await client.get("/api/admin/plans")).json()
    starter = next(p for p in plans if p["code"] == "starter")
    body = {
        k: starter[k]
        for k in (
            "name",
            "description",
            "price_cents",
            "currency",
            "max_monitors",
            "min_interval_seconds",
            "is_active",
            "is_public",
            "sort_order",
        )
    }
    try:
        r = await client.put(
            "/api/admin/plans/starter", json={**body, "price_cents": 700, "max_monitors": 4}
        )
        assert r.status_code == 200 and r.json()["price_cents"] == 700
        public = (await make_client().get("/api/public/plans")).json()["plans"]
        assert next(p for p in public if p["code"] == "starter")["max_monitors"] == 4
        bad = await client.put("/api/admin/plans/starter", json={**body, "min_interval_seconds": 5})
        assert bad.status_code == 422
        audit = (await client.get("/api/admin/audit", params={"action": "admin.plan"})).json()
        assert audit[0]["action"] == "admin.plan_update"
        assert audit[0]["details"]["changes"]["price_cents"] == [starter["price_cents"], 700]
    finally:
        await client.put("/api/admin/plans/starter", json=body)

    code = f"team-{uuid.uuid4().hex[:6]}"
    new = {**body, "code": code, "name": "Team", "price_cents": 4900, "is_public": False}
    assert (await client.post("/api/admin/plans", json=new)).status_code == 201
    assert (await client.post("/api/admin/plans", json=new)).status_code == 409
    assert (
        await client.post("/api/admin/plans", json={**new, "code": "Bad Code"})
    ).status_code == 422
    public = (await make_client().get("/api/public/plans")).json()["plans"]
    assert code not in [p["code"] for p in public]  # not public


async def test_licence_products(client, db) -> None:
    await make_admin(client, db)
    products = (await client.get("/api/admin/licence-products")).json()
    pro = next(p for p in products if p["code"] == "selfhosted-professional")
    body = {
        k: pro[k]
        for k in (
            "name",
            "description",
            "price_cents",
            "currency",
            "limits",
            "is_active",
            "sort_order",
        )
    }
    try:
        r = await client.put(
            "/api/admin/licence-products/selfhosted-professional",
            json={**body, "price_cents": 24900},
        )
        assert r.json()["price_cents"] == 24900
        bad = await client.put(
            "/api/admin/licence-products/selfhosted-professional",
            json={**body, "limits": {**body["limits"], "min_interval_seconds": 1}},
        )
        assert bad.status_code == 422
    finally:
        await client.put("/api/admin/licence-products/selfhosted-professional", json=body)


async def test_plans_hidden_in_selfhosted(client, db, settings, monkeypatch) -> None:
    await make_admin(client, db)
    monkeypatch.setattr(settings, "edition", "selfhosted")
    monkeypatch.setattr(settings, "billing_provider", "disabled")
    assert (await client.get("/api/admin/plans")).status_code == 404
    ov = (await client.get("/api/admin/overview")).json()
    assert "licence" in ov and "subscriptions" not in ov


async def test_settings(client, db) -> None:
    await make_admin(client, db)
    try:
        assert (
            await client.put("/api/admin/settings", json={"public_signup": True})
        ).status_code == 200
        assert (await client.get("/api/admin/settings")).json()["values"]["public_signup"] is True
    finally:
        await client.put("/api/admin/settings", json={"public_signup": False})


async def test_event_log_reaches_admin_logs(client, db) -> None:
    await make_admin(client, db)
    eventlog.install()
    marker = uuid.uuid4().hex
    logging.getLogger("uptivora.testsource").warning("Something odd %s", marker)
    logging.getLogger("uptivora.testsource").info("ignored info %s", marker)  # below threshold
    logging.getLogger("other.lib").error("not ours %s", marker)
    assert await eventlog.flush_events(get_sessionmaker()) >= 1
    logs = (await client.get("/api/admin/logs", params={"level": "warning"})).json()
    mine = [entry for entry in logs if marker in entry["message"]]
    assert len(mine) == 1 and mine[0]["source"] == "testsource" and mine[0]["level"] == "warning"
    db.add(SystemEvent(level="error", source="mailer", message=f"SMTP down {marker}"))
    await db.commit()
    errors = (
        await client.get("/api/admin/logs", params={"level": "error", "source": "mailer"})
    ).json()
    assert any(marker in e["message"] for e in errors)


async def test_dev_test_account(client, make_client, db) -> None:
    await make_admin(client, db)
    r = await client.post("/api/admin/dev/test-account", json={"plan_code": "business"})
    assert r.status_code == 201
    created = r.json()
    login = await make_client().post(
        "/api/auth/login", json={"email": created["email"], "password": created["password"]}
    )
    assert login.status_code == 200
    assert login.json()["limits"]["plan_code"] == "business"
    assert login.json()["user"]["email_verified"] is True


async def test_dev_test_licence(client, db, settings, tmp_path, monkeypatch) -> None:
    await make_admin(client, db)
    monkeypatch.setattr(settings, "dev_key_dir", tmp_path)
    missing = await client.post("/api/admin/dev/test-licence", json={})
    assert missing.status_code == 409 and missing.json()["error"]["code"] == "no_dev_key"

    key = Ed25519PrivateKey.generate()
    (tmp_path / "dev-private.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    from licensegen.core import public_key_b64

    (tmp_path / "dev-public.key").write_text(public_key_b64(key))
    r = await client.post(
        "/api/admin/dev/test-licence",
        json={"edition": "professional", "licensee_name": "QA AG", "max_monitors": 7},
    )
    assert r.status_code == 200
    body = r.json()
    assert "PRIVATE" not in str(body) and str(tmp_path) not in str(body)  # never leak key material
    lic = verify_license(body["licence_text"], trusted_keys("test", tmp_path))
    assert lic.licensee_name == "QA AG" and lic.limits.max_monitors == 7
    # Production never trusts the dev key that signed it.
    assert "dev" not in trusted_keys("production", tmp_path)


async def test_dev_tools_disabled_outside_development(client, db, settings, monkeypatch) -> None:
    await make_admin(client, db)
    monkeypatch.setattr(settings, "env", "production")
    for path in ("/api/admin/dev/test-account", "/api/admin/dev/test-licence"):
        assert (await client.post(path, json={})).status_code == 404
    assert (await client.get("/api/admin/dev/status")).status_code == 404


@pytest.fixture(autouse=True)
async def _restore_admin_free_state(db):
    yield
    # Leave no extra admins with suspended state behind for other test modules.
    await db.execute(text("UPDATE users SET is_active = true WHERE role = 'admin'"))
    await db.commit()
