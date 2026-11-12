from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def audit(
    db: AsyncSession,
    action: str,
    *,
    actor_id: uuid.UUID | None,
    ip: str | None = None,
    target_type: str | None = None,
    target_id: object | None = None,
    **details: Any,
) -> None:
    """Add an audit entry to the current transaction (committed with the action itself)."""
    db.add(
        AuditLog(
            actor_user_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            ip_address=ip,
            details=details,
        )
    )
