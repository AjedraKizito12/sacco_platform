"""PaymentService — payment lifecycle.

State machine:
    record  → pending (maker action)
    confirm → confirmed (checker action; applies amount to invoice)
    reject  → rejected (checker action; no invoice change)

Idempotency: every record() takes an idempotency_key. Replays return
the existing payment row instead of raising. The DB has a UNIQUE
constraint on payments.idempotency_key as the ultimate guard.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal  # noqa: TC003
from typing import cast

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.billing.models import Invoice, Payment

_log = structlog.get_logger(__name__)


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── Queries ────────────────────────────────────────────────────────────

    async def get(self, payment_id: uuid.UUID) -> Payment | None:
        return cast(
            Payment | None,
            await self._s.scalar(select(Payment).where(Payment.id == payment_id)),
        )

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        return cast(
            Payment | None,
            await self._s.scalar(
                select(Payment).where(Payment.idempotency_key == key)
            ),
        )

    # ── Commands ───────────────────────────────────────────────────────────

    async def record(
        self,
        *,
        invoice_id: uuid.UUID,
        amount: Decimal,
        currency: str,
        payment_method: str,
        recorded_by: uuid.UUID,
        idempotency_key: str,
        external_reference: str | None = None,
        notes: str | None = None,
    ) -> Payment:
        """Create a pending payment record. Idempotent on idempotency_key.

        Raises:
            ValueError: invoice not found, or amount/currency mismatch.
        """
        # Idempotency: check before insert.
        existing = await self.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        invoice = cast(
            Invoice | None,
            await self._s.scalar(select(Invoice).where(Invoice.id == invoice_id)),
        )
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        if currency != invoice.currency:
            raise ValueError(
                f"Currency mismatch: payment {currency!r} vs invoice {invoice.currency!r}"
            )

        pmt = Payment(
            invoice_id=invoice_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            external_reference=external_reference,
            notes=notes,
            recorded_by=recorded_by,
            idempotency_key=idempotency_key,
            status="pending",
            recorded_at=datetime.now(UTC),
        )
        self._s.add(pmt)
        try:
            await self._s.flush()
        except IntegrityError:
            # Race: another caller inserted with the same idempotency_key
            # between our check and our flush. Return the existing row.
            await self._s.rollback()
            existing = await self.get_by_idempotency_key(idempotency_key)
            if existing is None:  # pragma: no cover — defensive
                raise
            return existing

        _log.info(
            "payment.recorded",
            payment_id=str(pmt.id),
            invoice_id=str(invoice_id),
            tenant_id=str(invoice.tenant_id),
            amount=str(amount),
            payment_method=payment_method,
            recorded_by=str(recorded_by),
        )
        return pmt
