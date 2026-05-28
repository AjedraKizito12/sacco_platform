# app/modules/credit/services/disbursement.py
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select, text

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanApplication, LoanInstallment
from app.modules.credit.services._schedule import compute_schedule
from app.modules.ledger.models import ChartOfAccount

_log = structlog.get_logger(__name__)


class LoanDisbursementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def disburse(
        self,
        *,
        loan_application_id: uuid.UUID,
        actor_id: uuid.UUID,
        idempotency_key: str,
    ) -> Loan:
        """Disburse an approved loan application. All steps in one transaction."""
        from app.modules.ledger.service import LedgerService

        # Step 1: Idempotency guard (checked first so retries don't hit status guard).
        existing_loan = await self._session.scalar(
            select(Loan).where(Loan.idempotency_key == idempotency_key)
        )
        if existing_loan is not None:
            _log.info(
                "credit.disburse.idempotent_hit", idempotency_key=idempotency_key
            )
            return existing_loan

        # Step 2: Lock application row.
        result = await self._session.execute(
            select(LoanApplication)
            .where(LoanApplication.id == loan_application_id)
            .with_for_update()
        )
        application = result.scalar_one_or_none()
        if application is None:
            raise ValueError(f"LoanApplication '{loan_application_id}' not found")
        if application.status != "approved":
            raise ValueError(
                f"Cannot disburse application with status '{application.status}' — "
                f"must be 'approved'"
            )

        # Fetch product for terms.
        from app.modules.credit.models import LoanProduct

        product = await self._session.get(LoanProduct, application.loan_product_id)
        if product is None:
            raise ValueError(f"LoanProduct '{application.loan_product_id}' not found")

        principal = application.approved_amount
        term_periods = application.approved_term_periods

        # Step 3: Resolve GL account IDs from codes.
        principal_recv = await self._session.scalar(
            select(ChartOfAccount).where(
                ChartOfAccount.code == product.gl_principal_receivable_code
            )
        )
        if principal_recv is None:
            raise ValueError(
                f"GL account '{product.gl_principal_receivable_code}' not found"
            )
        interest_recv = await self._session.scalar(
            select(ChartOfAccount).where(
                ChartOfAccount.code == product.gl_interest_receivable_code
            )
        )
        if interest_recv is None:
            raise ValueError(
                f"GL account '{product.gl_interest_receivable_code}' not found"
            )
        interest_income = await self._session.scalar(
            select(ChartOfAccount).where(
                ChartOfAccount.code == product.gl_interest_income_code
            )
        )
        if interest_income is None:
            raise ValueError(
                f"GL account '{product.gl_interest_income_code}' not found"
            )

        # Resolve loan loss expense account (optional).
        loan_loss_id: uuid.UUID | None = None
        if product.gl_loan_loss_expense_code:
            loan_loss_acct = await self._session.scalar(
                select(ChartOfAccount).where(
                    ChartOfAccount.code == product.gl_loan_loss_expense_code
                )
            )
            if loan_loss_acct:
                loan_loss_id = loan_loss_acct.id

        # Resolve disbursement account ID.
        if application.disbursement_destination == "member_savings":
            raise ValueError(
                "member_savings disbursement requires a savings account — "
                "not supported in this version"
            )
        if application.disbursement_account_id is None:
            raise ValueError(
                "disbursement_account_id is required for 'cash' and 'internal_gl' destinations"
            )
        disbursement_account_id = application.disbursement_account_id

        # Step 4: Generate loan_reference from sequence.
        seq_val_result = await self._session.execute(
            text("SELECT nextval('loan_number_seq')")
        )
        seq_val = seq_val_result.scalar_one()
        disbursement_date = datetime.now(UTC)
        loan_reference = f"LN-{disbursement_date.strftime('%Y%m')}-{seq_val:06d}"

        # Step 5: Create loan row (status=disbursing).
        loan = Loan(
            loan_reference=loan_reference,
            loan_application_id=loan_application_id,
            loan_product_id=product.id,
            member_id=application.member_id,
            status="disbursing",
            principal_amount=principal,
            interest_method=product.interest_method,
            annual_interest_rate=product.annual_interest_rate,
            repayment_frequency=product.repayment_frequency,
            term_periods=term_periods,
            repayment_allocation=product.repayment_allocation,
            disbursement_destination=application.disbursement_destination,
            disbursement_account_id=application.disbursement_account_id,
            gl_principal_receivable_id=principal_recv.id,
            gl_interest_receivable_id=interest_recv.id,
            gl_interest_income_id=interest_income.id,
            gl_disbursement_account_id=disbursement_account_id,
            gl_loan_loss_expense_id=loan_loss_id,
            outstanding_principal=Decimal("0"),
            disbursed_by=actor_id,
            idempotency_key=idempotency_key,
        )
        self._session.add(loan)
        await self._session.flush()

        # Step 6: Compute amortisation schedule.
        schedule = compute_schedule(
            principal=principal,
            annual_interest_rate=product.annual_interest_rate,
            interest_method=product.interest_method,
            repayment_frequency=product.repayment_frequency,
            term_periods=term_periods,
            disbursement_date=disbursement_date.date(),
        )

        # Step 7: Post disbursement GL entry (principal).
        ledger_svc = LedgerService(self._session)
        await ledger_svc.post_journal_entry(
            reference=f"LOAN-DISB-{loan.id}",
            description=f"Loan disbursement: {loan_reference}",
            posted_by=actor_id,
            idempotency_key=f"loan-disb-{idempotency_key}",
            lines=[
                {
                    "account_id": principal_recv.id,
                    "debit_amount": principal,
                    "credit_amount": Decimal("0"),
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": loan.id,
                },
                {
                    "account_id": disbursement_account_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": principal,
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": loan.id,
                },
            ],
        )

        # Step 8: Write installments.
        first_due = schedule[0].due_date
        last_due = schedule[-1].due_date
        for inst in schedule:
            self._session.add(
                LoanInstallment(
                    loan_id=loan.id,
                    period_number=inst.period_number,
                    due_date=inst.due_date,
                    principal_due=inst.principal_due,
                    interest_due=inst.interest_due,
                    total_due=inst.total_due,
                )
            )

        # Step 9: Set snapshot.
        loan.outstanding_principal = principal
        loan.first_repayment_due = first_due
        loan.maturity_date = last_due

        # Step 10: Flat method — post interest booking GL entry at disbursement.
        if product.interest_method == "flat":
            total_interest = sum(i.interest_due for i in schedule)
            if total_interest > Decimal("0"):
                await ledger_svc.post_journal_entry(
                    reference=f"LOAN-INT-BOOK-{loan.id}",
                    description=f"Flat interest booking: {loan_reference}",
                    posted_by=actor_id,
                    idempotency_key=f"loan-int-book-{idempotency_key}",
                    lines=[
                        {
                            "account_id": interest_recv.id,
                            "debit_amount": total_interest,
                            "credit_amount": Decimal("0"),
                            "sub_ledger_type": "loan",
                            "sub_ledger_id": loan.id,
                        },
                        {
                            "account_id": interest_income.id,
                            "debit_amount": Decimal("0"),
                            "credit_amount": total_interest,
                            "sub_ledger_type": "loan",
                            "sub_ledger_id": loan.id,
                        },
                    ],
                )

        # Step 11: Finalize.
        loan.status = "disbursed"
        loan.disbursed_at = disbursement_date
        application.status = "disbursed"
        await self._session.flush()

        _log.info(
            "credit.loan.disbursed",
            loan_id=str(loan.id),
            loan_reference=loan_reference,
            principal=str(principal),
            destination=application.disbursement_destination,
        )
        return loan
