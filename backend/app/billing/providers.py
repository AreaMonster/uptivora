"""Payment providers.

Uptivora talks to payments only through :class:`PaymentProvider`. Two implementations exist:

* :class:`TestModeProvider` — the TEST MODE simulator. No network calls, no money moves.
  Every result is flagged ``is_test`` and stored as such, and the UI labels it everywhere.
* :class:`StripeProvider` — skeleton for a future real integration. It is **disabled**: the
  configuration refuses ``UPTIVORA_BILLING_PROVIDER=stripe`` until it is implemented and a
  compliant merchant account exists. Webhook signature verification is implemented already.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from typing import Literal, Protocol

Simulation = Literal["success", "decline"]


@dataclass(frozen=True, slots=True)
class ChargeResult:
    ok: bool
    provider_payment_id: str
    error: str | None = None


class PaymentProvider(Protocol):
    name: str
    is_test: bool

    async def charge(
        self,
        *,
        amount_cents: int,
        currency: str,
        description: str,
        customer_ref: str,
        simulate: Simulation = "success",
    ) -> ChargeResult: ...


class TestModeProvider:
    """Simulated card payments. ``simulate`` decides the outcome; nothing leaves the server."""

    name = "test"
    is_test = True

    async def charge(
        self,
        *,
        amount_cents: int,
        currency: str,
        description: str,
        customer_ref: str,
        simulate: Simulation = "success",
    ) -> ChargeResult:
        ref = f"test_{uuid.uuid4().hex[:24]}"
        if simulate == "decline":
            return ChargeResult(False, ref, "Your card was declined (TEST MODE simulation).")
        return ChargeResult(True, ref)


class ManualProvider:
    """Plans assigned by an administrator (complimentary / invoiced offline). Never charges."""

    name = "manual"
    is_test = False

    async def charge(self, **_kwargs) -> ChargeResult:  # pragma: no cover - never called
        raise RuntimeError("Manual subscriptions are not charged")


class StripeProvider:  # pragma: no cover - intentionally disabled
    name = "stripe"
    is_test = False

    async def charge(self, **_kwargs) -> ChargeResult:
        raise NotImplementedError(
            "Real payments are disabled until a payment-provider account is set up."
        )


def get_provider(billing_provider: str) -> PaymentProvider:
    if billing_provider == "test":
        return TestModeProvider()
    raise LookupError(f"Billing provider {billing_provider!r} is not available")


# --- Stripe webhook verification (ready for the real integration) ---------------------------

WEBHOOK_TOLERANCE_SECONDS = 300


class WebhookSignatureError(ValueError):
    pass


def verify_stripe_signature(
    payload: bytes,
    signature_header: str,
    secret: str,
    *,
    tolerance: int = WEBHOOK_TOLERANCE_SECONDS,
    now: float | None = None,
) -> int:
    """Verify a ``Stripe-Signature`` header (``t=<ts>,v1=<hex hmac>[,v1=...]``).

    The signed message is ``f"{t}.{payload}"`` with HMAC-SHA256 and the endpoint secret.
    Rejects stale timestamps (replay protection). Returns the timestamp.
    """
    if not secret:
        raise WebhookSignatureError("Webhook secret is not configured")
    parts: dict[str, list[str]] = {}
    for item in (signature_header or "").split(","):
        key, _, value = item.strip().partition("=")
        if key and value:
            parts.setdefault(key, []).append(value)
    try:
        timestamp = int(parts["t"][0])
    except (KeyError, ValueError) as exc:
        raise WebhookSignatureError("Missing or invalid timestamp") from exc
    signatures = parts.get("v1", [])
    if not signatures:
        raise WebhookSignatureError("No v1 signature")
    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance:
        raise WebhookSignatureError("Timestamp outside the tolerance window")
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise WebhookSignatureError("Signature mismatch")
    return timestamp
