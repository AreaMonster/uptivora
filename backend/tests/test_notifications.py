"""Alert contacts, confirmation, unsubscribe, test alerts, delivery log, templates."""

from __future__ import annotations

import re
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select

from app.models import AlertContact, NotificationKind, NotificationOutbox, NotificationSettings
from app.notifications import templates
from tests.conftest import register, unique_email


async def _outbox(db, recipient: str) -> list[NotificationOutbox]:
    return list(
        (
            await db.scalars(
                select(NotificationOutbox)
                .where(NotificationOutbox.recipient == recipient)
                .order_by(NotificationOutbox.created_at)
                .execution_options(populate_existing=True)
            )
        ).all()
    )


async def _token_from(db, recipient: str, path: str) -> str:
    for row in reversed(await _outbox(db, recipient)):
        m = re.search(rf"/{path}#([A-Za-z0-9_-]+)", row.body_text)
        if m:
            return m.group(1)
    raise AssertionError(f"no {path} link sent to {recipient}")


async def verified_user(client, db) -> dict:
    me = await register(client)
    token = await _token_from(db, me["user"]["email"], "verify-email")
    assert (await client.post("/api/auth/verify-email", json={"token": token})).status_code == 200
    return me


async def test_contact_lifecycle(client, make_client, db) -> None:
    me = await verified_user(client, db)
    ops = unique_email("ops")
    created = await client.post("/api/account/alert-contacts", json={"email": ops.upper()})
    assert created.status_code == 201 and created.json()["status"] == "pending"
    contact_id = created.json()["id"]
    assert created.json()["email"] == ops

    # Confirmation email went to the contact, mentions the owner, and is confirmable publicly.
    mail = (await _outbox(db, ops))[-1]
    assert me["user"]["email"] in mail.body_text and "ignore" in mail.body_text
    token = await _token_from(db, ops, "confirm-alerts")
    stranger = make_client()
    ok = await stranger.post("/api/alert-contacts/confirm", json={"token": token})
    assert ok.status_code == 200 and ok.json()["email"] == ops
    again = await stranger.post("/api/alert-contacts/confirm", json={"token": token})
    assert again.status_code == 400

    listed = (await client.get("/api/account/alert-contacts")).json()
    assert [(c["email"], c["status"]) for c in listed] == [(ops, "confirmed")]

    # Disable / enable / delete
    off = await client.patch(
        f"/api/account/alert-contacts/{contact_id}", json={"is_enabled": False}
    )
    assert off.json()["is_enabled"] is False
    assert (await client.delete(f"/api/account/alert-contacts/{contact_id}")).status_code == 204
    assert (await client.get("/api/account/alert-contacts")).json() == []


async def test_contact_validation_and_limits(client, db) -> None:
    me = await verified_user(client, db)
    own = await client.post("/api/account/alert-contacts", json={"email": me["user"]["email"]})
    assert own.status_code == 422
    first = unique_email("c")
    assert (
        await client.post("/api/account/alert-contacts", json={"email": first})
    ).status_code == 201
    dup = await client.post("/api/account/alert-contacts", json={"email": first})
    assert dup.status_code == 409
    for _ in range(4):
        r = await client.post("/api/account/alert-contacts", json={"email": unique_email("c")})
        assert r.status_code == 201
    sixth = await client.post("/api/account/alert-contacts", json={"email": unique_email("c")})
    assert sixth.status_code == 409 and "up to 5" in sixth.json()["error"]["message"]


async def test_contacts_are_private(client, make_client, db) -> None:
    await verified_user(client, db)
    cid = (
        await client.post("/api/account/alert-contacts", json={"email": unique_email("p")})
    ).json()["id"]
    other = make_client()
    await register(other)
    assert (
        await other.patch(f"/api/account/alert-contacts/{cid}", json={"is_enabled": False})
    ).status_code == 404
    assert (await other.delete(f"/api/account/alert-contacts/{cid}")).status_code == 404
    assert (await other.post(f"/api/account/alert-contacts/{cid}/resend")).status_code == 404
    assert (await other.get("/api/account/alert-contacts")).json() == []


async def test_test_alert_reaches_all_confirmed_recipients(client, make_client, db) -> None:
    me = await verified_user(client, db)
    ops = unique_email("ops")
    await client.post("/api/account/alert-contacts", json={"email": ops})
    pending = unique_email("pending")
    await client.post("/api/account/alert-contacts", json={"email": pending})
    token = await _token_from(db, ops, "confirm-alerts")
    await make_client().post("/api/alert-contacts/confirm", json={"token": token})

    resp = await client.post("/api/account/notifications/test")
    assert resp.status_code == 202
    assert sorted(resp.json()["recipients"]) == sorted([me["user"]["email"], ops])
    contact_mail = [m for m in await _outbox(db, ops) if m.kind == NotificationKind.TEST][0]
    assert contact_mail.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "/api/notifications/unsubscribe?" in contact_mail.headers["List-Unsubscribe"]
    assert not [m for m in await _outbox(db, pending) if m.kind == NotificationKind.TEST]

    log = (await client.get("/api/account/notifications/log")).json()
    assert {e["recipient"] for e in log if e["kind"] == "test"} == {me["user"]["email"], ops}
    assert all(e["kind"] != "account" for e in log)  # confirmations/resets are not listed


