"""Flutterwave processor — stub.

Not implemented in v1. The class exists so the import graph and the
`PaymentProcessor` registry shape are pinned for future work.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.platform_.billing.processors.base import PaymentProcessor, ProcessorResult


class FlutterwaveProcessor(PaymentProcessor):
    def __init__(self) -> None:
        raise NotImplementedError(
            "FlutterwaveProcessor is a v1 stub; integration is post-launch"
        )

    @property
    def code(self) -> str:
        return "flutterwave"

    async def initiate(
        self,
        *,
        invoice_id: UUID,
        amount: Decimal,
        payment_method: str,
        external_reference: str | None,
    ) -> ProcessorResult:
        raise NotImplementedError
