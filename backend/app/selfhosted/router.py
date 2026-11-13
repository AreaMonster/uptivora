"""Self-hosted administration: licence installation, invitations, setup checklist."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.auth.deps import DB, AppSettings, CurrentAdmin, require_admin
from app.core.audit import audit
from app.core.errors import AppError, Conflict, NotFound
from app.core.requestctx import client_ip
from app.enforcement import enforce_instance
from app.licensing import LicenseError
from app.limits import instance_limits
from app.models import (
    InstalledLicense,
    Monitor,
    NotificationOutbox,
    OutboxStatus,
    PausedReason,
    User,
    UserRole,
    WorkerHeartbeat,
)
from app.selfhosted import invites
from app.selfhosted.licence import deactivate_licence, install_licence, licence_status

router = APIRouter(
    prefix="/api/admin", tags=["admin-selfhosted"], dependencies=[Depends(require_admin)]
)


def _selfhosted(settings) -> None:
    if settings.is_hosted:
        raise NotFound("Only available in the self-hosted edition.")


async def _count(db, model, *where) -> int:
    return int(await db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


# --- licence ----------------------------------------------------------------------------------


@router.get("/licence")
async def get_licence(db: DB, settings: AppSettings) -> dict:
    _selfhosted(settings)
    status = await licence_status(db, settings)
    limits = await instance_limits(db, settings)
    lic = status.licence
    history = (
        await db.scalars(
            select(InstalledLicense).order_by(InstalledLicense.installed_at.desc()).limit(10)
        )
    ).all()
    return {
        "installed": lic is not None,
        "source": status.source,
        "error": status.error,
        "file_path_configured": settings.license_path is not None,
        "licence": None
        if lic is None
        else {
            "license_id": lic.license_id,
            "edition": lic.edition.value,
            "licensee_name": lic.licensee_name,
            "licensee_email": lic.licensee_email,
            "issued_at": lic.issued_at.isoformat(),
            "key_id": lic.key_id,
            "updates": lic.updates,
            "limits": lic.limits.to_dict(),
            "development_key": lic.key_id == "dev",
        },
        "limits": limits.to_dict(),
        "usage": {
            "active_monitors": await _count(db, Monitor, Monitor.is_paused.is_(False)),
            "limit_paused_monitors": await _count(
                db, Monitor, Monitor.paused_reason == PausedReason.PLAN_LIMIT
            ),
            "users": await _count(db, User),
        },
        "history": [
            {
                "license_id": str(h.license_id),
                "edition": h.edition,
                "licensee_name": h.licensee_name,
                "is_active": h.is_active,
                "installed_at": h.installed_at.isoformat(),
            }
            for h in history
        ],
    }


class LicenceIn(BaseModel):
    licence_text: str = Field(min_length=50, max_length=32_768)


@router.post("/licence")
async def put_licence(
    body: LicenceIn, ctx: CurrentAdmin, request: Request, db: DB, settings: AppSettings
) -> dict:
    _selfhosted(settings)
    try:
        lic = await install_licence(db, settings, body.licence_text, installed_by=ctx.user.id)
    except LicenseError as exc:
        raise AppError(
            f"Licence rejected: {exc.message}",
            code="invalid_licence",
            status_code=422,
            fields={"licence_text": exc.message},
        ) from exc
    changes = await enforce_instance(db, settings)
    audit(
        db,
        "admin.licence_install",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="licence",
        target_id=lic.license_id,
        edition=lic.edition.value,
        **changes,
    )
    await db.commit()
    file_active = bool(settings.license_path and settings.license_path.is_file())
    return {
        "status": "installed",
        "license_id": lic.license_id,
        "edition": lic.edition.value,
        "file_overrides": file_active,
        **changes,
    }


@router.delete("/licence")
async def remove_licence(
    ctx: CurrentAdmin, request: Request, db: DB, settings: AppSettings
) -> dict:
    """Back to evaluation mode. Monitors over the evaluation limit are paused, never deleted."""
    _selfhosted(settings)
    if not await deactivate_licence(db):
        raise Conflict("No licence was installed through the dashboard.", code="no_licence")
    changes = await enforce_instance(db, settings)
    audit(db, "admin.licence_remove", actor_id=ctx.user.id, ip=client_ip(request), **changes)
    await db.commit()
    return {"status": "removed", **changes}


@router.get("/setup")
async def setup_checklist(db: DB, settings: AppSettings) -> dict:
    _selfhosted(settings)
    status = await licence_status(db, settings)
    heartbeat = await db.scalar(select(func.max(WorkerHeartbeat.last_seen_at)))
    worker_ok = bool(heartbeat and (datetime.now(UTC) - heartbeat).total_seconds() < 60)
    emails_sent = await _count(
        db, NotificationOutbox, NotificationOutbox.status == OutboxStatus.SENT
    )
    return {
        "steps": [
            {"key": "admin", "label": "Create the administrator account", "done": True},
            {"key": "worker", "label": "Start the monitoring worker", "done": worker_ok},
            {
                "key": "smtp",
                "label": "Configure SMTP and confirm your email",
                "done": bool(settings.smtp_host) and emails_sent > 0,
            },
            {
                "key": "licence",
                "label": "Install your licence (evaluation works without)",
                "done": status.licence is not None,
            },
            {
                "key": "monitor",
                "label": "Add your first monitor",
                "done": await _count(db, Monitor) > 0,
            },
            {
                "key": "team",
                "label": "Invite your team (optional)",
                "done": await _count(db, User) > 1,
            },
        ]
    }


# --- invitations ------------------------------------------------------------------------------


class InviteIn(BaseModel):
    email: EmailStr
    role: str = Field(default="user", pattern="^(user|admin)$")


@router.get("/invitations")
async def list_invitations(db: DB, settings: AppSettings) -> list[dict]:
    _selfhosted(settings)
    rows = (
        await db.scalars(
            select(User)
            .where(User.password_hash.startswith(invites.PENDING))
            .order_by(User.created_at.desc())
        )
    ).all()
    return [
        {"id": str(u.id), "email": u.email, "role": u.role, "invited_at": u.created_at.isoformat()}
        for u in rows
    ]


@router.post("/invitations", status_code=201)
async def create_invitation(
    body: InviteIn, ctx: CurrentAdmin, request: Request, db: DB, settings: AppSettings
) -> dict:
    _selfhosted(settings)
    user = await invites.invite(db, settings, ctx.user, str(body.email), UserRole(body.role))
    audit(
        db,
        "admin.invite",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="user",
        target_id=user.id,
        role=body.role,
    )
    await db.commit()
    return {"id": str(user.id), "email": user.email, "role": user.role}


@router.post("/invitations/{user_id}/resend", status_code=202)
async def resend_invitation(
    user_id: uuid.UUID, ctx: CurrentAdmin, db: DB, settings: AppSettings
) -> dict:
    _selfhosted(settings)
    user = await invites.pending_user(db, user_id)
    await invites.send_invite(db, settings, ctx.user, user)
    await db.commit()
    return {"status": "sent"}


@router.delete("/invitations/{user_id}", status_code=204)
async def revoke_invitation(
    user_id: uuid.UUID, ctx: CurrentAdmin, request: Request, db: DB, settings: AppSettings
) -> Response:
    _selfhosted(settings)
    user = await invites.pending_user(db, user_id)
    audit(
        db,
        "admin.invite_revoke",
        actor_id=ctx.user.id,
        ip=client_ip(request),
        target_type="user",
        target_id=user.id,
    )
    await db.delete(user)
    await db.commit()
    return Response(status_code=204)
