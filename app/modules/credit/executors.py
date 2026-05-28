# app/modules/credit/executors.py
"""Maker-checker executors for credit operations.

Import this module at app startup to register executors in approval_registry.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.modules.maker_checker.registry import approval_executor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("credit.approve_application")
async def execute_approve_application(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: called by ApprovalService.approve() when quorum is met.

    payload keys (all strings — JSON round-tripped through JSONB):
        application_id: str (UUID)
        approved_amount: str (Decimal)
        approved_term_periods: str (int)
    """
    from app.modules.credit.models import LoanApplication

    application_id = uuid.UUID(payload["application_id"])
    approved_amount = Decimal(payload["approved_amount"])
    approved_term_periods = int(payload["approved_term_periods"])

    application = await session.get(LoanApplication, application_id)
    if application is None:
        raise ValueError(f"LoanApplication '{application_id}' not found in executor")

    # Idempotency guard — already approved on a prior executor call.
    if application.status == "approved":
        return {
            "application_id": str(application_id),
            "status": "approved",
        }

    application.status = "approved"
    application.approved_amount = approved_amount
    application.approved_term_periods = approved_term_periods
    await session.flush()

    return {
        "application_id": str(application_id),
        "status": "approved",
    }


@approval_executor("credit.write_off")
async def execute_write_off(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: called by ApprovalService.approve() when quorum=2 is met for write-off."""
    loan_id = uuid.UUID(payload["loan_id"])
    amount = Decimal(payload["amount"])
    reason = str(payload["reason"])
    idempotency_key = str(payload["idempotency_key"])
    loan_loss_account_code = str(payload.get("loan_loss_account_code", "5100"))

    from app.modules.credit.models import Loan  # noqa: PLC0415
    from app.modules.credit.services.write_off import LoanWriteOffService  # noqa: PLC0415
    from app.modules.ledger.models import JournalEntry  # noqa: PLC0415

    # Idempotency guard.
    idem_key = f"loan-wo-{idempotency_key}"
    existing = await session.scalar(
        select(JournalEntry).where(JournalEntry.idempotency_key == idem_key)
    )
    if existing is not None:
        return {"status": "already_executed"}

    loan = await session.scalar(select(Loan).where(Loan.id == loan_id).with_for_update())
    if loan is None:
        raise ValueError(f"Loan {loan_id} not found in write_off executor")

    svc = LoanWriteOffService(session)
    await svc._execute_write_off(
        loan=loan,
        amount=amount,
        reason=reason,
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        idem_key=idem_key,
        loan_loss_account_code=loan_loss_account_code,
    )
    return {"status": "written_off", "loan_id": str(loan_id)}


@approval_executor("credit.restructure_schedule")
async def execute_restructure_schedule(
    session: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """Executor: called by ApprovalService when quorum=2 is met for restructuring."""
    from app.modules.credit.services.restructuring import LoanRestructuringService  # noqa: PLC0415

    loan_id = uuid.UUID(payload["loan_id"])
    restructuring_type = str(payload["restructuring_type"])
    periods_added = int(payload["periods_added"])
    reason = str(payload["reason"])
    idempotency_key = str(payload["idempotency_key"])
    raw_approval_id = payload.get("approval_request_id")
    approval_request_id = uuid.UUID(raw_approval_id) if raw_approval_id else None

    svc = LoanRestructuringService(session)
    restructuring = await svc._execute_restructuring(
        loan_id=loan_id,
        restructuring_type=restructuring_type,
        periods_added=periods_added,
        reason=reason,
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        idempotency_key=idempotency_key,
        approval_request_id=approval_request_id,
    )
    return {"status": "restructured", "restructuring_id": str(restructuring.id)}


@approval_executor("credit.apply_payroll_batch")
async def execute_apply_payroll_batch(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    """Executor: called by ApprovalService when payroll batch is approved."""
    batch_id = uuid.UUID(payload["batch_id"])
    clearing_account_id = uuid.UUID(payload["clearing_account_id"])

    from app.modules.credit.services.payroll import PayrollBatchService  # noqa: PLC0415
    from app.modules.credit.models import PayrollBatch  # noqa: PLC0415

    # Mark batch as approved before applying
    batch = await session.get(PayrollBatch, batch_id)
    if batch is not None and batch.status == "pending_review":
        batch.status = "approved"
        await session.flush()

    svc = PayrollBatchService(session)
    await svc.apply_batch(
        batch_id=batch_id,
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        clearing_account_id=clearing_account_id,
    )
    return {"status": "applied", "batch_id": str(batch_id)}
