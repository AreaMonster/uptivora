"""Uptivora licence file format (v1). Spec: docs/EDITIONS_AND_LICENSING.md §3.

This module contains only encoding/decoding and data types. It has no knowledge of private
keys; signing lives in the offline ``tools/licensegen`` utility.
"""

from __future__ import annotations

import base64
import binascii
import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

ARMOR_BEGIN = "-----BEGIN UPTIVORA LICENSE-----"
ARMOR_END = "-----END UPTIVORA LICENSE-----"
SIGNING_PREFIX = b"uptivora-license-v1\x00"
PRODUCT = "uptivora-selfhosted"
FORMAT_VERSION = 1
MAX_LICENSE_TEXT = 32 * 1024
MAX_PAYLOAD_BYTES = 8 * 1024
SIGNATURE_BYTES = 64
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class Edition(StrEnum):
    STARTER = "starter"
    PROFESSIONAL = "professional"


@dataclass(frozen=True, slots=True)
class LicenseLimits:
    """0 means unlimited for ``max_monitors`` and ``max_users``."""

    max_monitors: int
    max_users: int
    min_interval_seconds: int

    def to_dict(self) -> dict[str, int]:
        return {
            "max_monitors": self.max_monitors,
            "max_users": self.max_users,
            "min_interval_seconds": self.min_interval_seconds,
        }


EDITION_DEFAULT_LIMITS: dict[Edition, LicenseLimits] = {
    Edition.STARTER: LicenseLimits(max_monitors=25, max_users=3, min_interval_seconds=60),
    Edition.PROFESSIONAL: LicenseLimits(max_monitors=0, max_users=0, min_interval_seconds=30),
}
# Limits applied when no valid licence is installed (evaluation mode).
UNLICENSED_LIMITS = LicenseLimits(max_monitors=3, max_users=1, min_interval_seconds=300)


@dataclass(frozen=True, slots=True)
class License:
    license_id: str
    key_id: str
    edition: Edition
    licensee_name: str
    licensee_email: str
    issued_at: datetime
    limits: LicenseLimits
    updates: str
    notes: str = ""
    payload: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode_strict(value: str) -> bytes:
    """Decode unpadded base64url, rejecting non-canonical encodings (malleability)."""
    if not _B64URL_RE.match(value) or len(value) % 4 == 1:
        raise ValueError("invalid base64url")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64url") from exc
    if b64url_encode(decoded) != value:
        raise ValueError("non-canonical base64url")
    return decoded


def signing_message(payload_bytes: bytes) -> bytes:
    return SIGNING_PREFIX + payload_bytes


def armor(payload_bytes: bytes, signature: bytes) -> str:
    body = b64url_encode(payload_bytes) + "." + b64url_encode(signature)
    lines = textwrap.wrap(body, 64, break_on_hyphens=False)
    return "\n".join([ARMOR_BEGIN, *lines, ARMOR_END]) + "\n"


def dearmor(text: str) -> tuple[bytes, bytes]:
    """Return ``(payload_bytes, signature)`` from an armoured licence. Raises ValueError."""
    if len(text) > MAX_LICENSE_TEXT:
        raise ValueError("licence file is too large")
    text = text.replace("\r\n", "\n").strip().lstrip("﻿")
    if text.count(ARMOR_BEGIN) != 1 or text.count(ARMOR_END) != 1:
        raise ValueError("licence armour missing or duplicated")
    if not (text.startswith(ARMOR_BEGIN) and text.endswith(ARMOR_END)):
        raise ValueError("unexpected content outside the licence armour")
    body = "".join(text[len(ARMOR_BEGIN) : -len(ARMOR_END)].split())
    parts = body.split(".")
    if len(parts) != 2:
        raise ValueError("licence body must be '<payload>.<signature>'")
    payload_bytes = b64url_decode_strict(parts[0])
    signature = b64url_decode_strict(parts[1])
    if not payload_bytes or len(payload_bytes) > MAX_PAYLOAD_BYTES:
        raise ValueError("licence payload has an invalid size")
    if len(signature) != SIGNATURE_BYTES:
        raise ValueError("licence signature has an invalid size")
    return payload_bytes, signature
