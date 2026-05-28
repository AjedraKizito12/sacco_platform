# app/modules/credit/services/write_off.py
"""LoanWriteOffService — direct and maker-checker write-off paths."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.outbox.publisher import EventPublisher
from app.modules.credit.models import Loan, LoanProduct
from app.modules.ledger.models import ChartOfAccount, JournalEntry
from app.modules.ledger.service import LedgerService
from app.modules.maker_checker.service import ApprovalService

_log = structlog.get_logger(__name__)

_SYSTEM_ACTOR = uuid.UUID("00000000-0000-0000-0000-000000000000")


class LoanWriteOffService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write_off(
        self,
        *,
        loan_id: uuid.UUID,
        amount: Decimal,
        reason: str,
        actor_id: uuid.UUID,
        idempotency_key: str,
        loan_loss_account_code: str = "5100",
    ) -> dict[str, Any]:
        """Write off a portion (or all) of a loan's outstanding principal.

        If amount <= product.write_off_threshold → executes directly in this transaction.
        If amount > threshold → submits a maker-checker approval request (quorum=2).

        Returns dict with keys:
            direct: bool
            approval_request_id: uuid.UUID | None
            journal_entry_id: uuid.UUID | None
        """
        idem_key = f"loan-wo-{idempotency_key}"

        # Idempotency guard: check if this write-off journal entry already exists.
        existing_entry = await self._session.scalar(
            select(JournalEntry).where(JournalEntry.idempotency_key == idem_key)
        )
        if existing_entry is not None:
            _log.info("credit.write_off.idempotent_hit", idempotency_key=idempotency_key)
            return {
                "direct": True,
                "approval_request_id": None,
                "journal_entry_id": existing_entry.id,
            }

        # Lock the loan row.
        loan = await self._session.scalar(
            select(Loan).where(Loan.id == loan_id).with_for_update()
        )
        if loan is None:
            raise ValueError(f"Loan '{loan_id}' not found")

        if loan.status == "written_off":
            raise ValueError(
                f"Loan '{loan_id}' is already written_off — cannot write off again"
            )

        if amount > loan.outstanding_principal:
            raise ValueError(
                f"Write-off amount {amount} exceeds outstanding_principal "
                f"{loan.outstanding_principal} for loan '{loan_id}'"
            )

        # Load product for threshold.
        product = await self._session.get(LoanProduct, loan.loan_product_id)
        if product is None:
            raise ValueError(f"LoanProduct '{loan.loan_product_id}' not found")

        if amount > product.write_off_threshold:
            # Maker-checker path.
            approval_svc = ApprovalService(self._session)
            request = await approval_svc.submit(
                operation_type="credit.write_off",
                payload={
                    "loan_id": str(loan_id),
                    "amount": str(amount),
                    "reason": reason,
                    "idempotency_key": idempotency_key,
                    "loan_loss_account_code": loan_loss_account_code,
                },
                requested_by=actor_id,
                required_approvals=2,
            )
            _log.info(
                "credit.write_off.pending_approval",
                loan_id=str(loan_id),
                amount=str(amount),
                approval_request_id=str(request.id),
            )
            return {
                "direct": False,
                "approval_request_id": request.id,
                "journal_entry_id": None,
            }

        # Direct path.
        entry = await self._execute_write_off(
            loan=loan,
            amount=amount,
            reason=reason,
            actor_id=actor_id,
            idem_key=idem_key,
            loan_loss_account_code=loan_loss_account_code,
        )
        return {
            "direct": True,
            "approval_request_id": None,
            "journal_entry_id": entry.id,
        }

    async def _execute_write_off(
        self,
        *,
        loan: Loan,
        amount: Decimal,
        reason: str,
        actor_id: uuid.UUID,
        idem_key: str,
        loan_loss_account_code: str,
    ) -> JournalEntry:
        """Post GL, update loan snapshot, publish event. Called directly or from executor."""
        # Resolve GL accounts.
        loan_loss_acct = await self._session.scalar(
            select(ChartOfAccount).where(ChartOfAccount.code == loan_loss_account_code)
        )
        if loan_loss_acct is None:
            raise ValueError(
                f"GL account '{loan_loss_account_code}' not found for loan loss expense"
            )

        # Dr loan_loss_expense / Cr gl_principal_receivable.
        ledger_svc = LedgerService(self._session)
        entry = await ledger_svc.post_journal_entry(
            reference=f"LOAN-WO-{loan.id}",
            description=f"Write-off: {reason}",
            posted_by=actor_id,
            idempotency_key=idem_key,
            lines=[
                {
                    "account_id": loan_loss_acct.id,
                    "debit_amount": amount,
                    "credit_amount": Decimal("0"),
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": loan.id,
                },
                {
                    "account_id": loan.gl_principal_receivable_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": amount,
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": loan.id,
                },
            ],
        )

        # Update snapshot.
        loan.outstanding_principal = loan.outstanding_principal - amount
        loan.total_written_off = loan.total_written_off + amount
        if loan.outstanding_principal == Decimal("0"):
            loan.status = "written_off"

        await self._session.flush()

        await EventPublisher.publish(
            self._session,
            aggregate_type="loan",
            aggregate_id=loan.id,
            event_type="LoanWrittenOff",
            payload={
                "loan_id": str(loan.id),
                "amount": str(amount),
                "reason": reason,
                "journal_entry_id": str(entry.id),
            },
        )

        _log.info(
            "credit.loan.written_off",
            loan_id=str(loan.id),
            amount=str(amount),
            journal_entry_id=str(entry.id),
        )
        return entry
