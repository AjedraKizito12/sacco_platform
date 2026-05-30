# Sub-plan 04 — Disbursement

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Implement `LoanDisbursementService.disburse()` — the operation that turns an
approved application into an active loan. Adds `record_external_credit` and
`record_external_debit` to `SavingsService`. Writes `loan_installments` rows from the
pre-computed schedule. Posts the disbursement GL entry (and flat-interest GL entry).
Generates human-readable `loan_reference` from `loan_number_seq`.

**Architecture:** All steps (lock → create loan → compute schedule → resolve GL accounts
→ post GL → write installments → set snapshot → optional flat-interest GL → optional
`record_external_credit` → status=disbursed) run inside one DB transaction. The
`loan_number_seq` sequence produces a monotonically increasing number that is formatted
into `LN-{YYYYMM}-{seq:06d}`. All journal lines carry `sub_ledger_type='loan'`.

**Tech Stack:** SQLAlchemy 2.0 async, `SELECT ... FOR UPDATE`, `nextval()` sequence call,
Pydantic v2, pytest-asyncio

---

## Required Reading

Before starting, read these files in full:

- Sub-plans 01, 02, 03, 05 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §6 (Disbursement), §2.2 (Single-writer)
- `app/modules/savings/service.py` — `system_credit` (lines 459–528) — pattern for `record_external_credit`
- `app/modules/ledger/service.py` — `post_journal_entry` signature
- `tests/modules/savings/test_service.py` lines 64–80 — `_setup_gl_accounts` helper pattern

---

## File Map

```
New
  app/modules/credit/services/disbursement.py   LoanDisbursementService

Modified
  app/modules/savings/service.py                add record_external_credit, record_external_debit
  app/modules/credit/schemas.py                 append DisbursementOut
  app/modules/credit/api.py                     append disburse endpoint
  tests/modules/credit/test_service.py          append disbursement tests
```

---

## Task 1 — `SavingsService.record_external_credit` and `record_external_debit`

These two methods write a `SavingsTransaction` row with `transaction_type=EXTERNAL_CREDIT`
(or `EXTERNAL_DEBIT`) referencing a journal entry that was **already posted** by the
calling module. They do NOT post a new GL entry. They mirror the `system_credit` /
`system_debit` pattern but skip the GL step.

**Files:**
- Modify: `app/modules/savings/service.py`

- [ ] **Step 1: Append `record_external_credit` and `record_external_debit` to `SavingsService`**

Add these two methods to the end of the `SavingsService` class (after `system_credit`):

```python
    async def record_external_credit(
        self,
        *,
        savings_account_id: uuid.UUID,
        amount: Decimal,
        journal_entry_id: uuid.UUID,
        source_module: str,
        source_id: uuid.UUID,
        narration: str | None = None,
        idempotency_key: str,
    ) -> SavingsTransaction:
        """Record a credit to a savings account made by an external module.

        The GL entry has ALREADY been posted by the calling module (e.g. credit).
        This method only writes the savings_transactions statement row.
        NOT callable from API routes.
        """
        existing = await self._session.scalar(
            select(SavingsTransaction).where(
                SavingsTransaction.idempotency_key == idempotency_key,
                SavingsTransaction.savings_account_id == savings_account_id,
            )
        )
        if existing is not None:
            _log.info(
                "savings.record_external_credit.idempotent_hit",
                idempotency_key=idempotency_key,
            )
            return existing

        await self.get_account(savings_account_id)  # existence check

        txn = SavingsTransaction(
            savings_account_id=savings_account_id,
            transaction_type="EXTERNAL_CREDIT",
            amount=amount,
            narration=narration,
            journal_entry_id=journal_entry_id,
            posted_by=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            idempotency_key=idempotency_key,
            source_module=source_module,
            source_id=source_id,
            reason="EXTERNAL_CREDIT",
        )
        self._session.add(txn)
        await self._session.flush()
        _log.info(
            "savings.external_credit_recorded",
            savings_account_id=str(savings_account_id),
            amount=str(amount),
            source_module=source_module,
        )
        return txn

    async def record_external_debit(
        self,
        *,
        savings_account_id: uuid.UUID,
        amount: Decimal,
        journal_entry_id: uuid.UUID,
        source_module: str,
        source_id: uuid.UUID,
        narration: str | None = None,
        idempotency_key: str,
    ) -> SavingsTransaction:
        """Record a debit from a savings account made by an external module.

        The GL entry has ALREADY been posted by the calling module (e.g. credit).
        This method only writes the savings_transactions statement row.
        NOT callable from API routes.
        """
        existing = await self._session.scalar(
            select(SavingsTransaction).where(
                SavingsTransaction.idempotency_key == idempotency_key,
                SavingsTransaction.savings_account_id == savings_account_id,
            )
        )
        if existing is not None:
            _log.info(
                "savings.record_external_debit.idempotent_hit",
                idempotency_key=idempotency_key,
            )
            return existing

        await self.get_account(savings_account_id)  # existence check

        txn = SavingsTransaction(
            savings_account_id=savings_account_id,
            transaction_type="EXTERNAL_DEBIT",
            amount=amount,
            narration=narration,
            journal_entry_id=journal_entry_id,
            posted_by=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            idempotency_key=idempotency_key,
            source_module=source_module,
            source_id=source_id,
            reason="EXTERNAL_DEBIT",
        )
        self._session.add(txn)
        await self._session.flush()
        _log.info(
            "savings.external_debit_recorded",
            savings_account_id=str(savings_account_id),
            amount=str(amount),
            source_module=source_module,
        )
        return txn
```

