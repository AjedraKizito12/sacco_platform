"""Domain exceptions for the billing module.

Service callers catch these instead of relying on DB error strings.
"""
from __future__ import annotations


class BillingError(Exception):
    """Base class for all billing-module domain errors."""


class SubscriptionConflict(BillingError):
    """Raised when a tenant already has a live subscription and we tried
    to create another one."""


class PlanInactive(BillingError):
    """Raised when the requested plan is_active=False at assign() time."""


class InvalidTransition(BillingError):
    """Raised when a state transition is requested from a status it isn't
    allowed from."""

    def __init__(self, *, from_status: str, to_status: str) -> None:
        super().__init__(f"cannot transition from {from_status!r} to {to_status!r}")
        self.from_status = from_status
        self.to_status = to_status


class InvoiceConflict(BillingError):
    """Raised when an invoice operation conflicts with current state
    (e.g., voiding a partially-paid invoice, or generating an invoice for
    a billing period that already has one).
    """


class PaymentConflict(BillingError):
    """Raised when a payment operation conflicts with current state
    (e.g., confirming an already-confirmed payment).
    """


class OverpaymentRejected(BillingError):
    """Raised when a payment confirmation would push amount_paid past
    amount_total. Use partial-then-final flow instead.
    """