async def test_test_alert_without_recipients(client) -> None:
    await register(client)  # email not confirmed, no contacts
    resp = await client.post("/api/account/notifications/test")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "no_recipients"


async def test_one_click_unsubscribe_for_contact(client, make_client, db) -> None:
    await verified_user(client, db)
    ops = unique_email("ops")
    cid = uuid.UUID(
        (await client.post("/api/account/alert-contacts", json={"email": ops})).json()["id"]
    )
    await make_client().post(
        "/api/alert-contacts/confirm", json={"token": await _token_from(db, ops, "confirm-alerts")}
    )
    await client.post("/api/account/notifications/test")
    mail = [m for m in await _outbox(db, ops) if m.kind == NotificationKind.TEST][0]
    url = mail.headers["List-Unsubscribe"].strip("<>")
    path_qs = url.split("://", 1)[1].split("/", 1)[1]
    query = urlsplit(url).query

    mail_client = make_client()  # e.g. Gmail's servers: no cookies, form body
    tampered = await mail_client.post(
        "/" + path_qs.replace("t=", "t=x"),
        content=b"List-Unsubscribe=One-Click",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert tampered.status_code == 400
    done = await mail_client.post(
        "/api/notifications/unsubscribe?" + query,
        content=b"List-Unsubscribe=One-Click",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert done.status_code == 200 and done.json()["email"] == ops
    contact = await db.get(AlertContact, cid, populate_existing=True)
    assert contact.is_enabled is False and contact.verified_at is None  # opt-out sticks
    # Unsubscribed contact no longer receives tests.
    recipients = (await client.post("/api/account/notifications/test")).json()["recipients"]
    assert ops not in recipients


async def test_account_unsubscribe_via_page_json(client, make_client, db) -> None:
    me = await verified_user(client, db)
    await client.post("/api/account/notifications/test")
    mail = [m for m in await _outbox(db, me["user"]["email"]) if m.kind == NotificationKind.TEST][0]
    m = re.search(
        r"localhost:3000/unsubscribe\?k=(a)&id=([0-9a-f-]+)&t=([A-Za-z0-9_-]+)", mail.body_text
    )
    assert m, "plain-text body must contain the unsubscribe page link"
    resp = await make_client().post(
        "/api/notifications/unsubscribe", json={"k": m.group(1), "id": m.group(2), "t": m.group(3)}
    )
    assert resp.status_code == 200
    prefs = await db.get(NotificationSettings, uuid.UUID(me["user"]["id"]), populate_existing=True)
    assert prefs.send_to_account_email is False
    # Cannot unsubscribe someone else with a token for a different id
    bad = await make_client().post(
        "/api/notifications/unsubscribe", json={"k": "a", "id": str(uuid.uuid4()), "t": m.group(3)}
    )
    assert bad.status_code == 400


def test_templates_escape_and_stay_self_contained() -> None:
    footer = templates.Footer(
        manage_url="https://app.example.com/settings",
        unsubscribe_url="https://app.example.com/unsubscribe?x=1&y=2",
        one_click_url="https://app.example.com/api/u?x=1&y=2",
    )
    nasty = '<script>alert("x")</script>\nBcc: victim@example.com'
    for mail in [
        templates.monitor_down(
            nasty,
            "https://a.example.com",
            "<b>boom</b>",
            "now",
            "https://app.example.com/i/1",
            footer,
        ),
        templates.monitor_up(nasty, "https://a.example.com", 3725, "x", "https://l", footer),
        templates.ssl_expiring(nasty, "https://a.example.com", 3, "soon", "https://l", footer),
        templates.ssl_expiring(nasty, "https://a.example.com", -1, "past", "https://l", footer),
        templates.alert_test_email(nasty, "https://l", footer),
    ]:
        assert "<script>" not in mail.html and "&lt;script&gt;" in mail.html
        assert "\n" not in mail.subject and "\r" not in mail.subject
        assert "<img" not in mail.html and "@import" not in mail.html  # no remote content
        assert "y=2" in mail.text and "&amp;y=2" in mail.html  # links escaped in HTML
        assert mail.headers["List-Unsubscribe"] == "<https://app.example.com/api/u?x=1&y=2>"
    plain = templates.monitor_down("Shop", "https://s", "c", "t", "https://l")
    assert plain.headers == {} and "Unsubscribe" not in plain.text
    assert templates.fmt_duration(3725) == "1 h 2 min"
    assert templates.fmt_duration(200000) == "2 d 7 h"


async def test_body_link_goes_to_page_and_header_to_one_click_endpoint(client, db) -> None:
    me = await verified_user(client, db)
    await client.post("/api/account/notifications/test")
    mail = [m for m in await _outbox(db, me["user"]["email"]) if m.kind == NotificationKind.TEST][0]
    assert "http://localhost:3000/unsubscribe?k=a&" in mail.body_text
    assert "/api/notifications/unsubscribe" not in mail.body_text  # POST-only endpoint
    assert "/api/notifications/unsubscribe" not in mail.body_html
    assert mail.headers["List-Unsubscribe"].startswith(
        "<http://localhost:3000/api/notifications/unsubscribe?k=a&"
    )
