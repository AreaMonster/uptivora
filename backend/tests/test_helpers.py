from __future__ import annotations

import json
import socket
import uuid
from datetime import UTC, datetime, timedelta
from urllib.request import urlopen

import pytest
from starlette.requests import Request

from app.core.requestctx import client_ip
from app.models import NotificationKind, NotificationOutbox, OutboxStatus
from app.monitors.status_spec import normalize_status_spec, parse_status_spec, status_matches
from app.notifications.outbox import backoff, drain_outbox, enqueue


def test_status_spec() -> None:
    assert parse_status_spec("200-299, 301") == [(200, 299), (301, 301)]
    assert normalize_status_spec("200,201-201") == "200,201"
    assert status_matches(204, parse_status_spec("200-299"))
    assert not status_matches(500, parse_status_spec("200-299,404"))
    for bad in ["", "2000", "99", "600", "300-200", "abc", ",".join(["200"] * 11)]:
        with pytest.raises(ValueError):
            parse_status_spec(bad)


def _request(peer: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


def test_client_ip_only_trusts_configured_proxies(settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "trusted_proxies", ["127.0.0.1/32", "172.18.0.0/16"])
    # Untrusted peer: header ignored (spoofing attempt)
    assert client_ip(_request("198.51.100.4", "1.2.3.4")) == "198.51.100.4"
    # Trusted proxy: rightmost untrusted hop wins (client-supplied left entries ignored)
    assert client_ip(_request("172.18.0.5", "6.6.6.6, 203.0.113.7")) == "203.0.113.7"
    assert client_ip(_request("127.0.0.1", "203.0.113.7, 172.18.0.9")) == "203.0.113.7"
    assert client_ip(_request("127.0.0.1", "garbage")) == "127.0.0.1"
    assert client_ip(_request("127.0.0.1")) == "127.0.0.1"


def test_backoff_grows_and_caps() -> None:
    assert backoff(1) == timedelta(minutes=1)
    assert backoff(3) == timedelta(minutes=4)
    assert backoff(30) == timedelta(hours=6)


async def _cancel_others(db, keep_key: str) -> None:
    """Keep the drain focused on this test's email (other tests queue many)."""
    from sqlalchemy import update

    await db.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.dedupe_key != keep_key,
            NotificationOutbox.status == OutboxStatus.PENDING,
        )
        .values(status=OutboxStatus.CANCELLED)
    )
    await db.commit()


def _mailpit_up() -> bool:
    try:
        socket.create_connection(("localhost", 1025), timeout=1).close()
        return True
    except OSError:
        return False


async def test_outbox_dedupe_and_delivery_via_smtp(db, settings) -> None:
    if not _mailpit_up():
        pytest.skip("Mailpit not running")
    from app.core.db import get_sessionmaker

    recipient = f"outbox-{uuid.uuid4().hex[:8]}@example.com"
    key = f"test:{uuid.uuid4()}"
    kwargs = dict(
        kind=NotificationKind.ACCOUNT,
        recipient=recipient,
        subject="Hello <b>",
        body_text="Plain body",
        body_html="<p>HTML body</p>",
        dedupe_key=key,
    )
    assert await enqueue(db, **kwargs) is True
    assert await enqueue(db, **kwargs) is False  # duplicate suppressed
    await _cancel_others(db, key)

    sent = await drain_outbox(get_sessionmaker(), settings, batch=500)
    assert sent >= 1
    await db.rollback()
    row = await db.scalar(
        NotificationOutbox.__table__.select()
        .where(NotificationOutbox.dedupe_key == key)
        .with_only_columns(NotificationOutbox.status)
    )
    assert row == OutboxStatus.SENT

    url = f"http://localhost:8025/api/v1/search?query=to:{recipient}"
    with urlopen(url, timeout=5) as resp:  # noqa: S310, ASYNC210 - test-only, local Mailpit
        found = json.load(resp)
    assert found["messages_count"] == 1
    assert found["messages"][0]["Subject"] == "Hello <b>"


async def test_outbox_failure_is_retried_later(db, settings, monkeypatch) -> None:
    from app.core.db import get_sessionmaker

    key = f"fail:{uuid.uuid4()}"
    await enqueue(
        db,
        kind=NotificationKind.ACCOUNT,
        recipient="x@example.com",
        subject="s",
        body_text="b",
        dedupe_key=key,
    )
    await _cancel_others(db, key)
    monkeypatch.setattr(settings, "smtp_host", "")  # "not configured" -> MailerError
    await drain_outbox(get_sessionmaker(), settings, batch=500)
    await db.rollback()
    from sqlalchemy import select

    row = await db.scalar(select(NotificationOutbox).where(NotificationOutbox.dedupe_key == key))
    assert row.status == OutboxStatus.PENDING and row.attempts == 1
    assert "not configured" in row.last_error
    assert row.next_attempt_at > datetime.now(UTC) + timedelta(seconds=30)


def test_list_unsubscribe_header_is_not_encoded(settings) -> None:
    from app.notifications.mailer import EmailMessageData, build_message

    url = (
        "<https://app.example.com/api/notifications/unsubscribe?k=c&id="
        + "a" * 36
        + "&t="
        + "b" * 32
        + ">"
    )
    msg = build_message(
        settings,
        EmailMessageData(
            "x@example.com",
            "Subject",
            "body",
            None,
            {
                "List-Unsubscribe": url,
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                "X-Evil": "no",
                "X-Uptivora-Kind": "a\r\nBcc: victim@example.com",
            },
        ),
    )
    raw = msg.as_bytes()
    assert b"List-Unsubscribe: " + url.encode() in raw
    assert b"X-Evil" not in raw and b"Bcc:" not in raw  # unknown headers / CRLF injection dropped


async def test_smtp_delivery_keeps_unsubscribe_header_literal(settings) -> None:
    """Regression: aiosmtplib re-flattens with a 78-char policy unless we send raw bytes."""
    if not _mailpit_up():
        pytest.skip("Mailpit not running")
    from app.notifications.mailer import EmailMessageData, send_email

    to = f"hdr-{uuid.uuid4().hex[:8]}@example.com"
    base = "https://app.example.com/api/notifications/unsubscribe"
    url = f"<{base}?k=c&id={uuid.uuid4()}&t={'Z' * 32}>"
    await send_email(
        settings, EmailMessageData(to, "RECOVERED: x", "body", None, {"List-Unsubscribe": url})
    )
    with urlopen(f"http://localhost:8025/api/v1/search?query=to:{to}", timeout=5) as r:  # noqa: S310, ASYNC210
        msg_id = json.load(r)["messages"][0]["ID"]
    with urlopen(f"http://localhost:8025/api/v1/message/{msg_id}/headers", timeout=5) as r:  # noqa: S310, ASYNC210
        headers = json.load(r)
    assert headers["List-Unsubscribe"] == [url]
