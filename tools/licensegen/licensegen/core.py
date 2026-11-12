"""Licence signing. OFFLINE ONLY — this package is never shipped in application images."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Share the format definition with the application so they can never drift apart.
_BACKEND = Path(__file__).resolve().parents[3] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.licensing.format import (  # noqa: E402
    EDITION_DEFAULT_LIMITS,
    FORMAT_VERSION,
    PRODUCT,
    Edition,
    LicenseLimits,
    armor,
    b64url_encode,
    signing_message,
)


def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return b64url_encode(raw)


def generate_keypair() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def private_key_to_pem(private_key: Ed25519PrivateKey, passphrase: bytes | None) -> bytes:
    encryption = (
        serialization.BestAvailableEncryption(passphrase)
        if passphrase
        else serialization.NoEncryption()
    )
    return private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption
    )


def load_private_key(pem: bytes, passphrase: bytes | None) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem, password=passphrase)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Not an Ed25519 private key")
    return key


def build_payload(
    *,
    key_id: str,
    edition: Edition,
    licensee_name: str,
    licensee_email: str,
    limits: LicenseLimits | None = None,
    license_id: str | None = None,
    issued_at: datetime | None = None,
    notes: str = "",
) -> dict:
    limits = limits or EDITION_DEFAULT_LIMITS[edition]
    return {
        "format": FORMAT_VERSION,
        "key_id": key_id,
        "license_id": license_id or str(uuid.uuid4()),
        "product": PRODUCT,
        "edition": edition.value,
        "licensee": {"name": licensee_name.strip(), "email": licensee_email.strip()},
        "issued_at": (issued_at or datetime.now(UTC)).replace(microsecond=0).isoformat(),
        "expires_at": None,
        "updates": "lifetime",
        "limits": limits.to_dict(),
        "notes": notes,
    }


def sign_payload(private_key: Ed25519PrivateKey, payload: dict) -> str:
    payload_bytes = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    signature = private_key.sign(signing_message(payload_bytes))
    return armor(payload_bytes, signature)
