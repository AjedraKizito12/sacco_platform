"""InvoiceService — invoice lifecycle.

Invoice numbering: per-year Postgres SEQUENCE named `invoice_seq_YYYY` in
the `platform` schema. Format: INV-YYYY-NNNNNN. Sequences are created
lazily via `CREATE SEQUENCE IF NOT EXISTS`.

v1 line items: one base-price line per invoice. Per-user/per-member
billing lines are out of scope.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final, cast

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform_.billing.exceptions import InvoiceConflict
from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Subscription,
    SubscriptionPlan,
)

_log = structlog.get_logger(__name__)

_GENERATABLE_STATUSES: Final[frozenset[str]] = frozenset(
    {"trialing", "active", "past_due"}
)

_BILLING_PERIOD_DAYS: Final[dict[str, int]] = {
    "monthly": 30,
    "quarterly": 90,
    "annual": 365,
}


class InvoiceService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ── Numbering ──────────────────────────────────────────────────────────

    async def _next_invoice_number(self, *, today: date | None = None) -> str:
        """Allocate the next invoice number from this year's sequence.

        Creates the sequence lazily if it doesn't exist (e.g., first invoice
        of a new year). CREATE SEQUENCE IF NOT EXISTS is idempotent across
        racing callers.
        """
        d = today or date.today()
        seq_name = f"platform.invoice_seq_{d.year}"
        await self._s.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}"))
        n = await self._s.scalar(text(f"SELECT nextval('{seq_name}')"))
        if n is None:  # pragma: no cover — nextval cannot return null
            raise RuntimeError("nextval returned None")
        return f"INV-{d.year}-{int(n):06d}"

    # ── Queries ────────────────────────────────────────────────────────────

    async def get(self, invoice_id: uuid.UUID) -> Invoice | None:
        return cast(
            Invoice | None,
            await self._s.scalar(select(Invoice).where(Invoice.id == invoice_id)),
        )

    async def get_for_subscription_period(
        self,
        *,
        subscription_id: uuid.UUID,
        billing_period_start: date,
    ) -> Invoice | None:
        """Return the (one and only) invoice for this subscription/period,
        if it exists. Used by `generate_for_subscription` for idempotency.
        """
        return cast(
            Invoice | None,
            await self._s.scalar(
                select(Invoice).where(
                    Invoice.subscription_id == subscription_id,
                    Invoice.billing_period_start == billing_period_start,
                )
            ),
        )

    # ── Commands ───────────────────────────────────────────────────────────

    async def generate_for_subscription(
        self,
        *,
        subscription_id: uuid.UUID,
        billing_period_start: date | None = None,
    ) -> Invoice:
        """Generate the issued invoice for the subscription's current period.

        If `billing_period_start` is omitted, defaults to
        `subscription.current_period_start`. If an invoice already exists for
        that subscription+period_start, return it (idempotent).

        Raises:
            ValueError: subscription or plan not found.
            InvoiceConflict: subscription is not in a generatable state
                            (cancelled, suspended).
        """
        sub = cast(
            Subscription | None,
            await self._s.scalar(
                select(Subscription).where(Subscription.id == subscription_id)
            ),
        )
        if sub is None:
            raise ValueError(f"Subscription {subscription_id} not found")
        if sub.status not in _GENERATABLE_STATUSES:
            raise InvoiceConflict(
                f"Cannot generate invoice for subscription in status {sub.status!r}"
            )

        plan = cast(
            SubscriptionPlan | None,
            await self._s.scalar(
                select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
            ),
        )
        if plan is None:
            raise ValueError(f"SubscriptionPlan {sub.plan_id} not found")

        period_start = billing_period_start or sub.current_period_start
        existing = await self.get_for_subscription_period(
            subscription_id=subscription_id,
            billing_period_start=period_start,
        )
        if existing is not None:
            return existing

        period_end = period_start + timedelta(
            days=_BILLING_PERIOD_DAYS[plan.billing_period]
        )
        # Standard net-7 due: due_at = period_start + 7 days.
        due_at = period_start + timedelta(days=7)
        now = datetime.now(UTC)

        invoice_number = await self._next_invoice_number()

        invoice = Invoice(
            invoice_number=invoice_number,
            subscription_id=subscription_id,
            tenant_id=sub.tenant_id,
            billing_period_start=period_start,
            billing_period_end=period_end,
            amount_subtotal=plan.base_price,
            amount_tax=Decimal("0"),
            amount_total=plan.base_price,
            amount_paid=Decimal("0"),
            currency=plan.currency,
            status="issued",
            issued_at=now,
            due_at=due_at,
        )
        self._s.add(invoice)
        await self._s.flush()

        line = InvoiceLineItem(
            invoice_id=invoice.id,
            description=f"Base subscription ({plan.billing_period})",
            quantity=1,
            unit_price=plan.base_price,
            amount=plan.base_price,
            line_order=1,
        )
        self._s.add(line)
        await self._s.flush()

        _log.info(
            "invoice.generated",
            invoice_id=str(invoice.id),
            invoice_number=invoice_number,
            subscription_id=str(sub.id),
            tenant_id=str(sub.tenant_id),
            amount_total=str(plan.base_price),
        )

        from app.core.outbox.publisher import EventPublisher  # noqa: PLC0415

        await EventPublisher.publish(
            self._s,
            aggregate_type="invoice",
            aggregate_id=invoice.id,
            event_type="BillingInvoiceIssued",
            payload={
                "invoice_id": str(invoice.id),
                "tenant_id": str(sub.tenant_id),
                "invoice_number": invoice_number,
                "amount_total": str(plan.base_price),
                "currency": invoice.currency,
                "due_at": due_at.isoformat(),
            },
        )
        return invoice

    async def void(
        self,
        *,
        invoice_id: uuid.UUID,
        reason: str,
    ) -> Invoice:
        """Void an invoice that has not received any payment.

        Only invoices with amount_paid == 0 are voidable. Voiding a partial
        or paid invoice raises InvoiceConflict; the caller must reverse
        payments first (out of scope for v1).

        Raises:
            ValueError: invoice not found.
            InvoiceConflict: invoice already void, or has nonzero amount_paid.
        """
        invoice = await self.get(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        if invoice.status == "void":
            raise InvoiceConflict(f"Invoice {invoice_id} is already void")
        if invoice.amount_paid > Decimal("0"):
            raise InvoiceConflict(
                f"Invoice {invoice_id} has amount_paid={invoice.amount_paid}; "
                "reverse payments before voiding"
            )

        invoice.status = "void"
        invoice.voided_at = datetime.now(UTC)
        invoice.void_reason = reason
        await self._s.flush()

        _log.info(
            "invoice.voided",
            invoice_id=str(invoice.id),
            invoice_number=invoice.invoice_number,
            tenant_id=str(invoice.tenant_id),
            reason=reason,
        )
        return invoice

    async def mark_overdue(self, *, invoice_id: uuid.UUID) -> Invoice:
        """Mark a single invoice overdue. Silent no-op if invoice is not
        in {'issued', 'partial'} or if due_at has not passed.
        """
        invoice = await self.get(invoice_id)
        if invoice is None:
            raise ValueError(f"Invoice {invoice_id} not found")
        if invoice.status not in {"issued", "partial"}:
            return invoice
        if invoice.due_at >= date.today():
            return invoice

        invoice.status = "overdue"
        await self._s.flush()

        _log.info(
            "invoice.overdue",
            invoice_id=str(invoice.id),
            invoice_number=invoice.invoice_number,
            tenant_id=str(invoice.tenant_id),
            due_at=invoice.due_at.isoformat(),
        )
        return invoice

    async def mark_overdue_batch(self, *, as_of: date | None = None) -> int:
        """Mark all overdue invoices in one pass. Returns count transitioned.

        This is the beat-job-friendly bulk version. Uses a single UPDATE
        statement to keep the lock window small.
        """
        cutoff = as_of or date.today()
        result = await self._s.execute(
            text(
                "UPDATE platform.invoices "
                "SET status = 'overdue', updated_at = now() "
                "WHERE status IN ('issued', 'partial') "
                "AND due_at < :cutoff "
                "RETURNING id, tenant_id, invoice_number, amount_total, "
                "amount_paid, currency"
            ),
            {"cutoff": cutoff},
        )
        rows = result.fetchall()
        affected = len(rows)

        from app.core.outbox.publisher import EventPublisher  # noqa: PLC0415

        for row in rows:
            await EventPublisher.publish(
                self._s,
                aggregate_type="invoice",
                aggregate_id=row.id,
                event_type="BillingInvoiceOverdue",
                payload={
                    "invoice_id": str(row.id),
                    "tenant_id": str(row.tenant_id),
                    "invoice_number": row.invoice_number,
                    "amount_outstanding": str(row.amount_total - row.amount_paid),
                    "currency": row.currency,
                },
            )
        _log.info(
            "invoice.mark_overdue_batch",
            cutoff=cutoff.isoformat(),
            invoices_transitioned=affected,
        )
        return affected