- [ ] **Step 2: Verify savings tests still pass**

```bash
pytest tests/modules/savings/ -v
```

Expected: all existing tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/modules/savings/service.py
git commit -m "feat(savings): record_external_credit and record_external_debit methods"
```

---

## Task 2 — `LoanDisbursementService.disburse` (TDD)

**Files:**
- Modify: `tests/modules/credit/test_service.py`
- Create: `app/modules/credit/services/disbursement.py`

- [ ] **Step 1: Append failing disbursement tests to `tests/modules/credit/test_service.py`**

Add these imports at the top of the test file (after existing imports):

```python
from sqlalchemy import select as sa_select
from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.ledger.service import LedgerService
from app.modules.members.models import Member
from app.modules.members.service import MemberService
from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction
from app.modules.savings.service import SavingsService
from app.modules.credit.services.application import LoanApplicationService
from app.modules.credit.services.disbursement import LoanDisbursementService
from app.modules.credit.models import Loan, LoanInstallment
```

Update the `_cleanup` function to also delete GL entities added by disbursement tests:

```python
async def _cleanup(engine: AsyncEngine) -> None:
    """Delete all credit + savings + GL rows in dependency order."""
    async with _factory(engine)() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(delete(LoanRepayment))
        await session.execute(delete(LoanInstallment))
        await session.execute(delete(Loan))
        await session.execute(delete(LoanApplication))
        await session.execute(delete(LoanProduct))
        await session.execute(delete(SavingsTransaction))
        await session.execute(delete(SavingsAccount))
        await session.execute(delete(SavingsProduct))
        await session.execute(delete(JournalLine))
        await session.execute(delete(JournalEntry))
        await session.execute(delete(ChartOfAccount))
        await session.execute(delete(Member))
        await session.commit()
```

Add the helper for disbursement test setup:

```python
async def _setup_disbursement_accounts(engine: AsyncEngine) -> dict:
    """Create GL accounts and savings product needed for disbursement tests.

    Returns dict with account IDs and product for use in tests.
    """
    session = await _new_session(engine)
    try:
        actor = uuid.uuid4()
        ledger = LedgerService(session)
        # GL accounts
        principal_recv = await ledger.create_account(
            code="1300", name="Loans Receivable", account_type="asset", created_by=actor
        )
        interest_recv = await ledger.create_account(
            code="1310", name="Interest Receivable", account_type="asset", created_by=actor
        )
        interest_income = await ledger.create_account(
            code="4100", name="Interest Income", account_type="income", created_by=actor
        )
        cash_account = await ledger.create_account(
            code="1020", name="Cash", account_type="asset", created_by=actor
        )
        savings_liability = await ledger.create_account(
            code="2010", name="Member Savings Liability", account_type="liability", created_by=actor
        )
        loan_loss = await ledger.create_account(
            code="5100", name="Loan Loss Expense", account_type="expense", created_by=actor
        )
        # Savings product (for member_savings destination tests)
        savings_product = SavingsProduct(
            name="Standard Savings",
            interest_rate=Decimal("5"),
            minimum_balance=Decimal("0"),
            liability_account_id=savings_liability.id,
        )
        session.add(savings_product)
        await session.flush()
        await session.commit()
        return {
            "actor": actor,
            "principal_recv_id": principal_recv.id,
            "principal_recv_code": "1300",
            "interest_recv_id": interest_recv.id,
            "interest_recv_code": "1310",
            "interest_income_id": interest_income.id,
            "interest_income_code": "4100",
            "cash_account_id": cash_account.id,
            "cash_account_code": "1020",
            "savings_liability_id": savings_liability.id,
            "savings_liability_code": "2010",
            "loan_loss_id": loan_loss.id,
            "loan_loss_code": "5100",
            "savings_product_id": savings_product.id,
        }
    finally:
        await session.close()


