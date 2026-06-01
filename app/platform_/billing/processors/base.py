"""PaymentProcessor abstraction.

A `PaymentProcessor` is an external (or no-op) integration that handles
the payment-initiation half of the billing flow. The default in v1 is
`OfflineProcessor`, which is a no-op — invoices are paid via bank transfer
or mobile money outside the platform and the resulting `Payment` row is
created by a human operator through the maker-checker flow.

`flutterwave.py`, `stripe.py`, `momo.py` are import-only stubs in v1.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal  # noqa: TC003
from uuid import UUID  # noqa: TC003


@dataclass(frozen=True)
class ProcessorResult:
    """Outcome of `PaymentProcessor.initiate()`.

    status:
        - "pending"   — call accepted; payment outcome will be determined later
                        (e.g., human confirmation, async webhook).
        - "succeeded" — synchronous success (rare; reserved for direct-debit-style
                        processors that confirm in one round trip).
        - "failed"    — processor rejected the request synchronously.
    external_id:
        Provider-side identifier, if any. None for offline.
    message:
        Human-readable detail (logged, surfaced in UI).
    """

    status: str
    external_id: str | None
    message: str

    def __post_init__(self) -> None:
        if self.status not in {"pending", "succeeded", "failed"}:
            raise ValueError(f"invalid ProcessorResult.status: {self.status!r}")


class PaymentProcessor(ABC):
    """Minimal v1 interface.

    Real processors will add `verify_payment`, `handle_webhook`, `refund` as
    they are needed. YAGNI applies — do not add methods speculatively.
    """

    @property
    @abstractmethod
    def code(self) -> str:
        """Short stable identifier: 'offline', 'flutterwave', 'stripe', 'momo'."""

    @abstractmethod
    async def initiate(
        self,
        *,
        invoice_id: UUID,
        amount: Decimal,
        payment_method: str,
        external_reference: str | None,
    ) -> ProcessorResult:
        """Begin a payment for `invoice_id`. Does NOT write to the DB.

        Args:
            invoice_id: the invoice being paid (already exists).
            amount: payment amount (must be > 0; processor implementations
                    may further restrict).
            payment_method: matches `payments.payment_method` CHECK
                            ('bank_transfer'|'mobile_money'|'cash'|'cheque').
            external_reference: optional caller-supplied reference (bank txn id,
                                MoMo reference, cheque number).
        """
