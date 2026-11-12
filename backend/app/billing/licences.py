"""Self-hosted licence store (hosted edition).

Flow: customer pays → order ``paid`` → an operator signs the licence OFFLINE with
``tools/licensegen`` and attaches the file → the server verifies it with the embedded public
keys before accepting it → order ``fulfilled`` → customer downloads it.
The signing key never touches this server.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.providers import Simulation
from app.billing.service import PaymentDeclined, _charge, _email, ensure_billing
from app.core.config import Settings
from app.core.errors import AppError, Conflict
from app.licensing import LicenseError, trusted_keys, verify_license
from app.models import (
    LicenseOrder,
    LicenseOrderStatus,
    LicenseProduct,
    Payment,
    PaymentStatus,
    User,
)
from app.notifications import templates


async def create_order(
    db: AsyncSession,
    settings: Settings,
    user: User,
    product: LicenseProduct,
    *,
    licensee_name: str,
    licensee_email: str,
    simulate: Simulation = "success",
) -> LicenseOrder:
    ensure_billing(settings)
    if not product.is_active:
        raise AppError(
            "This licence is not available.", code="product_unavailable", status_code=422
        )
    provider_is_test = settings.billing_provider == "test"
    order = LicenseOrder(
        user_id=user.id,
        product_id=product.id,
        status=LicenseOrderStatus.PENDING_PAYMENT,
        price_cents=product.price_cents,
        currency=product.currency,
        is_test=provider_is_test,
        licensee_name=" ".join(licensee_name.split())[:200],
        licensee_email=licensee_email.strip().lower(),
    )
    db.add(order)
    await db.flush()
    result, _payment = await _charge(
        db,
        settings,
        user,
        amount_cents=product.price_cents,
        currency=product.currency,
        description=f"{product.name} (lifetime licence)",
        simulate=simulate,
        license_order_id=order.id,
    )
    if not result.ok:
        order.status = LicenseOrderStatus.CANCELLED
        await db.commit()
        raise PaymentDeclined(result.error or "Payment declined.")
    order.status = LicenseOrderStatus.PAID
    order.paid_at = datetime.now(UTC)
    await db.commit()
    return order


async def fulfil_order(
    db: AsyncSession, settings: Settings, order: LicenseOrder, licence_text: str
) -> LicenseOrder:
    """Attach a signed licence after verifying it like an installation would."""
    if order.status != LicenseOrderStatus.PAID:
        raise Conflict("Only paid orders can be fulfilled.", code="not_paid")
    try:
        lic = verify_license(licence_text, trusted_keys(settings.env, settings.dev_key_dir))
    except LicenseError as exc:
        raise AppError(
            f"Licence rejected: {exc.message}",
            code="invalid_licence",
            status_code=422,
            fields={"licence_text": exc.message},
        ) from exc
    product = await db.get(LicenseProduct, order.product_id)
    if product is None or lic.edition.value != product.edition:
        raise AppError(
            f"This is a {lic.edition.value} licence but the order is for "
            f"{product.edition if product else 'another product'}.",
            code="edition_mismatch",
            status_code=422,
            fields={"licence_text": "Wrong edition"},
        )
    taken = await db.scalar(
        select(LicenseOrder.id).where(
            LicenseOrder.license_id == uuid.UUID(lic.license_id), LicenseOrder.id != order.id
        )
    )
    if taken:
        raise Conflict(
            "This licence file is already attached to another order.",
            code="licence_reused",
            fields={"licence_text": "Already used"},
        )
    order.license_id = uuid.UUID(lic.license_id)
    order.license_text = licence_text.strip() + "\n"
    order.status = LicenseOrderStatus.FULFILLED
    order.fulfilled_at = datetime.now(UTC)
    user = await db.get(User, order.user_id) if order.user_id else None
    if user is not None:
        await _email(
            db,
            user,
            templates.licence_ready(
                product.name, f"{settings.public_origin}/billing#licences", order.is_test
            ),
            f"licence-ready:{order.id}",
        )
    await db.commit()
    return order


async def refund_order(db: AsyncSession, order: LicenseOrder) -> LicenseOrder:
    if order.status not in (LicenseOrderStatus.PAID, LicenseOrderStatus.FULFILLED):
        raise Conflict("Only paid orders can be refunded.", code="not_refundable")
    payments = (
        await db.scalars(
            select(Payment).where(
                Payment.license_order_id == order.id, Payment.status == PaymentStatus.SUCCEEDED
            )
        )
    ).all()
    if any(not p.is_test for p in payments):
        raise Conflict(
            "Refunds of real payments must be made in the payment provider.",
            code="real_refund_unsupported",
        )
    for p in payments:
        p.status = PaymentStatus.REFUNDED
    order.status = LicenseOrderStatus.REFUNDED
    await db.commit()
    return order