async def _make_approved_application(
    engine: AsyncEngine,
    accounts: dict,
    interest_method: str = "flat",
) -> tuple[LoanApplication, LoanProduct]:
    """Create a product + submit + approve an application. Returns (application, product)."""
    # Product with GL codes matching the accounts dict
    product = await _make_product(
        engine,
        name=f"Disburse Test {interest_method}",
        interest_method=interest_method,
        gl_principal_receivable_code=accounts["principal_recv_code"],
        gl_interest_receivable_code=accounts["interest_recv_code"],
        gl_interest_income_code=accounts["interest_income_code"],
        gl_loan_loss_expense_code=accounts["loan_loss_code"],
        disbursement_destinations=["cash", "member_savings"],
        required_approvals=1,
    )

    submitter = uuid.uuid4()
    approver = uuid.uuid4()

    session = await _new_session(engine)
    try:
        app_svc = LoanApplicationService(session)
        approval_svc = ApprovalService(session)
        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("120000"),
            requested_term_periods=12,
            disbursement_destination="cash",
            disbursement_account_id=accounts["cash_account_id"],
            submitted_by=submitter,
            idempotency_key=f"app-{uuid.uuid4()}",
        )
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=approver,
        )
        await session.commit()
        return application, product
    finally:
        await session.close()
