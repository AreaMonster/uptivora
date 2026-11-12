"""Development-only admin tools: create test accounts and DEV-signed test licences.

Safety:
* The router is only mounted when ``UPTIVORA_ENV`` is ``development`` or ``test`` — and every
  endpoint re-checks it, so a mis-wired include cannot expose it in production.
* Development mode itself refuses to start on a non-local ``UPTIVORA_PUBLIC_URL``.
* Licences are signed with the local **dev** key (``backend/.dev-keys``), which production
  never trusts. The production signing key is never on a server, so it cannot be used here.
* Neither key material nor key paths are ever returned to the browser.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.auth.deps import DB, AppSettings, CurrentAdmin, require_admin
from app.auth.service import create_user, get_user_by_email
from app.core.audit import audit
from app.core.errors import AppError, Conflict, NotFound
from app.core.requestctx import client_ip
from app.core.security import generate_token
from app.licensing import EDITION_DEFAULT_LIMITS, Edition, LicenseLimits
from app.licensing.format import FORMAT_VERSION, PRODUCT, armor, signing_message
from app.licensing.keys import DEV_KEY_ID
from app.models import Plan, Subscription, SubscriptionStatus, UserRole

DEV_ENVIRONMENTS = ("development", "test")
DEV_PRIVATE_KEY_FILE = "dev-private.pem"

router = APIRouter(
    prefix="/api/admin/dev", tags=["admin-dev"], dependencies=[Depends(require_admin)]
)


def ensure_dev(settings) -> None:
    if settings.env not in DEV_ENVIRONMENTS:
        raise NotFound("Not found.")


@router.get("/status")
async def dev_status(settings: AppSettings) -> dict:
    ensure_dev(settings)
    return {
        "environment": settings.env,
        "dev_key_available": (settings.dev_key_dir / DEV_PRIVATE_KEY_FILE).is_file(),
    }


class TestAccountIn(BaseModel):
    email: EmailStr | None = None
    full_name: str = Field(default="Test Customer", max_length=120)
    plan_code: str | None = Field(default=None, max_length=32)
    admin: bool = False
    verified: bool = True


@router.post("/test-account", status_code=201)
async def create_test_account(
    body: TestAccountIn, ctx: CurrentAdmin, request: Request, db: DB, settings: AppSettings
) -> dict:
    ensure_dev(settings)
    email = str(body.email) if body.email else f"test-{uuid.uuid4().hex[:8]}@example.com"
    if await get_user_by_email(db, email):
        raise Conflict("A user with this email already exists.", fields={"email": "Already used"})
    password = generate_token(12)  # shown once to the developer, never stored in clear text
    user = await create_user(
        db,
        email=email,
        password=password,
        full_name=body.full_name,
        role=UserRole.ADMIN if body.admin else UserRole.USER,
    )
    if body.verified:
        user.email_verified_at = datetime.now(UTC)
    plan_name = None
    if body.plan_code:
        if not settings.is_hosted:
            raise AppError("Plans exist only in the hosted edition.", status_code=422)
        plan = await db.scalar(select(Plan).where(Plan.code == body.plan_code))
        if plan is None:
            raise AppError("Unknown plan.", status_code=422, fields={"plan_code": "Unknown plan"})
        now = datetime.now(UTC)
        db.add(
            Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                provider="test",
                is_test=True,
            )
        )
        plan_name = plan.name
    audit(
        db,
        "admin.dev_test_account",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="user",
        target_id=user.id,
        plan=body.plan_code,
    )
    await db.commit()
    return {
        "id": str(user.id),
        "email": email,
        "password": password,
        "plan": plan_name,
        "role": user.role,
        "note": "Development only. The password is shown once.",
    }


class TestLicenceIn(BaseModel):
    edition: Edition = Edition.STARTER
    licensee_name: str = Field(default="Test Licensee", min_length=1, max_length=200)
    licensee_email: EmailStr = "licensee@example.com"
    max_monitors: int | None = Field(default=None, ge=0, le=1_000_000)
    max_users: int | None = Field(default=None, ge=0, le=100_000)
    min_interval_seconds: int | None = Field(default=None, ge=30, le=86_400)


def _load_dev_key(settings) -> Ed25519PrivateKey:
    path = settings.dev_key_dir / DEV_PRIVATE_KEY_FILE
    if not path.is_file():
        raise AppError(
            "No development signing key found. Run "
            "`python -m licensegen keygen --dev` in tools/licensegen first.",
            code="no_dev_key",
            status_code=409,
        )
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise AppError("The development key is not an Ed25519 key.", status_code=500)
    return key


@router.post("/test-licence")
async def create_test_licence(
    body: TestLicenceIn, ctx: CurrentAdmin, request: Request, db: DB, settings: AppSettings
) -> dict:
    ensure_dev(settings)
    key = _load_dev_key(settings)
    defaults = EDITION_DEFAULT_LIMITS[body.edition]
    limits = LicenseLimits(
        max_monitors=defaults.max_monitors if body.max_monitors is None else body.max_monitors,
        max_users=defaults.max_users if body.max_users is None else body.max_users,
        min_interval_seconds=body.min_interval_seconds or defaults.min_interval_seconds,
    )
    payload = {
        "format": FORMAT_VERSION,
        "key_id": DEV_KEY_ID,
        "license_id": str(uuid.uuid4()),
        "product": PRODUCT,
        "edition": body.edition.value,
        "licensee": {"name": body.licensee_name.strip(), "email": str(body.licensee_email)},
        "issued_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "expires_at": None,
        "updates": "lifetime",
        "limits": limits.to_dict(),
        "notes": "DEVELOPMENT TEST LICENCE - not valid in production",
    }
    payload_bytes = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    text = armor(payload_bytes, key.sign(signing_message(payload_bytes)))
    audit(
        db,
        "admin.dev_test_licence",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="licence",
        target_id=payload["license_id"],
        edition=body.edition.value,
    )
    await db.commit()
    return {
        "license_id": payload["license_id"],
        "edition": body.edition.value,
        "limits": limits.to_dict(),
        "licence_text": text,
        "filename": f"test-{body.edition.value}.uptivora-license",
        "note": "Signed with the local DEV key: only accepted in development/test.",
    }
