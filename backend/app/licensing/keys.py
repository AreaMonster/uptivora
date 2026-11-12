"""Trusted Ed25519 PUBLIC keys for licence verification.

Only public keys belong here. Private keys are generated and kept offline with
``tools/licensegen`` and must never be committed, copied into an image or stored in the database.

Key rotation: add a new entry; never remove an old one (licences signed with it are perpetual).
Only remove a key if it is known to be compromised (see docs/LICENSE_KEY_OPERATIONS.md).
"""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.licensing.format import b64url_decode_strict

# key_id -> base64url raw 32-byte Ed25519 public key.
# Populate with `python -m licensegen keygen --key-id <id>` output before the first release.
PRODUCTION_PUBLIC_KEYS: dict[str, str] = {}

DEV_KEY_ID = "dev"
DEV_PUBLIC_KEY_FILE = "dev-public.key"


def load_public_key(b64: str) -> Ed25519PublicKey:
    raw = b64url_decode_strict(b64.strip())
    if len(raw) != 32:
        raise ValueError("Ed25519 public keys are 32 bytes")
    return Ed25519PublicKey.from_public_bytes(raw)


def trusted_keys(env: str, dev_key_dir: Path | None = None) -> dict[str, Ed25519PublicKey]:
    """Keys trusted in ``env``. The dev key is trusted ONLY in development/test."""
    keys = {kid: load_public_key(b64) for kid, b64 in PRODUCTION_PUBLIC_KEYS.items()}
    if DEV_KEY_ID in keys:
        raise RuntimeError("The 'dev' key id is reserved and must not be a production key")
    if env in ("development", "test") and dev_key_dir is not None:
        dev_file = dev_key_dir / DEV_PUBLIC_KEY_FILE
        if dev_file.is_file():
            keys[DEV_KEY_ID] = load_public_key(dev_file.read_text(encoding="ascii"))
    return keys
