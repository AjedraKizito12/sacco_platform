"""Maker-checker executors for manual GL operations.

Import this module at app startup to register executors in approval_registry.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.maker_checker.registry import approval_executor


@approval_executor("ledger.post_journal_entry")
async def execute_post_journal_entry(
    session: AsyncSession, payload: dict
) -> dict:
    """Executor: called by ApprovalService.approve() when quorum is met.

    payload keys (all strings — JSON round-tripped through JSONB):
        reference: str
        description: str
        posted_by: str (UUID)
        idempotency_key: str
        lines: list of {account_id: str, debit_amount: str, credit_amount: str, description: str|null}
    """
    # Import inside function to avoid circular imports at module load time.
    from app.modules.ledger.service import LedgerService

    svc = LedgerService(session)
    lines = [
        {
            "account_id": uuid.UUID(ln["account_id"]),
            "debit_amount": Decimal(ln["debit_amount"]),
            "credit_amount": Decimal(ln["credit_amount"]),
            "description": ln.get("description"),
        }
        for ln in payload["lines"]
    ]
    entry = await svc.post_journal_entry(
        reference=payload["reference"],
        description=payload["description"],
        posted_by=uuid.UUID(payload["posted_by"]),
        idempotency_key=payload["idempotency_key"],
        lines=lines,
    )
    return {"journal_entry_id": str(entry.id)}
