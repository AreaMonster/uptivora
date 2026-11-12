"""Subscriptions, TEST MODE payments, renewals, licence store, webhooks."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from licensegen.core import build_payload, public_key_b64, sign_payload
from sqlalchemy import select, update

from app.billing.providers import WebhookSignatureError, verify_stripe_signature
from app.billing.router import record_webhook_event
from app.billing.service import add_month, process_due_subscriptions, prorate
from app.core.db import get_sessionmaker
from app.licensing import Edition
from app.models import (
    Monitor,
    NotificationOutbox,
    Payment,
    Subscription,
    SubscriptionStatus,
    User,
    UserRole,
)
from tests.conftest import register

MON = {"name": "Site", "url": "https://site.example.com", "interval_seconds": 60}


def test_add_month_and_prorate() -> None:
    assert add_month(datetime(2026, 1, 31, tzinfo=UTC)) == datetime(2026, 2, 28, tzinfo=UTC)
    assert add_month(datetime(2028, 1, 31, tzinfo=UTC)) == datetime(2028, 2, 29, tzinfo=UTC)
    assert add_month(datetime(2026, 12, 15, 9, tzinfo=UTC)) == datetime(2027, 1, 15, 9, tzinfo=UTC)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 31, tzinfo=UTC)
    assert prorate(500, 1200, start, end, start + timedelta(days=15)) == 350
    assert prorate(500, 1200, start, end, end + timedelta(days=1)) == 0
    assert prorate(1200, 500, start, end, start) == 0  # never negative


async def _sub(db, user_id: str) -> Subscription | None:
    return await db.scalar(
        select(Subscription)
        .where(Subscription.user_id == uuid.UUID(user_id))
        .order_by(Subscription.created_at.desc())
        .execution_options(populate_existing=True)
    )


async def _expire_period(db, user_id: str, *, by: timedelta = timedelta(seconds=1)) -> None:
    await db.execute(
        update(Subscription)
        .where(
            Subscription.user_id == uuid.UUID(user_id),
            Subscription.status.in_(["active", "cancelled", "past_due"]),
        )
        .values(
            current_period_end=datetime.now(UTC) - by,
            current_period_start=datetime.now(UTC) - by - timedelta(days=30),
        )
    )
    await db.commit()


async def _run_job(settings) -> dict:
    return await process_due_subscriptions(get_sessionmaker(), settings)


async def _mails(db, email: str) -> list[str]:
    return list(
        (
            await db.scalars(
                select(NotificationOutbox.subject)
                .where(NotificationOutbox.recipient == email)
                .order_by(NotificationOutbox.created_at)
            )
        ).all()
    )


async def test_subscribe_receipt_and_limits(client, db) -> None:
    me = await register(client)
    q = (await client.get("/api/billing/quote", params={"plan": "starter"})).json()
    assert q["action"] == "subscribe" and q["amount_cents"] == 500 and q["test_mode"] is True
    r = await client.post("/api/billing/subscribe", json={"plan_code": "starter"})
    assert r.status_code == 200 and r.json() == {"action": "subscribe", "charged_cents": 500}
    summary = (await client.get("/api/billing")).json()
    assert summary["subscription"]["plan"]["code"] == "starter"
    assert summary["subscription"]["is_test"] is True
    assert summary["payments"][0]["status"] == "succeeded" and summary["payments"][0]["is_test"]
    assert (await client.get("/api/auth/me")).json()["limits"]["plan_code"] == "starter"
    subjects = await _mails(db, me["user"]["email"])
    assert any(s.startswith("[TEST] Uptivora receipt: CHF 5.00") for s in subjects)
    same = await client.post("/api/billing/subscribe", json={"plan_code": "starter"})
    assert same.json()["action"] == "none"


async def test_declined_payment_creates_no_subscription(client, db) -> None:
    me = await register(client)
    r = await client.post(
        "/api/billing/subscribe", json={"plan_code": "pro", "simulate": "decline"}
    )
    assert r.status_code == 402 and r.json()["error"]["code"] == "payment_declined"
    assert await _sub(db, me["user"]["id"]) is None
    failed = await db.scalar(select(Payment).where(Payment.user_id == uuid.UUID(me["user"]["id"])))
    assert failed.status == "failed" and failed.is_test


async def test_prorated_upgrade_is_immediate(client, db) -> None:
    me = await register(client)
    await client.post("/api/billing/subscribe", json={"plan_code": "starter"})
    now = datetime.now(UTC)
    await db.execute(
        update(Subscription)
        .where(Subscription.user_id == uuid.UUID(me["user"]["id"]))
        .values(
            current_period_start=now - timedelta(days=15),
            current_period_end=now + timedelta(days=15),
        )
    )
    await db.commit()
    q = (await client.get("/api/billing/quote", params={"plan": "pro"})).json()
    assert q["action"] == "upgrade" and 345 <= q["amount_cents"] <= 355
    r = await client.post("/api/billing/subscribe", json={"plan_code": "pro"})
    assert r.json()["action"] == "upgrade"
    assert (await client.get("/api/auth/me")).json()["limits"]["plan_code"] == "pro"


async def test_downgrade_at_period_end_pauses_excess_monitors(client, db, settings) -> None:
    me = await register(client)
    await client.post("/api/billing/subscribe", json={"plan_code": "pro"})
    ids = [
        (await client.post("/api/monitors", json={**MON, "name": f"M{i}"})).json()["id"]
        for i in range(5)
    ]
    r = await client.post("/api/billing/subscribe", json={"plan_code": "starter"})
    assert r.json()["action"] == "downgrade" and r.json()["charged_cents"] == 0
    summary = (await client.get("/api/billing")).json()
    assert summary["subscription"]["pending_plan"]["code"] == "starter"
    assert summary["subscription"]["plan"]["code"] == "pro"  # still pro until period end

    await _expire_period(db, me["user"]["id"])
    stats = await _run_job(settings)
    assert stats.get("renewed", 0) >= 1
    sub = await _sub(db, me["user"]["id"])
    assert sub.status == SubscriptionStatus.ACTIVE and sub.pending_plan_id is None
    me_now = (await client.get("/api/auth/me")).json()
    assert me_now["limits"]["plan_code"] == "starter" and me_now["usage"]["active_monitors"] == 3
    monitors = {m["id"]: m for m in (await client.get("/api/monitors")).json()}
    assert [monitors[i]["paused_reason"] for i in ids] == [
        None,
        None,
        None,
        "plan_limit",
        "plan_limit",
    ]
    assert all(monitors[i]["interval_seconds"] == 300 for i in ids[:3])  # raised to plan minimum


async def test_cancel_resume_and_expiry(client, db, settings) -> None:
    me = await register(client)
    await client.post("/api/billing/subscribe", json={"plan_code": "starter"})
    mid = (await client.post("/api/monitors", json={**MON, "interval_seconds": 300})).json()["id"]
    assert (await client.post("/api/billing/cancel")).json()["status"] == "cancelled"
    assert (await client.get("/api/auth/me")).json()["limits"]["plan_code"] == "starter"
    assert (await client.post("/api/billing/resume")).json()["status"] == "active"
    await client.post("/api/billing/cancel")

    await _expire_period(db, me["user"]["id"])
    await _run_job(settings)
    assert (await _sub(db, me["user"]["id"])).status == SubscriptionStatus.EXPIRED
    me_now = (await client.get("/api/auth/me")).json()
    assert me_now["limits"]["source"] == "no_plan"
    assert (await client.get(f"/api/monitors/{mid}")).json()["monitor"][
        "paused_reason"
    ] == "plan_limit"
    assert any("has ended" in s for s in await _mails(db, me["user"]["email"]))

    # Subscribing again resumes the monitor automatically.
    await client.post("/api/billing/subscribe", json={"plan_code": "starter"})
    assert (await client.get(f"/api/monitors/{mid}")).json()["monitor"]["is_paused"] is False


async def test_failed_renewal_past_due_retry_and_grace(client, db, settings) -> None:
    me = await register(client)
    await client.post("/api/billing/subscribe", json={"plan_code": "starter"})
    assert (
        await client.put("/api/billing/test-settings", json={"simulate_renewal_failure": True})
    ).status_code == 200
    await _expire_period(db, me["user"]["id"])
    await _run_job(settings)
    sub = await _sub(db, me["user"]["id"])
    assert sub.status == SubscriptionStatus.PAST_DUE
    # Grace period: still on the plan
    assert (await client.get("/api/auth/me")).json()["limits"]["plan_code"] == "starter"
    assert any("payment failed" in s for s in await _mails(db, me["user"]["email"]))
    blocked = await client.post("/api/billing/subscribe", json={"plan_code": "pro"})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "past_due"
    # The job does not retry again within 24 h
    assert "renewed" not in await _run_job(settings)

    declined = await client.post("/api/billing/retry", json={"simulate": "decline"})
    assert declined.status_code == 402
    ok = await client.post("/api/billing/retry", json={"simulate": "success"})
    assert ok.status_code == 200 and ok.json()["status"] == "renewed"
    sub = await _sub(db, me["user"]["id"])
    assert sub.status == SubscriptionStatus.ACTIVE and sub.current_period_end > datetime.now(UTC)


async def test_past_due_expires_after_grace(client, db, settings) -> None:
    me = await register(client)
    await client.post("/api/billing/subscribe", json={"plan_code": "starter"})
    await client.put("/api/billing/test-settings", json={"simulate_renewal_failure": True})
    await _expire_period(db, me["user"]["id"], by=timedelta(days=8))
    await _run_job(settings)  # -> past due
    await db.execute(
        update(Subscription)
        .where(Subscription.user_id == uuid.UUID(me["user"]["id"]))
        .values(last_payment_attempt_at=datetime.now(UTC) - timedelta(days=2))
    )
    await db.commit()
    await _run_job(settings)  # grace (7 days) is over
    assert (await _sub(db, me["user"]["id"])).status == SubscriptionStatus.EXPIRED


async def test_billing_unavailable_cases(client, settings, monkeypatch) -> None:
    await register(client)
    monkeypatch.setattr(settings, "billing_provider", "disabled")
    r = await client.post("/api/billing/subscribe", json={"plan_code": "starter"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "billing_disabled"
    monkeypatch.setattr(settings, "edition", "selfhosted")
    assert (await client.get("/api/billing")).status_code == 404


async def test_admin_assigns_complimentary_plan(client, make_client, db, settings) -> None:
    admin = await register(client)
    await db.execute(
        update(User).where(User.id == uuid.UUID(admin["user"]["id"])).values(role=UserRole.ADMIN)
    )
    await db.commit()
    customer = make_client()
    me = await register(customer)
    r = await client.post(
        f"/api/admin/users/{me['user']['id']}/subscription",
        json={"plan_code": "business", "months": 2},
    )
    assert r.status_code == 200 and r.json()["provider"] == "manual"
    limits = (await customer.get("/api/auth/me")).json()["limits"]
    assert limits["plan_code"] == "business"
    await _expire_period(db, me["user"]["id"])
    await _run_job(settings)
    assert (await _sub(db, me["user"]["id"])).status == SubscriptionStatus.EXPIRED
    assert not any("has ended" in s for s in await _mails(db, me["user"]["email"]))


@pytest.fixture
def dev_key(settings, tmp_path, monkeypatch) -> Ed25519PrivateKey:
    key = Ed25519PrivateKey.generate()
    (tmp_path / "dev-public.key").write_text(public_key_b64(key))
    (tmp_path / "dev-private.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    monkeypatch.setattr(settings, "dev_key_dir", tmp_path)
    return key


def _licence(key, edition: Edition) -> str:
    return sign_payload(
        key,
        build_payload(
            key_id="dev", edition=edition, licensee_name="Acme AG", licensee_email="it@acme.ch"
        ),
    )


async def test_licence_store_end_to_end(client, make_client, db, dev_key) -> None:
    me = await register(client)
    admin = make_client()
    adm = await register(admin)
    await db.execute(
        update(User).where(User.id == uuid.UUID(adm["user"]["id"])).values(role=UserRole.ADMIN)
    )
    await db.commit()

    declined = await client.post(
        "/api/billing/licence-orders",
        json={
            "product_code": "selfhosted-starter",
            "licensee_name": "Acme AG",
            "licensee_email": "it@acme.ch",
            "simulate": "decline",
        },
    )
    assert declined.status_code == 402
    r = await client.post(
        "/api/billing/licence-orders",
        json={
            "product_code": "selfhosted-starter",
            "licensee_name": "Acme AG",
            "licensee_email": "IT@acme.ch",
        },
    )
    assert r.status_code == 201 and r.json()["status"] == "paid"
    order_id = r.json()["id"]
    not_ready = await client.get(f"/api/billing/licence-orders/{order_id}/download")
    assert not_ready.status_code == 409

    paid = (await admin.get("/api/admin/licence-orders", params={"status": "paid"})).json()
    assert order_id in [o["id"] for o in paid]
    wrong = await admin.post(
        f"/api/admin/licence-orders/{order_id}/fulfil",
        json={"licence_text": _licence(dev_key, Edition.PROFESSIONAL)},
    )
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "edition_mismatch"
    forged = await admin.post(
        f"/api/admin/licence-orders/{order_id}/fulfil",
        json={"licence_text": _licence(Ed25519PrivateKey.generate(), Edition.STARTER)},
    )
    assert forged.status_code == 422 and forged.json()["error"]["code"] == "invalid_licence"
    text = _licence(dev_key, Edition.STARTER)
    ok = await admin.post(
        f"/api/admin/licence-orders/{order_id}/fulfil", json={"licence_text": text}
    )
    assert ok.status_code == 200 and ok.json()["status"] == "fulfilled"
    assert any("licence is ready" in s for s in await _mails(db, me["user"]["email"]))

    dl = await client.get(f"/api/billing/licence-orders/{order_id}/download")
    assert dl.status_code == 200 and dl.text.strip() == text.strip()
    assert "attachment" in dl.headers["content-disposition"]
    assert (
        await make_client().get(f"/api/billing/licence-orders/{order_id}/download")
    ).status_code == 401
    stranger = make_client()
    await register(stranger)
    assert (
        await stranger.get(f"/api/billing/licence-orders/{order_id}/download")
    ).status_code == 404

    # The same licence file cannot be attached to a second order.
    r2 = await client.post(
        "/api/billing/licence-orders",
        json={
            "product_code": "selfhosted-starter",
            "licensee_name": "Acme AG",
            "licensee_email": "it@acme.ch",
        },
    )
    reused = await admin.post(
        f"/api/admin/licence-orders/{r2.json()['id']}/fulfil", json={"licence_text": text}
    )
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "licence_reused"
    refund = await admin.post(f"/api/admin/licence-orders/{r2.json()['id']}/refund")
    assert refund.json()["status"] == "refunded"
    summary = (await client.get("/api/billing")).json()
    assert {o["status"] for o in summary["licence_orders"]} >= {"fulfilled", "refunded"}


def _stripe_header(payload: bytes, secret: str, ts: int) -> str:
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def test_stripe_signature_verification() -> None:
    payload = b'{"id":"evt_1","type":"invoice.paid"}'
    secret = "whsec_test"
    ts = 1_800_000_000
    assert (
        verify_stripe_signature(payload, _stripe_header(payload, secret, ts), secret, now=ts + 10)
        == ts
    )
    multi = _stripe_header(payload, secret, ts) + ",v1=deadbeef"
    assert verify_stripe_signature(payload, multi, secret, now=ts)
    bad_cases = [
        (payload, _stripe_header(payload, "other", ts), ts),  # wrong secret
        (payload + b" ", _stripe_header(payload, secret, ts), ts),  # body modified
        (payload, _stripe_header(payload, secret, ts), ts + 301),  # replay / stale
        (payload, "garbage", ts),
        (payload, f"t={ts}", ts),
    ]
    for body, header, now in bad_cases:
        with pytest.raises(WebhookSignatureError):
            verify_stripe_signature(body, header, secret, now=now)
    with pytest.raises(WebhookSignatureError):
        verify_stripe_signature(payload, _stripe_header(payload, "", ts), "", now=ts)


async def test_webhook_events_are_idempotent(db, client) -> None:
    event_id = f"evt_{uuid.uuid4().hex}"
    assert await record_webhook_event(db, "stripe", event_id, "invoice.paid", {"id": event_id})
    assert not await record_webhook_event(db, "stripe", event_id, "invoice.paid", {"id": event_id})
    await db.commit()
    # The endpoint stays inactive while the Stripe provider is disabled.
    assert (await client.post("/api/billing/webhooks/stripe", content=b"{}")).status_code == 404


async def test_monitors_survive_downgrade_never_deleted(client, db, settings) -> None:
    me = await register(client)
    await client.post("/api/billing/subscribe", json={"plan_code": "business"})
    for i in range(6):
        await client.post("/api/monitors", json={**MON, "name": f"B{i}", "interval_seconds": 30})
    await client.post("/api/billing/subscribe", json={"plan_code": "starter"})
    await _expire_period(db, me["user"]["id"])
    await _run_job(settings)
    total = len(
        (
            await db.scalars(
                select(Monitor.id).where(Monitor.owner_id == uuid.UUID(me["user"]["id"]))
            )
        ).all()
    )
    assert total == 6
