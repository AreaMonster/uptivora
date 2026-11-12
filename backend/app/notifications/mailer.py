"""SMTP delivery via aiosmtplib. Works with any SMTP server — no email API required."""

from __future__ import annotations

from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

import aiosmtplib

from app.core.config import Settings


class MailerError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class EmailMessageData:
    to: str
    subject: str
    text: str
    html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


# RFC 5322 allows 998-char lines; the 78-char default would RFC 2047-encode long URL headers
# such as List-Unsubscribe, which mail clients then ignore.
MAIL_POLICY = policy.SMTP.clone(max_line_length=998)

# Only these extra headers may be set by callers (no header injection via stored data).
ALLOWED_HEADERS = {"List-Unsubscribe", "List-Unsubscribe-Post", "X-Uptivora-Kind"}


def build_message(settings: Settings, data: EmailMessageData) -> EmailMessage:
    msg = EmailMessage(policy=MAIL_POLICY)
    from_addr = parseaddr(settings.smtp_from)[1] or "alerts@localhost"
    msg["From"] = settings.smtp_from
    msg["To"] = data.to
    msg["Subject"] = data.subject.replace("\r", " ").replace("\n", " ")
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=from_addr.rsplit("@", 1)[-1])
    msg["Auto-Submitted"] = "auto-generated"
    for name, value in data.headers.items():
        if name in ALLOWED_HEADERS and not any(c in value for c in "\r\n"):
            msg[name] = value
    msg.set_content(data.text)
    if data.html:
        msg.add_alternative(data.html, subtype="html")
    return msg


async def send_email(settings: Settings, data: EmailMessageData) -> None:
    if not settings.smtp_host:
        raise MailerError("SMTP is not configured (UPTIVORA_SMTP_HOST)")
    message = build_message(settings, data)
    # Serialize ourselves: aiosmtplib would re-flatten with the 78-char default policy and
    # encode List-Unsubscribe. Envelope sender/recipient are passed explicitly.
    raw = message.as_bytes(policy=MAIL_POLICY)
    sender = parseaddr(settings.smtp_from)[1] or "alerts@localhost"
    try:
        await aiosmtplib.send(
            raw,
            sender=sender,
            recipients=[data.to],
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password.get_secret_value() or None,
            use_tls=settings.smtp_security == "tls",
            start_tls=True if settings.smtp_security == "starttls" else False,
            timeout=settings.smtp_timeout_seconds,
        )
    except (aiosmtplib.SMTPException, OSError, TimeoutError) as exc:
        raise MailerError(f"{type(exc).__name__}: {exc}") from exc
