# app/modules/credit/services/repayment.py
"""LoanRepaymentService — interest-first allocation, GL posting, closure detection."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanInstallment, LoanRepayment

_log = structlog.get_logger(__name__)

_TERMINAL_STATUSES = frozenset({"closed", "written_off"})


class LoanRepaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply_repayment(
        self,
        *,
        loan_id: uuid.UUID,
        amount: Decimal,
        payment_account_id: uuid.UUID,
        posted_by: uuid.UUID,
        narration: str | None = None,
        idempotency_key: str,
        savings_account_id: uuid.UUID | None = None,
    ) -> LoanRepayment:
        """Apply a repayment to a loan. Interest-first allocation.

        Steps:
        1. Idempotency guard.
        2. Lock loan row (FOR UPDATE).
        3. Validate loan status.
        4. Allocate: interest → principal → penalties → overpayment.
        5. Post GL entry (balanced double-entry).
        6. Update loan snapshot fields.
        7. Create LoanRepayment row.
        8. Update installments (oldest-first).
        9. Closure detection.
        10. Publish outbox events.
        """
        from app.core.outbox import EventPublisher
        from app.modules.ledger.service import LedgerService

        # ── Step 1: Idempotency guard ─────────────────────────────────────────
        existing = await self._session.scalar(
            select(LoanRepayment).where(LoanRepayment.idempotency_key == idempotency_key)
        )
        if existing is not None:
            _log.info("credit.repayment.idempotent_hit", idempotency_key=idempotency_key)
            return existing

        # ── Step 2: Lock loan row ─────────────────────────────────────────────
        loan = await self._session.scalar(
            select(Loan).where(Loan.id == loan_id).with_for_update()
        )
        if loan is None:
            raise ValueError(f"Loan '{loan_id}' not found")

        # ── Step 3: Validate status ───────────────────────────────────────────
        if loan.status in _TERMINAL_STATUSES:
            raise ValueError(
                f"Cannot apply repayment: loan '{loan_id}' is {loan.status}"
            )
        if loan.status == "disbursing":
            raise ValueError(
                f"Cannot apply repayment: loan '{loan_id}' is still disbursing"
            )

        # ── Step 4: Allocation ────────────────────────────────────────────────
        remaining = amount

        interest_applied = min(remaining, loan.accrued_interest)
        remaining -= interest_applied

        principal_applied = min(remaining, loan.outstanding_principal)
        remaining -= principal_applied

        penalties_applied = min(remaining, loan.accrued_penalties)
        remaining -= penalties_applied

        overpayment = remaining

        # Total actually applied to loan (excluding overpayment)
        total_applied = interest_applied + principal_applied + penalties_applied

        # ── Step 5: Post GL entry ─────────────────────────────────────────────
        # Only post GL for what was actually applied (not overpayment).
        # Dr payment_account (cash/bank) for the total applied.
        # Cr principal_receivable for principal_applied (if > 0).
        # Cr interest_receivable for interest_applied (if > 0).
        gl_lines: list[dict] = []

        if total_applied > Decimal("0"):
            gl_lines.append({
                "account_id": payment_account_id,
                "debit_amount": total_applied,
                "credit_amount": Decimal("0"),
                "sub_ledger_type": "loan",
                "sub_ledger_id": loan.id,
            })
            if principal_applied > Decimal("0"):
                gl_lines.append({
                    "account_id": loan.gl_principal_receivable_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": principal_applied,
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": loan.id,
                })
            if interest_applied > Decimal("0"):
                gl_lines.append({
                    "account_id": loan.gl_interest_receivable_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": interest_applied,
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": loan.id,
                })
        else:
            # Pure overpayment: no GL movement (nothing was applied)
            # Create a zero-effect entry so journal_entry_id is populated.
            # We still need a balanced entry — use payment account as both sides
            # with zero amounts... but LedgerService requires at least 2 lines and
            # debits == credits. Post a minimal balanced self-referencing entry.
            gl_lines.append({
                "account_id": payment_account_id,
                "debit_amount": Decimal("0"),
                "credit_amount": Decimal("0"),
                "sub_ledger_type": "loan",
                "sub_ledger_id": loan.id,
            })
            gl_lines.append({
                "account_id": loan.gl_principal_receivable_id,
                "debit_amount": Decimal("0"),
                "credit_amount": Decimal("0"),
                "sub_ledger_type": "loan",
                "sub_ledger_id": loan.id,
            })

        ledger_svc = LedgerService(self._session)
        journal_entry = await ledger_svc.post_journal_entry(
            reference=f"LOAN-RPY-{loan_id}",
            description=narration or f"Loan repayment: {loan.loan_reference}",
            posted_by=posted_by,
            idempotency_key=f"loan-rpy-{idempotency_key}",
            lines=gl_lines,
        )

        # ── Step 6: Update loan snapshot ──────────────────────────────────────
        loan.accrued_interest -= interest_applied
        loan.outstanding_principal -= principal_applied
        loan.accrued_penalties -= penalties_applied
        loan.total_paid_interest += interest_applied
        loan.total_paid_principal += principal_applied
        loan.total_paid_penalties += penalties_applied
        loan.last_repayment_at = datetime.now(UTC)
        loan.last_repayment_amount = amount

        # ── Step 7: Create LoanRepayment row ──────────────────────────────────
        repayment = LoanRepayment(
            loan_id=loan_id,
            amount=amount,
            principal_applied=principal_applied,
            interest_applied=interest_applied,
            penalties_applied=penalties_applied,
            overpayment=overpayment,
            payment_account_id=payment_account_id,
            journal_entry_id=journal_entry.id,
            posted_by=posted_by,
            narration=narration,
            idempotency_key=idempotency_key,
        )
        self._session.add(repayment)
        await self._session.flush()

        # ── Step 8: Update installments ───────────────────────────────────────
        await self._update_installments(
            loan_id=loan_id,
            interest_to_allocate=interest_applied,
            principal_to_allocate=principal_applied,
        )

        # ── Step 9: Closure detection ─────────────────────────────────────────
        is_closed = (
            loan.outstanding_principal <= Decimal("0")
            and loan.accrued_interest <= Decimal("0")
            and loan.accrued_penalties <= Decimal("0")
        )
        if is_closed:
            loan.status = "closed"
            loan.closed_at = datetime.now(UTC)

        await self._session.flush()

        # ── Step 9b: Record savings statement row ─────────────────────────────
        if savings_account_id is not None:
            from app.modules.savings.service import SavingsService

            savings_svc = SavingsService(self._session)
            await savings_svc.record_external_debit(
                savings_account_id=savings_account_id,
                amount=amount,
                journal_entry_id=journal_entry.id,
                source_module="credit",
                source_id=loan.id,
                narration=narration or f"Loan repayment: {loan.loan_reference}",
                idempotency_key=f"loan-rpy-savings-{idempotency_key}",
            )

        # ── Step 10: Publish outbox events ────────────────────────────────────
        await EventPublisher.publish(
            self._session,
            aggregate_type="loan",
            aggregate_id=loan_id,
            event_type="LoanRepaymentPosted",
            payload={
                "repayment_id": str(repayment.id),
                "loan_id": str(loan_id),
                "amount": str(amount),
                "interest_applied": str(interest_applied),
                "principal_applied": str(principal_applied),
                "penalties_applied": str(penalties_applied),
                "overpayment": str(overpayment),
            },
        )

        if is_closed:
            await EventPublisher.publish(
                self._session,
                aggregate_type="loan",
                aggregate_id=loan_id,
                event_type="LoanClosed",
                payload={
                    "loan_id": str(loan_id),
                    "loan_reference": loan.loan_reference,
                    "closed_at": loan.closed_at.isoformat() if loan.closed_at else None,
                },
            )

        _log.info(
            "credit.repayment.posted",
            loan_id=str(loan_id),
            amount=str(amount),
            interest_applied=str(interest_applied),
            principal_applied=str(principal_applied),
            closed=is_closed,
        )
        return repayment

    async def _update_installments(
        self,
        *,
        loan_id: uuid.UUID,
        interest_to_allocate: Decimal,
        principal_to_allocate: Decimal,
    ) -> None:
        """Allocate interest and principal to oldest pending/partial/overdue installments."""
        result = await self._session.execute(
            select(LoanInstallment)
            .where(
                LoanInstallment.loan_id == loan_id,
                LoanInstallment.status.in_(["pending", "partial", "overdue"]),
            )
            .order_by(LoanInstallment.period_number)
            .with_for_update()
        )
        installments = list(result.scalars().all())

        now = datetime.now(UTC)

        for inst in installments:
            if interest_to_allocate <= Decimal("0") and principal_to_allocate <= Decimal("0"):
                break

            # Allocate interest first to this installment
            interest_remaining_on_inst = inst.interest_due - inst.interest_paid
            interest_for_inst = min(interest_to_allocate, interest_remaining_on_inst)
            if interest_for_inst > Decimal("0"):
                inst.interest_paid += interest_for_inst
                interest_to_allocate -= interest_for_inst

            # Then allocate principal to this installment
            principal_remaining_on_inst = inst.principal_due - inst.principal_paid
            principal_for_inst = min(principal_to_allocate, principal_remaining_on_inst)
            if principal_for_inst > Decimal("0"):
                inst.principal_paid += principal_for_inst
                principal_to_allocate -= principal_for_inst

            # Determine new status
            fully_paid_interest = inst.interest_paid >= inst.interest_due
            fully_paid_principal = inst.principal_paid >= inst.principal_due
            if fully_paid_interest and fully_paid_principal:
                inst.status = "paid"
                inst.paid_at = now
            elif inst.interest_paid > Decimal("0") or inst.principal_paid > Decimal("0"):
                inst.status = "partial"

    async def list_repayments(self, loan_id: uuid.UUID) -> list[LoanRepayment]:
        """Return all repayments for a loan, newest first."""
        result = await self._session.execute(
            select(LoanRepayment)
            .where(LoanRepayment.loan_id == loan_id)
            .order_by(LoanRepayment.created_at.desc())
        )
        return list(result.scalars().all())
