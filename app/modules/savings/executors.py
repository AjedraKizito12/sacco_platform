"""Maker-checker executors for savings withdrawal operations.

Import this module at app startup to register executors in approval_registry.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.modules.maker_checker.registry import approval_executor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("savings.withdraw")  # type: ignore[misc]
async def execute_withdraw(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    """Executor: called by ApprovalService.approve() when quorum is met.

    payload keys (all strings — JSON round-tripped through JSONB):
        savings_account_id: str (UUID)
        amount: str (Decimal)
        payment_account_id: str (UUID)
        liability_account_id: str (UUID)
        posted_by: str (UUID)
        narration: str | None
        idempotency_key: str
    """
    # Import inside function to avoid circular imports at module load time.
    from app.modules.ledger.service import LedgerService
    from app.modules.savings.models import SavingsTransaction

    savings_account_id = uuid.UUID(payload["savings_account_id"])
    amount = Decimal(payload["amount"])
    payment_account_id = uuid.UUID(payload["payment_account_id"])
    liability_account_id = uuid.UUID(payload["liability_account_id"])
    posted_by = uuid.UUID(payload["posted_by"])
    narration = payload.get("narration")
    idempotency_key = payload["idempotency_key"]

    # Idempotency guard — return early if already executed.
    from sqlalchemy import select as sa_select
    existing = await session.scalar(
        sa_select(SavingsTransaction).where(
            SavingsTransaction.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return {
            "savings_account_id": str(savings_account_id),
            "amount": str(amount),
            "journal_entry_id": str(existing.journal_entry_id),
        }

    # GL: DEBIT savings liability, CREDIT payment account (cash/bank).
    # Exact reversal of a deposit.
    ledger_svc = LedgerService(session)
    entry = await ledger_svc.post_journal_entry(
        reference=f"SAV-WDR-{savings_account_id}",
        description=f"Savings withdrawal: {amount}",
        posted_by=posted_by,
        idempotency_key=f"savings-withdraw-{idempotency_key}",
        lines=[
            {
                "account_id": liability_account_id,
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

    txn = SavingsTransaction(
        savings_account_id=savings_account_id,
        transaction_type="withdrawal",
        amount=amount,
        narration=narration,
        journal_entry_id=entry.id,
        posted_by=posted_by,
        idempotency_key=idempotency_key,
    )
    session.add(txn)
    await session.flush()

    return {
        "savings_account_id": str(savings_account_id),
        "amount": str(amount),
        "journal_entry_id": str(entry.id),
    }
