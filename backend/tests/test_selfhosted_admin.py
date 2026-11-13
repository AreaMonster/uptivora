"""Self-hosted administration: licence install/remove, instance-wide limits, invitations,
race-free first run, setup checklist, licence files on disk."""

from __future__ import annotations

import asyncio
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from licensegen.core import build_payload, sign_payload
from sqlalchemy import select, update

from app.licensing import Edition, LicenseLimits
from app.models import Monitor, NotificationOutbox, User, UserRole
from tests.conftest import register, unique_email
from tests.test_selfhosted_api import NEW, selfhosted  # noqa: F401 - pytest fixture

PASSWORD = "Colleague-pass-99"


def _signed(key, edition=Edition.STARTER, limits=None, name="Acme GmbH") -> str:
    return sign_payload(
        key,
        build_payload(
            key_id="dev",
            edition=edition,
            licensee_name=name,
            licensee_email="it@acme.ch",
            limits=limits,
        ),
    )


async def _install(client, key, limits=None, **kw) -> dict:
    r = await client.post(
        "/api/admin/licence", json={"licence_text": _signed(key, limits=limits, **kw)}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_install_and_remove_licence_rebalances_monitors(selfhosted, client, db) -> None:  # noqa: F811
    await register(client)  # first account: admin
    for i in range(3):  # evaluation limit: 3
        assert (
            await client.post("/api/monitors", json={**NEW, "name": f"M{i}"})
        ).status_code == 201
    status = (await client.get("/api/admin/licence")).json()
    assert status["installed"] is False and status["limits"]["source"] == "unlicensed"

    bad = await client.post(
        "/api/admin/licence", json={"licence_text": _signed(Ed25519PrivateKey.generate())}
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_licence"

    licence_text = _signed(selfhosted, limits=LicenseLimits(5, 3, 60))
    ok = (await client.post("/api/admin/licence", json={"licence_text": licence_text})).json()
    assert ok["edition"] == "starter"
    for i in range(3, 5):
        assert (
            await client.post("/api/monitors", json={**NEW, "name": f"M{i}"})
        ).status_code == 201
    status = (await client.get("/api/admin/licence")).json()
    assert status["licence"]["licensee_name"] == "Acme GmbH"
    assert status["licence"]["development_key"] is True
    assert status["usage"]["active_monitors"] == 5

    # Removing the licence: back to evaluation (3) — the two newest are paused, not deleted.
    removed = await client.request("DELETE", "/api/admin/licence")
    assert removed.status_code == 200 and removed.json()["paused"] == 2
    rows = (
        await db.scalars(
            select(Monitor).order_by(Monitor.created_at).execution_options(populate_existing=True)
        )
    ).all()
    assert [m.paused_reason for m in rows] == [None, None, None, "plan_limit", "plan_limit"]

    # Re-installing the same licence resumes them and re-activates the history entry.
    again = await client.post("/api/admin/licence", json={"licence_text": licence_text})
    assert again.json()["resumed"] == 2
    history = (await client.get("/api/admin/licence")).json()["history"]
    assert len(history) == 1 and history[0]["is_active"]


async def test_limits_apply_across_all_users(selfhosted, client, make_client, db) -> None:  # noqa: F811
    await register(client)
    await _install(client, selfhosted, LicenseLimits(4, 5, 60))
    await client.put("/api/admin/settings", json={"public_signup": True})
    colleague = make_client()
    await register(colleague)
    for c in (client, client, colleague, colleague):
        assert (await c.post("/api/monitors", json=NEW)).status_code == 201
    assert (await colleague.post("/api/monitors", json=NEW)).status_code == 402

    # A smaller licence pauses the newest monitors across the whole installation and raises
    # intervals to the licence minimum.
    await _install(client, selfhosted, LicenseLimits(2, 5, 600), name="Acme Two")
    active = (
        await db.scalars(
            select(Monitor)
            .where(Monitor.is_paused.is_(False))
            .execution_options(populate_existing=True)
        )
    ).all()
    assert len(active) == 2 and all(m.interval_seconds == 600 for m in active)


async def test_selfhosted_admin_endpoints_hidden_in_hosted(client, db) -> None:
    me = await register(client)
    await db.execute(
        update(User).where(User.email == me["user"]["email"]).values(role=UserRole.ADMIN)
    )
    await db.commit()
    for method, path in [
        ("GET", "/api/admin/licence"),
        ("POST", "/api/admin/invitations"),
        ("GET", "/api/admin/setup"),
        ("GET", "/api/admin/invitations"),
    ]:
        r = await client.request(method, path, json={"email": "x@example.com"})
        assert r.status_code == 404, path


async def test_invitation_flow(selfhosted, client, make_client, db) -> None:  # noqa: F811
    await register(client)  # admin; evaluation mode allows exactly 1 user
    invite_email = unique_email("colleague")
    full = await client.post("/api/admin/invitations", json={"email": invite_email})
    assert full.status_code == 402 and full.json()["error"]["code"] == "user_limit"

    await _install(client, selfhosted, LicenseLimits(10, 2, 60))
    r = await client.post("/api/admin/invitations", json={"email": invite_email, "role": "user"})
    assert r.status_code == 201
    assert (
        await client.post("/api/admin/invitations", json={"email": invite_email})
    ).status_code == 409
    # Pending invitations count towards the user limit (2).
    assert (
        await client.post("/api/admin/invitations", json={"email": unique_email()})
    ).status_code == 402
    pending = (await client.get("/api/admin/invitations")).json()
    assert [p["email"] for p in pending] == [invite_email]

    guest = make_client()
    blocked = await guest.post(
        "/api/auth/login", json={"email": invite_email, "password": "anything-1234"}
    )
    assert blocked.status_code == 401  # no usable password before accepting

    body = (
        await db.scalars(
            select(NotificationOutbox.body_text).where(NotificationOutbox.recipient == invite_email)
        )
    ).first()
    token = re.search(r"/accept-invite#([A-Za-z0-9_-]+)", body).group(1)
    weak = await guest.post("/api/auth/accept-invite", json={"token": token, "password": "short"})
    assert weak.status_code == 422
    accepted = await guest.post(
        "/api/auth/accept-invite",
        json={"token": token, "password": PASSWORD, "full_name": "Co Worker"},
    )
    assert accepted.status_code == 200
    me = accepted.json()
    assert me["user"]["email_verified"] is True and me["user"]["role"] == "user"
    assert me["user"]["full_name"] == "Co Worker"
    again = await guest.post("/api/auth/accept-invite", json={"token": token, "password": PASSWORD})
    assert again.status_code == 400
    assert (await client.get("/api/admin/invitations")).json() == []
    login = await make_client().post(
        "/api/auth/login", json={"email": invite_email, "password": PASSWORD}
    )
    assert login.status_code == 200


async def test_revoke_and_resend_invitation(selfhosted, client) -> None:  # noqa: F811
    await register(client)
    await _install(client, selfhosted, LicenseLimits(10, 5, 60))
    uid = (await client.post("/api/admin/invitations", json={"email": unique_email()})).json()["id"]
    assert (await client.post(f"/api/admin/invitations/{uid}/resend")).status_code == 202
    assert (await client.request("DELETE", f"/api/admin/invitations/{uid}")).status_code == 204
    assert (await client.get("/api/admin/invitations")).json() == []
    # Real accounts cannot be removed through the invitation endpoint.
    admin_id = (await client.get("/api/auth/me")).json()["user"]["id"]
    assert (await client.request("DELETE", f"/api/admin/invitations/{admin_id}")).status_code == 404


async def test_first_run_is_race_free(selfhosted, make_client, db) -> None:  # noqa: F811
    """Two people opening a fresh installation at the same moment: exactly one admin."""
    a, b = make_client(), make_client()
    results = await asyncio.gather(
        *(
            c.post(
                "/api/auth/register", json={"email": unique_email(), "password": "Setup-pass-1234"}
            )
            for c in (a, b)
        )
    )
    assert sorted(r.status_code for r in results) == [201, 403]
    admins = (await db.scalars(select(User).where(User.role == UserRole.ADMIN))).all()
    assert len(admins) == 1


async def test_setup_checklist(selfhosted, client) -> None:  # noqa: F811
    await register(client)
    steps = {s["key"]: s["done"] for s in (await client.get("/api/admin/setup")).json()["steps"]}
    assert steps["admin"] is True and steps["licence"] is False and steps["monitor"] is False
    await client.post("/api/monitors", json=NEW)
    steps = {s["key"]: s["done"] for s in (await client.get("/api/admin/setup")).json()["steps"]}
    assert steps["monitor"] is True


async def test_licence_file_on_disk(selfhosted, client, settings, tmp_path, monkeypatch) -> None:  # noqa: F811
    from app.core.db import get_sessionmaker
    from app.enforcement import enforce_instance_job

    await register(client)
    licence_file = tmp_path / "uptivora.license"
    licence_file.write_text(_signed(selfhosted, edition=Edition.PROFESSIONAL))
    monkeypatch.setattr(settings, "license_path", licence_file)
    status = (await client.get("/api/admin/licence")).json()
    assert status["source"] == "file" and status["licence"]["edition"] == "professional"
    me = (await client.get("/api/auth/me")).json()
    assert me["limits"]["max_monitors"] is None  # professional: unlimited
    assert (await enforce_instance_job(get_sessionmaker(), settings))["paused"] == 0