```

Now append the tests:

```python
@pytest.mark.asyncio
async def test_disburse_cash_destination_creates_loan(test_engine):
    accounts = await _setup_disbursement_accounts(test_engine)
    application, product = await _make_approved_application(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=f"disb-{uuid.uuid4()}",
        )
        await session.commit()

        assert loan.id is not None
        assert loan.status == "disbursed"
        assert loan.outstanding_principal == Decimal("120000")
        assert loan.loan_reference.startswith("LN-")
        assert len(loan.loan_reference) == len("LN-202601-000001")
        assert loan.disbursed_at is not None
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_disburse_creates_installments(test_engine):
    accounts = await _setup_disbursement_accounts(test_engine)
    application, product = await _make_approved_application(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=f"disb-inst-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        installments = list(
            (await session2.execute(
                sa_select(LoanInstallment).where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
            )).scalars().all()
        )
        assert len(installments) == 12
        assert installments[0].period_number == 1
        total_principal = sum(i.principal_due for i in installments)
        assert abs(total_principal - Decimal("120000")) <= Decimal("1")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_disburse_gl_entry_balanced(test_engine):
    accounts = await _setup_disbursement_accounts(test_engine)
    application, product = await _make_approved_application(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=f"disb-gl-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        # Fetch all GL lines tagged sub_ledger_id=loan.id
        from app.modules.ledger.models import JournalLine
        lines = list(
            (await session2.execute(
                sa_select(JournalLine).where(JournalLine.sub_ledger_id == loan.id)
            )).scalars().all()
        )
        assert len(lines) >= 2
        total_dr = sum(ln.debit_amount for ln in lines)
        total_cr = sum(ln.credit_amount for ln in lines)
        assert total_dr == total_cr
        for ln in lines:
            assert ln.sub_ledger_type == "loan"
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_disburse_flat_posts_interest_gl(test_engine):
    """Flat method: second GL entry Dr interest_receivable / Cr interest_income."""
    accounts = await _setup_disbursement_accounts(test_engine)
    application, product = await _make_approved_application(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=f"disb-flat-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        lines = list(
            (await session2.execute(
                sa_select(JournalLine).where(
                    JournalLine.sub_ledger_id == loan.id,
                    JournalLine.account_id == accounts["interest_recv_id"],
                )
            )).scalars().all()
        )
        # Interest receivable line should have a debit amount > 0
        assert any(ln.debit_amount > 0 for ln in lines)
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_disburse_idempotency(test_engine):
    """Same idempotency_key → returns same loan, exactly one GL entry."""
    accounts = await _setup_disbursement_accounts(test_engine)
    application, product = await _make_approved_application(test_engine, accounts, "flat")

    idem_key = f"disb-idem-{uuid.uuid4()}"
    session = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session)
        loan1 = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=idem_key,
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanDisbursementService(session2)
        loan2 = await svc2.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=idem_key,
        )
        assert loan2.id == loan1.id
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_disburse_non_approved_raises(test_engine):
    accounts = await _setup_disbursement_accounts(test_engine)
    product = await _make_product(
        test_engine,
        gl_principal_receivable_code=accounts["principal_recv_code"],
        gl_interest_receivable_code=accounts["interest_recv_code"],
        gl_interest_income_code=accounts["interest_income_code"],
    )
    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)
        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="cash",
            disbursement_account_id=accounts["cash_account_id"],
            submitted_by=uuid.uuid4(),
            idempotency_key=f"not-approved-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session2)
        with pytest.raises(ValueError, match="[Aa]pproved|status"):
            await svc.disburse(
                loan_application_id=application.id,
                actor_id=accounts["actor"],
                idempotency_key=f"nonapproved-disb-{uuid.uuid4()}",
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_service.py -k "disburse" -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.modules.credit.services.disbursement'`

- [ ] **Step 3: Create `app/modules/credit/services/disbursement.py`**

```python
# app/modules/credit/services/disbursement.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select, text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanApplication, LoanInstallment
from app.modules.credit.services._schedule import compute_schedule
from app.modules.ledger.models import ChartOfAccount

_log = structlog.get_logger(__name__)
_SYSTEM_ACTOR = uuid.UUID("00000000-0000-0000-0000-000000000000")


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
        """Disburse an approved loan application. All steps in one transaction.

        Steps (per spec §6.1):
          1. SELECT loan_application FOR UPDATE — verify status=approved
          2. Idempotency guard — return existing loan if key already used
          3. Create loan record (status=disbursing)
          4. Compute amortisation schedule
          5. Resolve GL account IDs from codes
          6. Post disbursement GL entry
          7. Write loan_installments rows
          8. Set loan.outstanding_principal = principal_amount
          9. If flat: post interest booking GL entry
         10. If member_savings: call SavingsService.record_external_credit
         11. Set loan.status = disbursed
        """
        from app.modules.ledger.service import LedgerService

        # Step 1: Lock application row.
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

        # Step 2: Idempotency guard.
        existing_loan = await self._session.scalar(
            select(Loan).where(Loan.idempotency_key == idempotency_key)
        )
        if existing_loan is not None:
            _log.info(
                "credit.disburse.idempotent_hit", idempotency_key=idempotency_key
            )
            return existing_loan

        # Fetch product for terms.
        from app.modules.credit.models import LoanProduct

        product = await self._session.get(LoanProduct, application.loan_product_id)
        if product is None:
            raise ValueError(f"LoanProduct '{application.loan_product_id}' not found")

        principal = application.approved_amount  # type: ignore[assignment]
        term_periods = application.approved_term_periods  # type: ignore[assignment]

        # Step 3: Resolve GL account IDs.
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

        # Resolve disbursement account.
        disbursement_account_id: uuid.UUID
        if application.disbursement_destination == "member_savings":
            # Resolve via savings product liability account.
            from app.modules.savings.service import SavingsService

            savings_svc = SavingsService(self._session)
            savings_account = await savings_svc.get_primary_account_for_member(
                application.member_id
            )
            if savings_account is None:
                raise ValueError(
                    f"No savings account found for member '{application.member_id}'"
                )
            disbursement_account_id = savings_account.liability_account_id
        else:
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
        loan_reference = (
            f"LN-{disbursement_date.strftime('%Y%m')}-{seq_val:06d}"
        )

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

        # Step 11: member_savings destination — write savings statement row.
        if application.disbursement_destination == "member_savings":
            from app.modules.savings.service import SavingsService

            savings_svc = SavingsService(self._session)
            savings_account = await savings_svc.get_primary_account_for_member(
                application.member_id
            )
            if savings_account is not None:
                # Fetch the disbursement GL entry to reference it.
                disb_entry = await self._session.scalar(
                    select(
                        __import__(
                            "app.modules.ledger.models",
                            fromlist=["JournalEntry"],
                        ).JournalEntry
                    ).where(
                        __import__(
                            "app.modules.ledger.models",
                            fromlist=["JournalEntry"],
                        ).JournalEntry.idempotency_key
                        == f"loan-disb-{idempotency_key}"
                    )
                )
                if disb_entry is not None:
                    await savings_svc.record_external_credit(
                        savings_account_id=savings_account.id,
                        amount=principal,
                        journal_entry_id=disb_entry.id,
                        source_module="credit",
                        source_id=loan.id,
                        narration=f"Loan disbursement: {loan_reference}",
                        idempotency_key=f"loan-disb-savtx-{idempotency_key}",
                    )

        # Step 12: Finalize.
        loan.status = "disbursed"
        loan.disbursed_at = disbursement_date
        application.status = "disbursed" if hasattr(application, "disbursed") else application.status
        await self._session.flush()

        _log.info(
            "credit.loan.disbursed",
            loan_id=str(loan.id),
            loan_reference=loan_reference,
            principal=str(principal),
            destination=application.disbursement_destination,
        )
        return loan
```

> **Note on the `member_savings` GL entry fetch:** The nested `__import__` for
> `JournalEntry` avoids a circular import at module load time. In practice this is
> cleaner with a local import:
>
> ```python
> from app.modules.ledger.models import JournalEntry as _JE
> disb_entry = await self._session.scalar(
>     select(_JE).where(_JE.idempotency_key == f"loan-disb-{idempotency_key}")
> )
> ```
>
> Use the local import form — replace the `__import__` block with this cleaner version.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/modules/credit/test_service.py -k "disburse" -v
```

Expected: all 6 disbursement tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/services/disbursement.py tests/modules/credit/test_service.py
git commit -m "feat(credit): LoanDisbursementService.disburse — GL, installments, flat-interest booking"
```

---

## Task 3 — Disbursement Schema and API Endpoint

**Files:**
- Modify: `app/modules/credit/schemas.py`
- Modify: `app/modules/credit/api.py`

- [ ] **Step 1: Append disbursement schemas to `app/modules/credit/schemas.py`**

```python
# ── Loans ─────────────────────────────────────────────────────────────────────


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    loan_reference: str
    loan_application_id: uuid.UUID
    loan_product_id: uuid.UUID
    member_id: uuid.UUID
    status: str
    principal_amount: Decimal
    interest_method: str
    annual_interest_rate: Decimal
    repayment_frequency: str
    term_periods: int
    repayment_allocation: str
    disbursement_destination: str
    outstanding_principal: Decimal
    accrued_interest: Decimal
    accrued_penalties: Decimal
    total_paid_principal: Decimal
    total_paid_interest: Decimal
    total_paid_penalties: Decimal
    total_written_off: Decimal
    last_repayment_at: datetime | None
    last_repayment_amount: Decimal | None
    disbursed_at: datetime | None
    first_repayment_due: date | None
    maturity_date: date | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DisburseIn(BaseModel):
    idempotency_key: str
```

Also add `date` to the imports at the top of `schemas.py`:

```python
from datetime import date, datetime
```

- [ ] **Step 2: Append disburse endpoint to `app/modules/credit/api.py`**

Add import at top:

```python
from app.modules.credit.schemas import (
    DisburseIn,
    LoanOut,
    ...  # existing imports
)
from app.modules.credit.services.disbursement import LoanDisbursementService
```

Append endpoint:

```python
# ── Loans ─────────────────────────────────────────────────────────────────────


@router.post(
    "/loans/{application_id}/disburse",
    response_model=LoanOut,
    status_code=201,
)
async def disburse_loan(
    application_id: uuid.UUID,
    body: DisburseIn,
    session: Session,
) -> LoanOut:
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application_id,
            actor_id=uuid.uuid4(),  # TODO: replace with CurrentTenantUser in sub-plan 12
            idempotency_key=body.idempotency_key,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return LoanOut.model_validate(loan)


@router.get("/loans/{loan_id}", response_model=LoanOut)
async def get_loan(loan_id: uuid.UUID, session: Session) -> LoanOut:
    from app.modules.credit.models import Loan as _Loan

    loan = await session.get(_Loan, loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail=f"Loan '{loan_id}' not found")
    return LoanOut.model_validate(loan)
```

- [ ] **Step 3: Verify API imports**

```bash
python -c "from app.modules.credit.api import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/modules/credit/schemas.py app/modules/credit/api.py
git commit -m "feat(credit): LoanOut schema + disburse + get loan API endpoints"
```

---

## Verification Criteria

```bash
# 1. Disbursement tests pass
pytest tests/modules/credit/test_service.py -k "disburse" -v

# 2. Savings tests unaffected
pytest tests/modules/savings/ -v

# 3. Full suite — no regressions
pytest -x -q
```

All commands must exit 0. Confirm:
- `loan.status == 'disbursed'`, `outstanding_principal == approved_amount`
- `loan_reference` matches `LN-{YYYYMM}-{6-digit seq}`
- 12 `loan_installments` rows created, `SUM(principal_due) == 120000 ± 1`
- GL lines all tagged `sub_ledger_type='loan'`, debits == credits
- Flat method: interest receivable debit line exists
- Same idempotency_key → same loan returned, no duplicate GL entries
- Non-approved application → `ValueError`
