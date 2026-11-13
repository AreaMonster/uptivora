"""Email bodies: plain text + minimal inline-styled HTML.

No external images, fonts, tracking pixels or remote CSS. Every value is HTML-escaped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    text: str
    html: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Footer:
    """Links appended to every alert: manage settings and (for contacts) unsubscribe."""

    manage_url: str | None = None
    unsubscribe_url: str | None = None  # page with a confirm button (link in the body)
    one_click_url: str | None = None  # RFC 8058 POST endpoint (List-Unsubscribe header)
    reason: str = "You receive this email because of your Uptivora account."


ACCENT = {"down": "#F43F5E", "up": "#10B981", "warn": "#F59E0B", "info": "#14B8A6"}


def _clean_subject(subject: str) -> str:
    return " ".join(subject.split())[:200]


def _html(
    title: str,
    paragraphs: list[str],
    button: tuple[str, str] | None = None,
    *,
    footer: Footer | None = None,
    tone: str = "info",
    details: list[tuple[str, str]] | None = None,
) -> str:
    footer = footer or Footer()
    body = "".join(
        f'<p style="margin:0 0 14px;line-height:1.55">{escape(p)}</p>' for p in paragraphs
    )
    if details:
        rows = "".join(
            f'<tr><td style="padding:6px 12px 6px 0;color:#64748B;white-space:nowrap;'
            f'vertical-align:top">{escape(k)}</td>'
            f'<td style="padding:6px 0;word-break:break-word">{escape(v)}</td></tr>'
            for k, v in details
        )
        body += (
            '<table role="presentation" style="border-collapse:collapse;font-size:14px;'
            f'margin:4px 0 18px;width:100%">{rows}</table>'
        )
    if button:
        label, url = button
        body += (
            f'<p style="margin:22px 0"><a href="{escape(url, quote=True)}" '
            'style="background:#10B981;color:#04140D;text-decoration:none;font-weight:600;'
            f'padding:12px 20px;border-radius:8px;display:inline-block">{escape(label)}</a></p>'
            '<p style="margin:0 0 6px;font-size:12px;color:#64748B">Or open this link: '
            f"{escape(url)}</p>"
        )
    links = []
    if footer.manage_url:
        links.append(
            f'<a href="{escape(footer.manage_url, quote=True)}" style="color:#475569">'
            "Notification settings</a>"
        )
    if footer.unsubscribe_url:
        links.append(
            f'<a href="{escape(footer.unsubscribe_url, quote=True)}" style="color:#475569">'
            "Unsubscribe</a>"
        )
    link_html = " · ".join(links)
    accent = ACCENT.get(tone, ACCENT["info"])
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width"></head>'
        '<body style="margin:0;background:#F1F5F9;'
        'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0F172A">'
        '<div style="max-width:560px;margin:0 auto;padding:28px 16px">'
        '<div style="font-weight:700;letter-spacing:.14em;color:#0B1220;margin-bottom:14px;'
        'font-size:13px">UPTIVORA</div>'
        f'<div style="background:#fff;border-radius:12px;border-top:4px solid {accent};'
        'padding:26px">'
        f'<h1 style="font-size:20px;line-height:1.3;margin:0 0 14px">{escape(title)}</h1>'
        f"{body}</div>"
        '<p style="font-size:12px;color:#64748B;margin:16px 4px 0;line-height:1.5">'
        f"{escape(footer.reason)}"
        f"{'<br>' + link_html if link_html else ''}</p></div></body></html>"
    )


def _text(
    title: str,
    paragraphs: list[str],
    link: str | None = None,
    *,
    footer: Footer | None = None,
    details: list[tuple[str, str]] | None = None,
) -> str:
    footer = footer or Footer()
    parts = [title, "", *paragraphs]
    if details:
        parts += ["", *(f"{k}: {v}" for k, v in details)]
    if link:
        parts += ["", link]
    parts += ["", "— Uptivora", "", footer.reason]
    if footer.manage_url:
        parts.append(f"Notification settings: {footer.manage_url}")
    if footer.unsubscribe_url:
        parts.append(f"Unsubscribe: {footer.unsubscribe_url}")
    return "\n".join(parts)


def _unsubscribe_headers(footer: Footer | None) -> dict[str, str]:
    if not footer or not footer.one_click_url:
        return {}
    # RFC 8058 one-click unsubscribe (supported by Gmail, Outlook, Apple Mail).
    return {
        "List-Unsubscribe": f"<{footer.one_click_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def fmt_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} seconds"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours} h {minutes} min"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h"


# --- account emails ------------------------------------------------------------------------


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


def confirm_alert_contact(owner_email: str, url: str) -> RenderedEmail:
    title = "Confirm that you want to receive monitoring alerts"
    paras = [
        f"{owner_email} added this address as an alert recipient on Uptivora, a website "
        "monitoring service.",
        "If you confirm, you will receive emails when their websites go down or recover. "
        "Every alert contains a one-click unsubscribe link.",
        "If you do not know this person or did not expect this, simply ignore this email — "
        "you will not receive anything else.",
    ]
    footer = Footer(
        reason="This one-time email was sent because your address was entered on Uptivora. "
        "The link expires in 48 hours."
    )
    return RenderedEmail(
        "Confirm Uptivora monitoring alerts",
        _text(title, paras, url, footer=footer),
        _html(title, paras, ("Confirm alerts", url), footer=footer),
    )


# --- alerts --------------------------------------------------------------------------------


def monitor_down(
    name: str, url: str, cause: str, started: str, link: str, footer: Footer | None = None
) -> RenderedEmail:
    title = f"{name} is down"
    paras = [f"Uptivora cannot reach {url}. We will email you again as soon as it recovers."]
    details = [("Monitor", name), ("URL", url), ("Cause", cause), ("Down since", started)]
    return RenderedEmail(
        _clean_subject(f"🔴 DOWN: {name}"),
        _text(title, paras, link, footer=footer, details=details),
        _html(title, paras, ("View monitor", link), footer=footer, tone="down", details=details),
        _unsubscribe_headers(footer),
    )


def monitor_up(
    name: str,
    url: str,
    duration_seconds: int,
    cause: str,
    link: str,
    footer: Footer | None = None,
) -> RenderedEmail:
    title = f"{name} is back up"
    paras = [f"{url} is reachable again."]
    details = [
        ("Monitor", name),
        ("URL", url),
        ("Outage duration", fmt_duration(duration_seconds)),
    ]
    if cause:
        details.append(("Cause", cause))
    return RenderedEmail(
        _clean_subject(f"🟢 RECOVERED: {name} (down {fmt_duration(duration_seconds)})"),
        _text(title, paras, link, footer=footer, details=details),
        _html(title, paras, ("View incident", link), footer=footer, tone="up", details=details),
        _unsubscribe_headers(footer),
    )


def ssl_expiring(
    name: str, url: str, days: int, expires: str, link: str, footer: Footer | None = None
) -> RenderedEmail:
    if days < 0:
        title = f"The SSL certificate of {name} has expired"
        subject = f"⚠️ SSL certificate EXPIRED: {name}"
        lead = "Visitors now see security warnings. Renew the certificate as soon as possible."
    else:
        title = f"The SSL certificate of {name} expires in {days} days"
        subject = f"⚠️ SSL certificate expires in {days} days: {name}"
        lead = "Renew the certificate (or check your automatic renewal) to avoid an outage."
    details = [("Monitor", name), ("URL", url), ("Expires", expires)]
    return RenderedEmail(
        _clean_subject(subject),
        _text(title, [lead], link, footer=footer, details=details),
        _html(title, [lead], ("View monitor", link), footer=footer, tone="warn", details=details),
        _unsubscribe_headers(footer),
    )


def alert_test_email(owner_email: str, link: str, footer: Footer | None = None) -> RenderedEmail:
    title = "Test alert from Uptivora"
    paras = [
        f"This is a test sent by {owner_email}. If you can read this, alerts reach this inbox.",
        "Tip: add the sender to your contacts so real alerts never land in spam.",
    ]
    return RenderedEmail(
        "✅ Uptivora test alert",
        _text(title, paras, link, footer=footer),
        _html(title, paras, ("Open Uptivora", link), footer=footer, tone="info"),
        _unsubscribe_headers(footer),
    )


# --- billing (subjects carry "[TEST]" for simulated payments) ------------------------------


def _billing_subject(subject: str, is_test: bool) -> str:
    return _clean_subject(f"[TEST] {subject}" if is_test else subject)


def _test_note(is_test: bool) -> list[str]:
    return ["TEST MODE: this payment was simulated. No money was charged."] if is_test else []


def billing_receipt(
    plan: str, amount: str, description: str, period_end: str, link: str, is_test: bool
) -> RenderedEmail:
    title = "Payment received — thank you"
    paras = [*_test_note(is_test), f"We received your payment for the {plan} plan."]
    details = [
        ("Plan", plan),
        ("Amount", amount),
        ("For", description),
        ("Next renewal", period_end),
    ]
    return RenderedEmail(
        _billing_subject(f"Uptivora receipt: {amount}", is_test),
        _text(title, paras, link, details=details),
        _html(title, paras, ("View billing", link), tone="up", details=details),
    )


def billing_payment_failed(
    plan: str, amount: str, grace_until: str, link: str, is_test: bool
) -> RenderedEmail:
    title = "Your payment did not go through"
    paras = [
        *_test_note(is_test),
        f"We could not charge {amount} for your {plan} plan. Monitoring continues until "
        f"{grace_until}; we will retry automatically every day.",
        "You can also retry now from your billing page.",
    ]
    return RenderedEmail(
        _billing_subject("Action needed: payment failed", is_test),
        _text(title, paras, link),
        _html(title, paras, ("Retry payment", link), tone="warn"),
    )


def billing_subscription_ended(plan: str, link: str, is_test: bool) -> RenderedEmail:
    title = "Your subscription has ended"
    paras = [
        *_test_note(is_test),
        f"Your {plan} plan has ended and your monitors are paused. Your data and history "
        "are kept — choose a plan any time to resume monitoring.",
    ]
    return RenderedEmail(
        _billing_subject("Your Uptivora subscription has ended", is_test),
        _text(title, paras, link),
        _html(title, paras, ("Choose a plan", link), tone="down"),
    )


def licence_ready(product: str, link: str, is_test: bool) -> RenderedEmail:
    title = "Your self-hosted licence is ready"
    paras = [
        *_test_note(is_test),
        f"Your {product} licence file is ready to download from your account.",
        "Copy it into your installation or upload it in your admin dashboard. The licence "
        "never expires and is verified offline.",
    ]
    return RenderedEmail(
        _billing_subject("Your Uptivora licence is ready", is_test),
        _text(title, paras, link),
        _html(title, paras, ("Download licence", link), tone="up"),
    )


def invitation(inviter: str, url: str) -> RenderedEmail:
    title = "You have been invited to Uptivora"
    paras = [
        f"{inviter} invited you to their Uptivora installation, where your team monitors its "
        "websites.",
        "Choose a password to activate your account. The link is valid for 7 days.",
    ]
    return RenderedEmail(
        _clean_subject(f"{inviter} invited you to Uptivora"),
        _text(title, paras, url),
        _html(title, paras, ("Accept invitation", url)),
    )
