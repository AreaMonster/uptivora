"""Self-hosted licence state. Verified locally on every load; results cached by content hash."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.licensing import License, LicenseError, trusted_keys, verify_license
from app.models import InstalledLicense

log = logging.getLogger("uptivora.licence")

_cache: dict[str, License | LicenseError] = {}


@dataclass(frozen=True, slots=True)
class LicenceStatus:
    licence: License | None
    source: str | None  # "file" | "database" | None
    error: str | None = None


def verify_cached(raw: str, settings: Settings) -> License:
    digest = hashlib.sha256(f"{settings.env}\0{raw}".encode()).hexdigest()
    hit = _cache.get(digest)
    if hit is None:
        try:
            hit = verify_license(raw, trusted_keys(settings.env, settings.dev_key_dir))
        except LicenseError as exc:
            hit = exc
        _cache[digest] = hit
    if isinstance(hit, LicenseError):
        raise hit
    return hit


async def licence_status(db: AsyncSession, settings: Settings) -> LicenceStatus:
    raw: str | None = None
    source: str | None = None
    if settings.license_path and settings.license_path.is_file():
        raw, source = settings.license_path.read_text(encoding="utf-8", errors="replace"), "file"
    else:
        raw = await db.scalar(
            select(InstalledLicense.raw_text).where(InstalledLicense.is_active.is_(True))
        )
        source = "database" if raw else None
    if not raw:
        return LicenceStatus(None, None)
    try:
        return LicenceStatus(verify_cached(raw, settings), source)
    except LicenseError as exc:
        log.warning("Installed licence rejected (%s): %s", exc.code, exc.message)
        return LicenceStatus(None, source, exc.message)
