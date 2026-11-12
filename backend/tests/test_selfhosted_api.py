"""Self-hosted edition behaviour: first-run admin, closed sign-up, licence-based limits."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from licensegen.core import build_payload, public_key_b64, sign_payload
from sqlalchemy import text

from app.licensing import Edition, LicenseLimits
from app.models import AppSetting, InstalledLicense
from tests.conftest import register, unique_email

NEW = {"name": "Intranet status", "url": "https://status.example.com", "interval_seconds": 300}


@pytest.fixture
async def selfhosted(settings, db, tmp_path, monkeypatch: pytest.MonkeyPatch):
    await db.execute(text("TRUNCATE users, installed_licenses, app_settings CASCADE"))
    await db.commit()
    key = Ed25519PrivateKey.generate()
    (tmp_path / "dev-public.key").write_text(public_key_b64(key))
    monkeypatch.setattr(settings, "edition", "selfhosted")
    monkeypatch.setattr(settings, "billing_provider", "disabled")
    monkeypatch.setattr(settings, "dev_key_dir", tmp_path)
    yield key
    await db.execute(text("TRUNCATE users, installed_licenses, app_settings CASCADE"))
    await db.commit()


async def _install(db, key, *, edition=Edition.STARTER, limits=None) -> None:
    payload = build_payload(
        key_id="dev",
        edition=edition,
        licensee_name="Acme GmbH",
        licensee_email="it@acme.ch",
        limits=limits,
    )
    db.add(
        InstalledLicense(
            license_id=payload["license_id"],
            edition=edition.value,
            licensee_name="Acme GmbH",
            raw_text=sign_payload(key, payload),
        )
    )
    await db.commit()


async def test_first_user_is_admin_then_signup_closes(selfhosted, client, make_client, db) -> None:
    cfg = (await client.get("/api/public/config")).json()
    assert cfg["needs_setup"] is True and cfg["billing_enabled"] is False
    me = await register(client)
    assert me["user"]["role"] == "admin"
    closed = await make_client().post(
        "/api/auth/register", json={"email": unique_email(), "password": "Some-Pass-word-1"}
    )
    assert closed.status_code == 403 and closed.json()["error"]["code"] == "registration_closed"
    assert (await client.get("/api/public/plans")).json() == {"plans": [], "licences": []}

    db.add(AppSetting(key="public_signup", value=True))
    await db.commit()
    # Unlicensed: max 1 user, so sign-up stays closed even when enabled.
    again = await make_client().post(
        "/api/auth/register", json={"email": unique_email(), "password": "Some-Pass-word-1"}
    )
    assert again.status_code == 403


async def test_unlicensed_limits(selfhosted, client) -> None:
    me = await register(client)
    assert me["limits"]["source"] == "unlicensed" and me["limits"]["max_monitors"] == 3
    # Admins are NOT exempt in self-hosted: limits are per installation.
    assert (
        await client.post("/api/monitors", json={**NEW, "interval_seconds": 60})
    ).status_code == 402
    for i in range(3):
        assert (
            await client.post("/api/monitors", json={**NEW, "name": f"M{i}"})
        ).status_code == 201
    assert (await client.post("/api/monitors", json=NEW)).status_code == 402


async def test_licence_limits_apply_instance_wide(selfhosted, client, make_client, db) -> None:
    await register(client)
    await _install(
        db, selfhosted, limits=LicenseLimits(max_monitors=2, max_users=5, min_interval_seconds=60)
    )
    me = (await client.get("/api/auth/me")).json()
    assert me["limits"]["source"] == "licence" and me["limits"]["licensee"] == "Acme GmbH"
    assert me["limits"]["scope"] == "instance"
    assert (
        await client.post("/api/monitors", json={**NEW, "interval_seconds": 60})
    ).status_code == 201

    db.add(AppSetting(key="public_signup", value=True))
    await db.commit()
    colleague = make_client()
    other = await register(colleague)
    assert other["user"]["role"] == "user"
    assert (await colleague.post("/api/monitors", json=NEW)).status_code == 201
    # The installation-wide limit of 2 is reached, regardless of which user asks.
    assert (await client.post("/api/monitors", json=NEW)).status_code == 402


async def test_professional_is_unlimited(selfhosted, client, db) -> None:
    await register(client)
    await _install(db, selfhosted, edition=Edition.PROFESSIONAL)
    me = (await client.get("/api/auth/me")).json()
    assert me["limits"]["max_monitors"] is None and me["limits"]["min_interval_seconds"] == 30
    assert (
        await client.post("/api/monitors", json={**NEW, "interval_seconds": 30})
    ).status_code == 201


async def test_forged_licence_falls_back_to_unlicensed(selfhosted, client, db) -> None:
    await register(client)
    forger = Ed25519PrivateKey.generate()
    await _install(db, forger, edition=Edition.PROFESSIONAL)
    me = (await client.get("/api/auth/me")).json()
    assert me["limits"]["source"] == "unlicensed" and me["limits"]["max_monitors"] == 3
