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

from app.platform_.billing.exceptions import (
    OverpaymentRejected,
    PaymentConflict,
)
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

    async def confirm(
        self,
        *,
        payment_id: uuid.UUID,
        confirmed_by: uuid.UUID | None = None,
    ) -> Payment:
        """Confirm a pending payment. Applies amount to the parent invoice.

        Args:
            payment_id: target payment.
            confirmed_by: the checker's user_id. When None, the maker/checker
                check is skipped — this is the path used by the
                `billing.confirm_payment` approval executor, since
                `ApprovalService.approve()` has already enforced maker != checker.

        Transitions:
            payment.status: pending → confirmed
            invoice.amount_paid: += payment.amount
            invoice.status:
                amount_paid == amount_total → 'paid' (paid_at set)
                0 < amount_paid < amount_total → 'partial'
                else → unchanged

        Raises:
            ValueError: payment not found.
            PaymentConflict: payment not pending, or self-approval attempt
                            (only when confirmed_by is provided).
            OverpaymentRejected: confirmation would push amount_paid past total.
        """
        pmt = await self.get(payment_id)
        if pmt is None:
            raise ValueError(f"Payment {payment_id} not found")
        if pmt.status != "pending":
            raise PaymentConflict(
                f"Cannot confirm payment in status {pmt.status!r}"
            )
        if confirmed_by is not None and pmt.recorded_by == confirmed_by:
            raise PaymentConflict(
                "Maker cannot be checker (payment.recorded_by == confirmed_by)"
            )

        invoice = cast(
            Invoice | None,
            await self._s.scalar(
                select(Invoice).where(Invoice.id == pmt.invoice_id)
            ),
        )
        if invoice is None:  # pragma: no cover — FK guarantees existence
            raise ValueError(f"Invoice {pmt.invoice_id} not found")

        new_paid = invoice.amount_paid + pmt.amount
        if new_paid > invoice.amount_total:
            raise OverpaymentRejected(
                f"Confirming would make amount_paid={new_paid} > "
                f"amount_total={invoice.amount_total}"
            )

        now = datetime.now(UTC)
        pmt.status = "confirmed"
        pmt.confirmed_at = now
        invoice.amount_paid = new_paid
        if new_paid == invoice.amount_total:
            invoice.status = "paid"
            invoice.paid_at = now
        elif new_paid > Decimal("0"):
            invoice.status = "partial"
        await self._s.flush()

        _log.info(
            "payment.confirmed",
            payment_id=str(pmt.id),
            invoice_id=str(invoice.id),
            tenant_id=str(invoice.tenant_id),
            amount=str(pmt.amount),
            new_invoice_status=invoice.status,
            confirmed_by=str(confirmed_by),
        )
        return pmt

    async def reject(
        self,
        *,
        payment_id: uuid.UUID,
        rejected_by: uuid.UUID,
        reason: str,
    ) -> Payment:
        """Reject a pending payment. Invoice is not touched.

        Raises:
            ValueError: payment not found.
            PaymentConflict: payment not pending, or self-rejection attempt.
        """
        pmt = await self.get(payment_id)
        if pmt is None:
            raise ValueError(f"Payment {payment_id} not found")
        if pmt.status != "pending":
            raise PaymentConflict(
                f"Cannot reject payment in status {pmt.status!r}"
            )
        if pmt.recorded_by == rejected_by:
            raise PaymentConflict(
                "Maker cannot be checker (payment.recorded_by == rejected_by)"
            )

        pmt.status = "rejected"
        # Reason is captured in audit log (SP04), not in the Payment row.
        await self._s.flush()

        _log.info(
            "payment.rejected",
            payment_id=str(pmt.id),
            invoice_id=str(pmt.invoice_id),
            rejected_by=str(rejected_by),
            reason=reason,
        )
        return pmt
