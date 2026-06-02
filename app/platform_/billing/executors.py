"""Maker-checker executors for billing operations.

Import this module at app startup so the decorators register their executors
in `app.modules.maker_checker.registry.approval_registry`.

Each executor is the second leg of a maker-checker flow:
    maker action (SP05 API)  →  creates ApprovalRequest with the op_type below
    checker approval         →  ApprovalService.approve() invokes the executor

Executor signature: (session: AsyncSession, payload: dict[str, Any]) -> dict.
Payload keys are JSON-roundtripped strings; UUIDs must be parsed.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.modules.maker_checker.registry import approval_executor
from app.platform_.billing.services import (
    InvoiceService,
    PaymentService,
    SubscriptionService,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("billing.confirm_payment")  # type: ignore[misc]
async def execute_confirm_payment(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: runs when a payment-recording request reaches quorum.

    The maker/checker check is enforced by ApprovalService.approve()
    before this executor runs, so we don't re-check here.

    payload keys:
        payment_id: str (UUID) — the pending Payment row created by the maker
    """
    payment_id = uuid.UUID(payload["payment_id"])

    svc = PaymentService(session)
    # Idempotency: if the payment is already confirmed, return success.
    existing = await svc.get(payment_id)
    if existing is not None and existing.status == "confirmed":
        return {
            "payment_id": str(payment_id),
            "status": "confirmed",
            "idempotent": True,
        }

    pmt = await svc.confirm(payment_id=payment_id, confirmed_by=None)
    return {
        "payment_id": str(pmt.id),
        "invoice_id": str(pmt.invoice_id),
        "status": pmt.status,
    }


@approval_executor("billing.void_invoice")  # type: ignore[misc]
async def execute_void_invoice(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: runs when a void-invoice request reaches quorum.

    payload keys:
        invoice_id: str (UUID)
        reason: str
    """
    invoice_id = uuid.UUID(payload["invoice_id"])
    reason = str(payload["reason"])

    svc = InvoiceService(session)
    existing = await svc.get(invoice_id)
    if existing is not None and existing.status == "void":
        return {
            "invoice_id": str(invoice_id),
            "status": "void",
            "idempotent": True,
        }

    inv = await svc.void(invoice_id=invoice_id, reason=reason)
    return {
        "invoice_id": str(inv.id),
        "invoice_number": inv.invoice_number,
        "status": inv.status,
    }


@approval_executor("billing.cancel_subscription")  # type: ignore[misc]
async def execute_cancel_subscription(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: runs when a hard-cancel subscription request reaches quorum.

    Hard cancel only (cancel_at_period_end=False). The soft path (graceful
    end-of-period cancellation) does not need maker-checker — operators can
    call SubscriptionService.cancel(cancel_at_period_end=True) directly.

    payload keys:
        subscription_id: str (UUID)
        reason: str
    """
    subscription_id = uuid.UUID(payload["subscription_id"])
    reason = str(payload["reason"])

    svc = SubscriptionService(session)
    existing = await svc.get(subscription_id)
    if existing is not None and existing.status == "cancelled":
        return {
            "subscription_id": str(subscription_id),
            "status": "cancelled",
            "idempotent": True,
        }

    sub = await svc.cancel(
        subscription_id=subscription_id,
        reason=reason,
        cancel_at_period_end=False,
    )
    return {
        "subscription_id": str(sub.id),
        "status": sub.status,
    }
