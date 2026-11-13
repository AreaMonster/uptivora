"""Self-hosted licence store (hosted edition).

Flow: customer pays → order ``paid`` → the isolated signing service (``app.signer``) signs the
licence, or an operator attaches a file signed offline with ``tools/licensegen`` → the server
verifies it with the embedded public keys before accepting it → order ``fulfilled`` → email
to the customer, who downloads it. The signing key is never readable by the API or worker.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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

log = logging.getLogger("uptivora.licences")


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


async def auto_fulfil(db: AsyncSession, settings: Settings, order: LicenseOrder) -> bool:
    """Have the signing service sign a paid order. False (order stays ``paid``, retried by
    the worker and visible to admins) if the signer is not configured or unavailable."""
    from app.billing import signer_client

    if not settings.signer_url or order.status != LicenseOrderStatus.PAID:
        return False
    product = await db.get(LicenseProduct, order.product_id)
    if product is None:
        return False
    try:
        text = await signer_client.request_licence(settings, order, product)
        await fulfil_order(db, settings, order, text)
    except (signer_client.SignerError, AppError) as exc:
        await db.rollback()
        log.warning("Licence for order %s not signed yet: %s", order.id, exc)
        return False
    log.info("Licence for order %s signed and delivered", order.id)
    return True


async def fulfil_pending_orders(maker: async_sessionmaker[AsyncSession], settings: Settings) -> int:
    """Worker job: retry paid orders whose licence could not be signed right away."""
    if not settings.signer_url:
        return 0
    done = 0
    async with maker() as db:
        ids = (
            await db.scalars(
                select(LicenseOrder.id).where(
                    LicenseOrder.status == LicenseOrderStatus.PAID,
                    LicenseOrder.paid_at < datetime.now(UTC) - timedelta(seconds=30),
                )
            )
        ).all()
    for order_id in ids:
        async with maker() as db:
            order = await db.get(LicenseOrder, order_id)
            if order is not None and await auto_fulfil(db, settings, order):
                done += 1
    return done


async def reissue_licences(
    maker: async_sessionmaker[AsyncSession], settings: Settings, *, from_key_id: str | None = None
) -> tuple[int, int]:
    """After a key rotation: re-sign fulfilled orders not signed with the current key and
    email the new files. Returns (re-issued, failed)."""
    from app.billing import signer_client

    reissued = failed = 0
    async with maker() as db:
        ids = (
            await db.scalars(
                select(LicenseOrder.id).where(LicenseOrder.status == LicenseOrderStatus.FULFILLED)
            )
        ).all()
    for order_id in ids:
        async with maker() as db:
            order = await db.get(LicenseOrder, order_id)
            current = signer_client.licence_key_id(order.license_text or "")
            if current == settings.signer_key_id or (from_key_id and current != from_key_id):
                continue
            product = await db.get(LicenseProduct, order.product_id)
            try:
                text = await signer_client.request_licence(settings, order, product, reissue=True)
                lic = verify_license(text, trusted_keys(settings.env, settings.dev_key_dir))
            except (signer_client.SignerError, LicenseError) as exc:
                log.warning("Re-issue of order %s failed: %s", order.id, exc)
                failed += 1
                continue
            order.license_id = uuid.UUID(lic.license_id)
            order.license_text = text.strip() + "\n"
            user = await db.get(User, order.user_id) if order.user_id else None
            if user is not None:
                await _email(
                    db,
                    user,
                    templates.licence_ready(
                        product.name, f"{settings.public_origin}/billing#licences", order.is_test
                    ),
                    f"licence-reissued:{order.id}:{lic.license_id}",
                )
            await db.commit()
            reissued += 1
    return reissued, failed


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
