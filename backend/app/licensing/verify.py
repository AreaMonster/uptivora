"""Offline licence verification. No network access, ever."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.licensing.format import (
    FORMAT_VERSION,
    PRODUCT,
    Edition,
    License,
    LicenseLimits,
    dearmor,
    signing_message,
)


class LicenseError(Exception):
    """Licence rejected. ``code`` is stable and safe to show to users."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key {key!r}")
        obj[key] = value
    return obj


def _int_field(obj: Mapping[str, object], key: str, *, minimum: int = 0) -> int:
    value = obj.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum or value > 10**9:
        raise LicenseError("invalid_payload", f"limits.{key} must be an integer >= {minimum}")
    return value


def _str_field(obj: Mapping[str, object], key: str, *, max_len: int = 200) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or len(value) > max_len:
        raise LicenseError("invalid_payload", f"{key} must be a string")
    return value


def verify_license(text: str, trusted: Mapping[str, Ed25519PublicKey]) -> License:
    """Verify an armoured licence and return its contents, or raise :class:`LicenseError`."""
    try:
        payload_bytes, signature = dearmor(text)
    except ValueError as exc:
        raise LicenseError("malformed", f"Licence file is malformed: {exc}") from exc

    # Parse just enough to find the key id; nothing is trusted until the signature verifies.
    try:
        payload = json.loads(
            payload_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise LicenseError("malformed", "Licence payload is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise LicenseError("malformed", "Licence payload must be a JSON object")

    key_id = payload.get("key_id")
    if not isinstance(key_id, str) or key_id not in trusted:
        raise LicenseError("unknown_key", "Licence was not signed by a trusted Uptivora key")
    try:
        trusted[key_id].verify(signature, signing_message(payload_bytes))
    except InvalidSignature as exc:
        raise LicenseError(
            "bad_signature", "Licence signature is invalid (file modified?)"
        ) from exc

    # --- signature valid: validate semantics -------------------------------------------
    if payload.get("format") != FORMAT_VERSION:
        raise LicenseError("unsupported_format", "Unsupported licence format version")
    if payload.get("product") != PRODUCT:
        raise LicenseError("wrong_product", "This licence is for a different product")
    if payload.get("expires_at") is not None:
        raise LicenseError("invalid_payload", "Expiring licences are not supported")

    try:
        edition = Edition(payload.get("edition"))
    except ValueError as exc:
        raise LicenseError("invalid_payload", "Unknown licence edition") from exc

    license_id = _str_field(payload, "license_id", max_len=36)
    try:
        license_id = str(uuid.UUID(license_id))
    except ValueError as exc:
        raise LicenseError("invalid_payload", "license_id must be a UUID") from exc

    licensee = payload.get("licensee")
    if not isinstance(licensee, dict):
        raise LicenseError("invalid_payload", "licensee must be an object")
    name = _str_field(licensee, "name").strip()
    if not name:
        raise LicenseError("invalid_payload", "licensee.name must not be empty")
    email = _str_field(licensee, "email", max_len=254)

    try:
        issued_at = datetime.fromisoformat(_str_field(payload, "issued_at", max_len=40))
    except ValueError as exc:
        raise LicenseError("invalid_payload", "issued_at must be an ISO-8601 timestamp") from exc
    if issued_at.tzinfo is None:
        raise LicenseError("invalid_payload", "issued_at must include a timezone")

    limits_obj = payload.get("limits")
    if not isinstance(limits_obj, dict):
        raise LicenseError("invalid_payload", "limits must be an object")
    limits = LicenseLimits(
        max_monitors=_int_field(limits_obj, "max_monitors"),
        max_users=_int_field(limits_obj, "max_users"),
        min_interval_seconds=_int_field(limits_obj, "min_interval_seconds", minimum=30),
    )

    return License(
        license_id=license_id,
        key_id=key_id,
        edition=edition,
        licensee_name=name,
        licensee_email=email,
        issued_at=issued_at,
        limits=limits,
        updates=_str_field(payload, "updates", max_len=32),
        notes=str(payload.get("notes") or "")[:500],
        payload=payload,
    )
