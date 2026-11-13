"""HTTP API of the signing service. See the package docstring for the security model."""

from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.core.config import Settings
from app.licensing.format import Edition, LicenseLimits
from app.licensing.keys import DEV_KEY_ID, PRODUCTION_PUBLIC_KEYS
from app.licensing.signing import build_payload, load_private_key, public_key_b64, sign_payload

log = logging.getLogger("uptivora.signer")

JOURNAL = "signed.jsonl"


class Limits(BaseModel):
    max_monitors: int = Field(ge=0, le=1_000_000)
    max_users: int = Field(ge=0, le=1_000_000)
    min_interval_seconds: int = Field(ge=30, le=86400)


class SignRequest(BaseModel):
    order_id: uuid.UUID
    edition: Literal["starter", "professional"]
    licensee_name: str = Field(min_length=2, max_length=200)
    licensee_email: EmailStr
    limits: Limits
    reissue: bool = False


@dataclass
class Entry:
    order_id: str
    license_id: str
    signed_at: datetime
    key_id: str
    edition: str
    licensee_name: str
    licensee_email: str
    limits: dict
    licence: str


class Journal:
    """Append-only record of every licence signed; also the source for idempotency."""

    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / JOURNAL
        self._lock = threading.Lock()
        self.entries: list[Entry] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    raw = json.loads(line)
                    raw["signed_at"] = datetime.fromisoformat(raw["signed_at"])
                    self.entries.append(Entry(**raw))

    def latest_for(self, order_id: str) -> Entry | None:
        found = [e for e in self.entries if e.order_id == order_id]
        return found[-1] if found else None

    def signed_since(self, since: datetime) -> int:
        """New licences only; re-issues of known orders do not count against the limit."""
        firsts: dict[str, datetime] = {}
        for e in self.entries:
            firsts.setdefault(e.order_id, e.signed_at)
        return sum(1 for t in firsts.values() if t >= since)

    def append(self, entry: Entry) -> None:
        line = json.dumps({**entry.__dict__, "signed_at": entry.signed_at.isoformat()})
        with self._lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self.entries.append(entry)


def load_signing_key(settings: Settings) -> Ed25519PrivateKey:
    if not settings.signer_key_id:
        raise RuntimeError("UPTIVORA_SIGNER_KEY_ID is not set")
    key = load_private_key(settings.signer_key_path.read_bytes(), None)
    public = public_key_b64(key)
    trusted = PRODUCTION_PUBLIC_KEYS.get(settings.signer_key_id)
    if trusted != public:
        allowed_dev = (
            settings.env in ("development", "test") and settings.signer_key_id == DEV_KEY_ID
        )
        if not allowed_dev:
            # A licence signed with a key the installations do not trust would be useless.
            raise RuntimeError(
                f"The signing key does not match PRODUCTION_PUBLIC_KEYS[{settings.signer_key_id!r}]"
            )
    return key


def create_app(settings: Settings, key: Ed25519PrivateKey | None = None) -> FastAPI:
    key = key or load_signing_key(settings)
    journal = Journal(settings.signer_data_dir)
    token = settings.signer_token.get_secret_value()
    lock = threading.Lock()
    app = FastAPI(title="Uptivora licence signer", docs_url=None, redoc_url=None, openapi_url=None)

    def authorise(authorization: str | None) -> None:
        expected = f"Bearer {token}"
        if not token or not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="unauthorised")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "key_id": settings.signer_key_id}

    @app.post("/sign")
    def sign(body: SignRequest, authorization: str | None = Header(default=None)) -> dict:
        authorise(authorization)
        order_id = str(body.order_id)
        with lock:
            previous = journal.latest_for(order_id)
            if previous and not body.reissue:
                return {
                    "licence": previous.licence,
                    "license_id": previous.license_id,
                    "reused": True,
                }
            if body.reissue:
                if previous is None:
                    raise HTTPException(
                        status_code=404, detail="unknown order: nothing to re-issue"
                    )
                if previous.key_id == settings.signer_key_id and (
                    datetime.now(UTC) - previous.signed_at < timedelta(days=1)
                ):
                    return {
                        "licence": previous.licence,
                        "license_id": previous.license_id,
                        "reused": True,
                    }
                # Same licensee, edition and limits as before: no new entitlement.
                name, email = previous.licensee_name, previous.licensee_email
                edition, limits = previous.edition, previous.limits
            else:
                day_ago = datetime.now(UTC) - timedelta(days=1)
                if journal.signed_since(day_ago) >= settings.signer_daily_limit:
                    log.warning("Daily signing limit reached; refusing order %s", order_id)
                    raise HTTPException(status_code=429, detail="daily signing limit reached")
                name, email = body.licensee_name, str(body.licensee_email)
                edition, limits = body.edition, body.limits.model_dump()

            payload = build_payload(
                key_id=settings.signer_key_id,
                edition=Edition(edition),
                licensee_name=name,
                licensee_email=email,
                limits=LicenseLimits(**limits),
                notes=f"order {order_id}",
            )
            licence = sign_payload(key, payload)
            journal.append(
                Entry(
                    order_id=order_id,
                    license_id=payload["license_id"],
                    signed_at=datetime.now(UTC),
                    key_id=settings.signer_key_id,
                    edition=edition,
                    licensee_name=name,
                    licensee_email=email,
                    limits=limits,
                    licence=licence,
                )
            )
            log.info(
                "Signed licence %s for order %s (%s)",
                payload["license_id"],
                order_id,
                "re-issue" if body.reissue else "new",
            )
            return {"licence": licence, "license_id": payload["license_id"], "reused": False}

    return app
