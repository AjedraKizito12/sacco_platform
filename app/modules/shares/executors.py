"""Maker-checker executors for share redemption operations.

Import this module at app startup to register executors in approval_registry.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.maker_checker.registry import approval_executor


@approval_executor("shares.redeem_shares")
async def execute_redeem_shares(
    session: AsyncSession, payload: dict
) -> dict:
    """Executor: called by ApprovalService.approve() when quorum is met.

    payload keys (all strings — JSON round-tripped through JSONB):
        share_account_id: str (UUID)
        quantity: int
        amount: str (Decimal)
        payment_account_id: str (UUID)
        share_capital_account_id: str (UUID)
        posted_by: str (UUID)
        reason: str | None
        idempotency_key: str
    """
    # Import inside function to avoid circular imports at module load time.
    from app.modules.ledger.service import LedgerService
    from app.modules.shares.models import ShareTransaction

    share_account_id = uuid.UUID(payload["share_account_id"])
    quantity = int(payload["quantity"])
    amount = Decimal(payload["amount"])
    payment_account_id = uuid.UUID(payload["payment_account_id"])
    share_capital_account_id = uuid.UUID(payload["share_capital_account_id"])
    posted_by = uuid.UUID(payload["posted_by"])
    idempotency_key = payload["idempotency_key"]

    # Post GL: DEBIT share capital (equity), CREDIT payment account (cash/bank).
    # This is the exact reversal of a purchase.
    ledger_svc = LedgerService(session)
    entry = await ledger_svc.post_journal_entry(
        reference=f"SHARES-REDEEM-{share_account_id}",
        description=f"Share redemption: {quantity} shares",
        posted_by=posted_by,
        idempotency_key=f"share-redeem-{idempotency_key}",
        lines=[
            {
                "account_id": share_capital_account_id,
                "debit_amount": amount,
                "credit_amount": Decimal("0"),
            },
            {
                "account_id": payment_account_id,
                "debit_amount": Decimal("0"),
                "credit_amount": amount,
            },
        ],
    )

    txn = ShareTransaction(
        share_account_id=share_account_id,
        transaction_type="redemption",
        quantity=quantity,
        amount=amount,
        journal_entry_id=entry.id,
        posted_by=posted_by,
        idempotency_key=idempotency_key,
    )
    session.add(txn)
    await session.flush()

    return {
        "share_account_id": str(share_account_id),
        "quantity": quantity,
        "journal_entry_id": str(entry.id),
    }
