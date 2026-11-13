"""Client for the isolated licence signer (``app.signer``) on the internal Docker network.

Operator-configured (``UPTIVORA_SIGNER_URL``) and hosted-only: self-hosted installations never
set it, so this module makes no requests there.
"""

from __future__ import annotations

import json

import httpx

from app.core.config import Settings
from app.licensing.format import dearmor
from app.models import LicenseOrder, LicenseProduct

# Tests replace this with an in-process transport to the signer app.
transport: httpx.AsyncBaseTransport | None = None


class SignerError(Exception):
    pass


def licence_key_id(licence_text: str) -> str | None:
    """The key id a stored licence was signed with (no signature check needed here)."""
    try:
        payload, _ = dearmor(licence_text)
        return json.loads(payload).get("key_id")
    except Exception:  # noqa: BLE001 — malformed text simply has no key id
        return None


async def health(settings: Settings) -> str:
    """'ok', 'no_key', 'not configured' or an error description."""
    if not settings.signer_url:
        return "not configured"
    try:
        async with httpx.AsyncClient(
            base_url=settings.signer_url, timeout=5, trust_env=False, transport=transport
        ) as client:
            resp = await client.get("/health")
        return str(resp.json().get("status", f"HTTP {resp.status_code}"))
    except (httpx.HTTPError, ValueError) as exc:
        return f"unreachable ({type(exc).__name__})"


async def request_licence(
    settings: Settings, order: LicenseOrder, product: LicenseProduct, *, reissue: bool = False
) -> str:
    if not settings.signer_url:
        raise SignerError("No signing service configured (UPTIVORA_SIGNER_URL)")
    limits = product.limits or {}
    body = {
        "order_id": str(order.id),
        "edition": product.edition,
        "licensee_name": order.licensee_name,
        "licensee_email": order.licensee_email,
        "limits": {
            "max_monitors": int(limits.get("max_monitors", 0)),
            "max_users": int(limits.get("max_users", 0)),
            "min_interval_seconds": int(limits.get("min_interval_seconds", 60)),
        },
        "reissue": reissue,
    }
    try:
        async with httpx.AsyncClient(
            base_url=settings.signer_url,
            timeout=15,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        ) as client:
            resp = await client.post(
                "/sign",
                json=body,
                headers={"Authorization": f"Bearer {settings.signer_token.get_secret_value()}"},
            )
    except httpx.HTTPError as exc:
        raise SignerError(f"Signer unreachable: {type(exc).__name__}") from exc
    if resp.status_code != 200:
        detail = (
            resp.json().get("detail", "")
            if resp.headers.get("content-type", "").startswith("application/json")
            else ""
        )
        raise SignerError(f"Signer answered HTTP {resp.status_code} {detail}".strip())
    return resp.json()["licence"]
