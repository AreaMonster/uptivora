"""Unauthenticated, cacheable information for the public website."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.auth.deps import DB, AppSettings
from app.auth.service import count_users
from app.models import AppSetting, LicenseProduct, Plan

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/config")
async def public_config(db: DB, settings: AppSettings) -> dict:
    if settings.is_hosted:
        signup = True
    else:
        setting = await db.get(AppSetting, "public_signup")
        signup = await count_users(db) == 0 or bool(setting and setting.value is True)
    return {
        "edition": settings.edition,
        "version": settings.version,
        "billing_test_mode": settings.billing_test_mode,
        "billing_enabled": settings.billing_provider != "disabled",
        "signup_open": signup,
        "needs_setup": (not settings.is_hosted) and await count_users(db) == 0,
        "environment": settings.env,
    }


@router.get("/plans")
async def public_plans(db: DB, settings: AppSettings) -> dict:
    if not settings.is_hosted:
        return {"plans": [], "licences": []}
    plans = (
        await db.scalars(
            select(Plan)
            .where(Plan.is_active.is_(True), Plan.is_public.is_(True))
            .order_by(Plan.sort_order)
        )
    ).all()
    products = (
        await db.scalars(
            select(LicenseProduct)
            .where(LicenseProduct.is_active.is_(True))
            .order_by(LicenseProduct.sort_order)
        )
    ).all()
    return {
        "plans": [
            {
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "price_cents": p.price_cents,
                "currency": p.currency,
                "interval": p.interval,
                "max_monitors": p.max_monitors,
                "min_interval_seconds": p.min_interval_seconds,
                "features": p.features,
            }
            for p in plans
        ],
        "licences": [
            {
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "edition": p.edition,
                "price_cents": p.price_cents,
                "currency": p.currency,
                "limits": p.limits,
            }
            for p in products
        ],
    }
