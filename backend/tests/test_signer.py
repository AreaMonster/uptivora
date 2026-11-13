"""Isolated licence signer (app.signer) and automatic licence fulfilment."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import SecretStr
from sqlalchemy import select, update

from app.billing import licences, signer_client
from app.core.db import get_sessionmaker
from app.licensing import keys, trusted_keys, verify_license
from app.licensing.signing import public_key_b64
from app.models import LicenseOrder, NotificationOutbox
from app.signer.service import create_app, load_signing_key
from tests.conftest import register

TOKEN = "t" * 40


def signer_settings(settings, tmp_path, key_id: str, **kw):
    return settings.model_copy(
        update={
            "signer_token": SecretStr(TOKEN),
            "signer_key_id": key_id,
            "signer_data_dir": tmp_path / "signer-data",
            **kw,
        }
    )


def make_key(monkeypatch, key_id: str) -> Ed25519PrivateKey:
    key = Ed25519PrivateKey.generate()
    monkeypatch.setitem(keys.PRODUCTION_PUBLIC_KEYS, key_id, public_key_b64(key))
    return key


def body(order_id: str | None = None, **kw) -> dict:
    return {
        "order_id": order_id or str(uuid.uuid4()),
        "edition": "starter",
        "licensee_name": "Acme AG",
        "licensee_email": "it@acme.ch",
        "limits": {"max_monitors": 25, "max_users": 3, "min_interval_seconds": 60},
        **kw,
    }


def client_for(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://signer",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )


# --- the service ----------------------------------------------------------------------------


async def test_requests_need_the_token(settings, tmp_path, monkeypatch) -> None:
    app = create_app(signer_settings(settings, tmp_path, "s1"), make_key(monkeypatch, "s1"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://signer"
    ) as c:
        assert (await c.post("/sign", json=body())).status_code == 401
        wrong = await c.post("/sign", json=body(), headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 401


async def test_signs_verifiable_licences_once_per_order(settings, tmp_path, monkeypatch) -> None:
    app = create_app(signer_settings(settings, tmp_path, "s1"), make_key(monkeypatch, "s1"))
    order = str(uuid.uuid4())
    async with client_for(app) as c:
        first = (await c.post("/sign", json=body(order))).json()
        again = (await c.post("/sign", json=body(order))).json()
    lic = verify_license(first["licence"], trusted_keys("production"))
    assert lic.licensee_name == "Acme AG" and lic.limits.max_monitors == 25
    assert again["licence"] == first["licence"] and again["reused"] is True
    # The journal survives a restart: still no second licence for the same order.
    app2 = create_app(signer_settings(settings, tmp_path, "s1"), make_key(monkeypatch, "s1"))
    async with client_for(app2) as c:
        assert (await c.post("/sign", json=body(order))).json()["license_id"] == first["license_id"]


async def test_daily_limit_caps_new_licences(settings, tmp_path, monkeypatch) -> None:
    app = create_app(
        signer_settings(settings, tmp_path, "s1", signer_daily_limit=2), make_key(monkeypatch, "s1")
    )
    async with client_for(app) as c:
        a = str(uuid.uuid4())
        assert (await c.post("/sign", json=body(a))).status_code == 200
        assert (await c.post("/sign", json=body())).status_code == 200
        assert (await c.post("/sign", json=body())).status_code == 429
        assert (await c.post("/sign", json=body(a))).status_code == 200  # known order


async def test_reissue_cannot_create_new_entitlements(settings, tmp_path, monkeypatch) -> None:
    old = create_app(signer_settings(settings, tmp_path, "s1"), make_key(monkeypatch, "s1"))
    order = str(uuid.uuid4())
    async with client_for(old) as c:
        first = (await c.post("/sign", json=body(order))).json()
        unknown = await c.post("/sign", json=body(reissue=True))
        assert unknown.status_code == 404
    # Key rotation: a new key id, same journal.
    new = create_app(signer_settings(settings, tmp_path, "s2"), make_key(monkeypatch, "s2"))
    greedy = body(
        order,
        reissue=True,
        edition="professional",
        licensee_name="Someone Else",
        limits={"max_monitors": 0, "max_users": 0, "min_interval_seconds": 30},
    )
    async with client_for(new) as c:
        second = (await c.post("/sign", json=greedy)).json()
    lic = verify_license(second["licence"], trusted_keys("production"))
    assert second["license_id"] != first["license_id"] and lic.key_id == "s2"
    assert lic.edition.value == "starter" and lic.licensee_name == "Acme AG"
    assert lic.limits.max_monitors == 25


def test_refuses_a_key_installations_would_not_trust(settings, tmp_path, monkeypatch) -> None:
    key = Ed25519PrivateKey.generate()
    path = tmp_path / "k.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    s = signer_settings(settings, tmp_path, "s9", signer_key_path=path, env="production")
    with pytest.raises(RuntimeError, match="does not match"):
        load_signing_key(s)
    monkeypatch.setitem(keys.PRODUCTION_PUBLIC_KEYS, "s9", public_key_b64(key))
    assert public_key_b64(load_signing_key(s)) == public_key_b64(key)


# --- automatic fulfilment through the API ---------------------------------------------------


@pytest.fixture
def wired_signer(settings, tmp_path, monkeypatch):
    """The API talks to an in-process signer app (instead of http://signer:8100)."""
    key = make_key(monkeypatch, "shop1")
    app = create_app(signer_settings(settings, tmp_path, "shop1"), key)
    monkeypatch.setattr(settings, "signer_url", "http://signer")
    monkeypatch.setattr(settings, "signer_token", SecretStr(TOKEN))
    monkeypatch.setattr(settings, "signer_key_id", "shop1")
    monkeypatch.setattr(signer_client, "transport", httpx.ASGITransport(app=app))
    return app


ORDER = {
    "product_code": "selfhosted-starter",
    "licensee_name": "Acme AG",
    "licensee_email": "it@acme.ch",
}


async def test_paid_order_is_signed_and_emailed_immediately(client, db, wired_signer) -> None:
    me = await register(client)
    r = await client.post("/api/billing/licence-orders", json=ORDER)
    assert r.status_code == 201 and r.json()["status"] == "fulfilled"
    dl = await client.get(f"/api/billing/licence-orders/{r.json()['id']}/download")
    lic = verify_license(dl.text, trusted_keys("production"))
    assert lic.licensee_name == "Acme AG" and lic.key_id == "shop1"
    mails = (
        await db.scalars(
            select(NotificationOutbox.subject).where(
                NotificationOutbox.recipient == me["user"]["email"]
            )
        )
    ).all()
    assert any("licence is ready" in s for s in mails)


async def test_signer_outage_is_retried_by_the_worker(
    client, db, settings, wired_signer, monkeypatch
) -> None:
    await register(client)

    class Down(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectError("signer down")

    monkeypatch.setattr(signer_client, "transport", Down())
    r = await client.post("/api/billing/licence-orders", json=ORDER)
    assert r.status_code == 201 and r.json()["status"] == "paid"  # sale is not lost
    order_id = uuid.UUID(r.json()["id"])
    await db.execute(
        update(LicenseOrder)
        .where(LicenseOrder.id == order_id)
        .values(paid_at=datetime.now(UTC) - timedelta(minutes=2))
    )
    await db.commit()

    monkeypatch.setattr(signer_client, "transport", httpx.ASGITransport(app=wired_signer))
    assert await licences.fulfil_pending_orders(get_sessionmaker(), settings) >= 1
    order = await db.scalar(
        select(LicenseOrder)
        .where(LicenseOrder.id == order_id)
        .execution_options(populate_existing=True)
    )
    assert order.status.value == "fulfilled"


async def test_reissue_after_key_rotation(
    client, db, settings, wired_signer, tmp_path, monkeypatch
) -> None:
    await register(client)
    r = await client.post("/api/billing/licence-orders", json=ORDER)
    order_id = uuid.UUID(r.json()["id"])

    rotated = create_app(
        signer_settings(settings, tmp_path, "shop2"), make_key(monkeypatch, "shop2")
    )
    monkeypatch.setattr(settings, "signer_key_id", "shop2")
    monkeypatch.setattr(signer_client, "transport", httpx.ASGITransport(app=rotated))
    done, failed = await licences.reissue_licences(
        get_sessionmaker(), settings, from_key_id="shop1"
    )
    assert done >= 1  # other tests' orders were signed by signers this one never saw
    order = await db.scalar(
        select(LicenseOrder)
        .where(LicenseOrder.id == order_id)
        .execution_options(populate_existing=True)
    )
    assert signer_client.licence_key_id(order.license_text) == "shop2"
    assert verify_license(order.license_text, trusted_keys("production")).licensee_name == (
        "Acme AG"
    )
