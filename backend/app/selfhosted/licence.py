"""Self-hosted licence state. Verified locally on every load; results cached by content hash."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
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


# --- installation through the admin dashboard ------------------------------------------------


async def install_licence(
    db: AsyncSession, settings: Settings, raw: str, *, installed_by: uuid.UUID | None = None
) -> License:
    """Verify and activate a licence. Earlier licences stay as inactive history.

    Raises :class:`LicenseError` for invalid files (nothing is changed then).
    """
    text = raw.strip() + "\n"
    lic = verify_cached(text, settings)
    await db.execute(
        update(InstalledLicense).where(InstalledLicense.is_active.is_(True)).values(is_active=False)
    )
    await db.flush()
    existing = await db.scalar(
        select(InstalledLicense).where(InstalledLicense.license_id == uuid.UUID(lic.license_id))
    )
    if existing is not None:  # re-installing the same licence re-activates it
        existing.is_active = True
        existing.raw_text = text
    else:
        db.add(
            InstalledLicense(
                license_id=uuid.UUID(lic.license_id),
                edition=lic.edition.value,
                licensee_name=lic.licensee_name,
                raw_text=text,
                installed_by=installed_by,
            )
        )
    await db.flush()
    return lic


async def deactivate_licence(db: AsyncSession) -> int:
    """Go back to evaluation mode (the licence stays in the history)."""
    result = await db.execute(
        update(InstalledLicense).where(InstalledLicense.is_active.is_(True)).values(is_active=False)
    )
    await db.flush()
    return result.rowcount or 0
