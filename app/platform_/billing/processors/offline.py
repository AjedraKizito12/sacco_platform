"""OfflineProcessor — the v1 default.

Payments are recorded by a human operator after confirming receipt via
bank statement, mobile-money dashboard, etc. `initiate()` is a no-op
that immediately returns a pending result; the actual `Payment` row is
created by the maker via `PaymentService.record()` (SP03) and confirmed
by the checker via the maker-checker flow (SP04).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.platform_.billing.processors.base import PaymentProcessor, ProcessorResult


class OfflineProcessor(PaymentProcessor):
    @property
    def code(self) -> str:
        return "offline"

    async def initiate(
        self,
        *,
        invoice_id: UUID,
        amount: Decimal,
        payment_method: str,
        external_reference: str | None,
    ) -> ProcessorResult:
        if amount <= Decimal("0"):
            return ProcessorResult(
                status="failed",
                external_id=None,
                message="amount must be greater than 0",
            )
        return ProcessorResult(
            status="pending",
            external_id=None,
            message="awaiting human confirmation",
        )
