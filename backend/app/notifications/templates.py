"""Email bodies (plain text + minimal inline-styled HTML). No external images or trackers."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


def _html(title: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> str:
    body = "".join(
        f'<p style="margin:0 0 16px;line-height:1.55">{escape(p)}</p>' for p in paragraphs
    )
    if button:
        label, url = button
        body += (
            f'<p style="margin:24px 0"><a href="{escape(url, quote=True)}" '
            'style="background:#10B981;color:#04140D;text-decoration:none;font-weight:600;'
            f'padding:12px 20px;border-radius:8px;display:inline-block">{escape(label)}</a></p>'
            f'<p style="margin:0 0 16px;font-size:13px;color:#64748B">Or open: '
            f"{escape(url)}</p>"
        )
    return (
        '<!doctype html><html><body style="margin:0;background:#F1F5F9;'
        'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0F172A">'
        '<div style="max-width:560px;margin:0 auto;padding:32px 16px">'
        '<div style="font-weight:700;letter-spacing:.08em;color:#0B1220;margin-bottom:16px">'
        "UPTIVORA</div>"
        '<div style="background:#fff;border-radius:12px;padding:28px">'
        f'<h1 style="font-size:20px;margin:0 0 16px">{escape(title)}</h1>{body}</div>'
        '<p style="font-size:12px;color:#64748B;margin-top:16px">'
        "You receive this email because of your Uptivora account.</p></div></body></html>"
    )


def _text(title: str, paragraphs: list[str], link: str | None = None) -> str:
    parts = [title, "", *paragraphs]
    if link:
        parts += ["", link]
    parts += ["", "— Uptivora"]
    return "\n".join(parts)


def verify_email(name: str, url: str) -> RenderedEmail:
    title = "Confirm your email address"
    paras = [
        f"Hi {name or 'there'},",
        "Please confirm your email address so we can send you monitoring alerts. "
        "The link is valid for 48 hours.",
    ]
    return RenderedEmail(
        "Confirm your Uptivora email address",
        _text(title, paras, url),
        _html(title, paras, ("Confirm email", url)),
    )


def reset_password(name: str, url: str) -> RenderedEmail:
    title = "Reset your password"
    paras = [
        f"Hi {name or 'there'},",
        "Someone (hopefully you) asked to reset your Uptivora password. The link is valid for "
        "1 hour. If you did not request this, you can ignore this email.",
    ]
    return RenderedEmail(
        "Reset your Uptivora password",
        _text(title, paras, url),
        _html(title, paras, ("Choose a new password", url)),
    )


def password_changed(name: str, url: str) -> RenderedEmail:
    title = "Your password was changed"
    paras = [
        f"Hi {name or 'there'},",
        "The password for your Uptivora account was just changed and other sessions were "
        "signed out. If this was not you, reset your password immediately.",
    ]
    return RenderedEmail(
        "Your Uptivora password was changed",
        _text(title, paras, url),
        _html(title, paras, ("Reset password", url)),
    )
