# Sub-plan 07 — Repayment

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Implement `LoanRepaymentService.apply_repayment` — interest-first allocation,
installment updates, GL posting, closure detection — and expose it via the repayment API
endpoint. Add GET `/credit/loans/{id}/schedule` endpoint.

**Architecture:** Single-writer discipline: SELECT loan FOR UPDATE → allocate →
`LedgerService.post_journal_entry` → UPDATE loan snapshot → write `LoanRepayment` row →
`record_external_debit` (savings source) → commit. All in one transaction.

**Tech Stack:** SQLAlchemy 2.0 async, LedgerService, SavingsService

---

## Required Reading

- Sub-plans 01, 04, 05, 06 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §7 (Repayment), §7.2 (GL entry)
- `app/modules/credit/services/disbursement.py` — single-writer pattern
- `app/modules/savings/service.py` — `record_external_debit` (added in sub-plan 04)

---

## File Map

```
New
  app/modules/credit/services/repayment.py   LoanRepaymentService

Modified
  app/modules/credit/schemas.py               LoanRepaymentOut, LoanRepaymentCreateIn
  app/modules/credit/api.py                   repayment + schedule endpoints
  tests/modules/credit/test_service.py        append repayment tests
```

---

## Task 1 — `LoanRepaymentService.apply_repayment` (TDD)

**Files:**
- Modify: `tests/modules/credit/test_service.py`
- Create: `app/modules/credit/services/repayment.py`

- [ ] **Step 1: Append failing repayment tests to `tests/modules/credit/test_service.py`**

Add import at top (alongside existing imports):

```python
from app.modules.credit.services.repayment import LoanRepaymentService
```

Append tests:

```python
# ── Repayment tests ───────────────────────────────────────────────────────────


async def _make_disbursed_loan_with_interest(
    engine: AsyncEngine,
    accounts: dict,
) -> tuple[Loan, Decimal]:
    """Disburse a reducing_balance loan, run one accrual cycle, return (loan, accrued_interest)."""
    loan = await _make_disbursed_loan(engine, accounts, "reducing_balance")

    # Backdate first installment so accrual fires.
    today = date.today()
    session = await _new_session(engine)
    try:
        installment = (
            await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalars().first()
        installment.due_date = today
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _accrue_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session2 = await _new_session(engine)
    try:
        refreshed = await session2.get(Loan, loan.id)
        return refreshed, refreshed.accrued_interest
    finally:
        await session2.close()


@pytest.mark.asyncio
async def test_repayment_interest_first_allocation(test_engine):
    """Interest cleared before principal; snapshot and installment updated."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)
    assert accrued_interest > Decimal("0"), "Precondition: loan must have accrued interest"

    principal_before = loan.outstanding_principal
    repayment_amount = accrued_interest + Decimal("100.00")  # more than just interest

    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        repayment = await svc.apply_repayment(
            loan_id=loan.id,
            amount=repayment_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    assert repayment.interest_applied == accrued_interest
    assert repayment.principal_applied == Decimal("100.00")
    assert repayment.overpayment == Decimal("0")

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.accrued_interest == Decimal("0")
        assert updated.outstanding_principal == principal_before - Decimal("100.00")
        assert updated.total_paid_interest == accrued_interest
        assert updated.total_paid_principal == Decimal("100.00")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_exact_payoff_closes_loan(test_engine):
    """Repayment = outstanding_principal + accrued_interest → loan.status = 'closed'."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    payoff_amount = loan.outstanding_principal + accrued_interest

    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        repayment = await svc.apply_repayment(
            loan_id=loan.id,
            amount=payoff_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.status == "closed"
        assert updated.closed_at is not None
        assert updated.outstanding_principal == Decimal("0")
        assert updated.accrued_interest == Decimal("0")
        assert repayment.overpayment == Decimal("0")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_overpayment(test_engine):
    """Repayment > total owed → overpayment > 0, loan closed."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    total_owed = loan.outstanding_principal + accrued_interest
    overpay_amount = total_owed + Decimal("50.00")

    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        repayment = await svc.apply_repayment(
            loan_id=loan.id,
            amount=overpay_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    assert repayment.overpayment == Decimal("50.00")

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.status == "closed"
        assert updated.outstanding_principal == Decimal("0")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_gl_balanced(test_engine):
    """GL entry for repayment is balanced (sum debits == sum credits)."""
    from app.modules.ledger.models import JournalEntry, JournalLine
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    repayment_amount = accrued_interest + Decimal("50.00")

    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        repayment = await svc.apply_repayment(
            loan_id=loan.id,
            amount=repayment_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
        repayment_id = repayment.id
        journal_entry_id = repayment.journal_entry_id
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        lines = list(
            (await session2.execute(
                sa_select(JournalLine).where(JournalLine.journal_entry_id == journal_entry_id)
            )).scalars().all()
        )
        total_debit = sum(l.debit_amount for l in lines)
        total_credit = sum(l.credit_amount for l in lines)
        assert total_debit == total_credit

        # All lines tagged sub_ledger_type='loan'
        for line in lines:
            assert line.sub_ledger_type == "loan"
            assert line.sub_ledger_id == loan.id
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_idempotency(test_engine):
    """Repayment with same idempotency_key twice → second call returns existing, one GL entry."""
    from app.modules.ledger.models import JournalEntry
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    idem_key = f"rpy-idem-{uuid.uuid4()}"

    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        r1 = await svc.apply_repayment(
            loan_id=loan.id,
            amount=Decimal("100.00"),
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=idem_key,
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanRepaymentService(session2)
        r2 = await svc2.apply_repayment(
            loan_id=loan.id,
            amount=Decimal("100.00"),
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=idem_key,
        )
        await session2.commit()
    finally:
        await session2.close()

    assert r1.id == r2.id

    # Verify only one GL entry
    session3 = await _new_session(test_engine)
    try:
        count = await session3.scalar(
            sa_select(func.count()).select_from(JournalEntry).where(
                JournalEntry.idempotency_key == f"loan-rpy-{idem_key}"
            )
        )
        assert count == 1
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_on_closed_loan_raises(test_engine):
    """Repayment on a closed loan raises ValueError."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    # Close the loan by full payoff
    payoff_amount = loan.outstanding_principal + accrued_interest
    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        await svc.apply_repayment(
            loan_id=loan.id,
            amount=payoff_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    # Now try a second repayment
    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanRepaymentService(session2)
        with pytest.raises(ValueError, match="closed"):
            await svc2.apply_repayment(
                loan_id=loan.id,
                amount=Decimal("10.00"),
                payment_account_id=accounts["disbursement_account"],
                posted_by=accounts["actor"],
                idempotency_key=f"rpy-{uuid.uuid4()}",
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_updates_installments(test_engine):
    """Repayment payment marks oldest pending installments as paid/partial."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    # Pay off the first installment fully (interest + principal_due)
    session = await _new_session(test_engine)
    try:
        installment = (
            await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalars().first()
        installment_total = installment.total_due
    finally:
        await session.close()

    payment_amount = accrued_interest + installment_total

    session2 = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session2)
        await svc.apply_repayment(
            loan_id=loan.id,
            amount=payment_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session2.commit()
    finally:
        await session2.close()

    session3 = await _new_session(test_engine)
    try:
        first_installment = (
            await session3.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalars().first()
        # First installment should be fully paid
        assert first_installment.status == "paid"
        assert first_installment.paid_at is not None
    finally:
        await session3.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_service.py -k "repayment" -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.modules.credit.services.repayment'`

- [ ] **Step 3: Create `app/modules/credit/services/repayment.py`**

```python
# app/modules/credit/services/repayment.py
"""Loan repayment allocation and posting."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanInstallment, LoanRepayment

_log = structlog.get_logger(__name__)


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
        """Apply a repayment to a loan with interest-first allocation.

        Args:
            loan_id: The loan to repay.
            amount: Total cash received.
            payment_account_id: GL account cash was received into (Dr side).
            posted_by: Actor performing the repayment.
            narration: Optional free-text note.
            idempotency_key: Caller-supplied deduplication key.
            savings_account_id: If set, call record_external_debit on this savings account.

        Returns:
            LoanRepayment row (committed by caller).
        """
        from app.modules.ledger.service import LedgerService

        idem_key = f"loan-rpy-{idempotency_key}"

        # Idempotency guard — return existing if already processed.
        existing = await self._session.scalar(
            select(LoanRepayment).where(LoanRepayment.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

        # Lock loan row to serialise concurrent repayments.
        loan = await self._session.scalar(
            select(Loan).where(Loan.id == loan_id).with_for_update()
        )
        if loan is None:
            raise ValueError(f"Loan {loan_id} not found")
        if loan.status in ("closed", "written_off", "disbursing"):
            raise ValueError(f"Cannot apply repayment to loan in status '{loan.status}'")

        # ── Interest-first allocation ────────────────────────────────────────
        remaining = amount
        interest_applied = min(remaining, loan.accrued_interest)
        remaining -= interest_applied

        principal_applied = min(remaining, loan.outstanding_principal)
        remaining -= principal_applied

        penalties_applied = min(remaining, loan.accrued_penalties)
        remaining -= penalties_applied

        overpayment = remaining

        # ── GL entry ─────────────────────────────────────────────────────────
        lines: list[dict] = [
            {
                "account_id": payment_account_id,
                "debit_amount": amount,
                "credit_amount": Decimal("0"),
                "sub_ledger_type": "loan",
                "sub_ledger_id": loan.id,
            },
        ]
        if principal_applied > Decimal("0"):
            lines.append(
                {
                    "account_id": loan.gl_principal_receivable_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": principal_applied,
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": loan.id,
                }
            )
        if interest_applied > Decimal("0"):
            lines.append(
                {
                    "account_id": loan.gl_interest_receivable_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": interest_applied,
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": loan.id,
                }
            )
        if penalties_applied > Decimal("0"):
            penalty_gl_id = await self._resolve_penalty_gl_account(loan)
            if penalty_gl_id:
                lines.append(
                    {
                        "account_id": penalty_gl_id,
                        "debit_amount": Decimal("0"),
                        "credit_amount": penalties_applied,
                        "sub_ledger_type": "loan",
                        "sub_ledger_id": loan.id,
                    }
                )

        # Ensure GL balances: debit = sum of all credits.
        total_credits = principal_applied + interest_applied + penalties_applied
        if total_credits < amount:
            # Overpayment: debit must equal credits only (no phantom credit line).
            # Reduce debit line to match credits (overpayment goes to payment account already received).
            # The overpayment is recorded in the LoanRepayment row but not as a GL line.
            # Debit line already set to full amount — correct: cash in = amount received.
            # Credits = total_credits (may be < amount). This would unbalance.
            # Fix: DR payment_account = total_credits (we only recognize what's applied).
            lines[0]["debit_amount"] = total_credits

        ledger_svc = LedgerService(self._session)
        journal_entry = await ledger_svc.post_journal_entry(
            reference=f"LOAN-RPY-{loan.loan_reference}",
            description=narration or f"Repayment: {loan.loan_reference}",
            posted_by=posted_by,
            idempotency_key=idem_key,
            lines=lines,
        )

        # ── Snapshot update ───────────────────────────────────────────────────
        loan.accrued_interest = loan.accrued_interest - interest_applied
        loan.accrued_penalties = loan.accrued_penalties - penalties_applied
        loan.outstanding_principal = loan.outstanding_principal - principal_applied
        loan.total_paid_interest = loan.total_paid_interest + interest_applied
        loan.total_paid_principal = loan.total_paid_principal + principal_applied
        loan.total_paid_penalties = loan.total_paid_penalties + penalties_applied
        loan.last_repayment_at = datetime.now(UTC)
        loan.last_repayment_amount = amount

        # ── Write LoanRepayment row ───────────────────────────────────────────
        repayment = LoanRepayment(
            loan_id=loan.id,
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

        # ── Update installments (oldest first) ────────────────────────────────
        await self._update_installments(loan, principal_applied, interest_applied)

        # ── Loan closure detection ────────────────────────────────────────────
        if (
            loan.outstanding_principal <= Decimal("0")
            and loan.accrued_interest <= Decimal("0")
            and loan.accrued_penalties <= Decimal("0")
        ):
            loan.status = "closed"
            loan.closed_at = datetime.now(UTC)

        # ── Savings external debit ────────────────────────────────────────────
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
                idempotency_key=f"savings-rpy-{idempotency_key}",
            )

        # ── Publish outbox event ──────────────────────────────────────────────
        from app.core.outbox.publisher import EventPublisher
        publisher = EventPublisher(self._session)
        event_payload: dict = {
            "loan_id": str(loan.id),
            "repayment_id": str(repayment.id),
            "amount": str(amount),
            "outstanding_principal": str(loan.outstanding_principal),
        }
        await publisher.publish("LoanRepaymentPosted", event_payload)
        if loan.status == "closed":
            await publisher.publish("LoanClosed", {"loan_id": str(loan.id), "member_id": str(loan.member_id)})

        _log.info(
            "credit.repayment.applied",
            loan_id=str(loan.id),
            amount=str(amount),
            principal_applied=str(principal_applied),
            interest_applied=str(interest_applied),
        )
        return repayment

    async def _update_installments(
        self,
        loan: Loan,
        principal_applied: Decimal,
        interest_applied: Decimal,
    ) -> None:
        """Update installment rows: oldest unpaid/partial first."""
        from datetime import timezone

        installments = list(
            (
                await self._session.execute(
                    select(LoanInstallment)
                    .where(
                        LoanInstallment.loan_id == loan.id,
                        LoanInstallment.status.in_(["pending", "partial", "overdue"]),
                    )
                    .order_by(LoanInstallment.period_number)
                )
            ).scalars().all()
        )

        remaining_interest = interest_applied
        remaining_principal = principal_applied

        for inst in installments:
            if remaining_interest <= Decimal("0") and remaining_principal <= Decimal("0"):
                break

            interest_to_apply = min(remaining_interest, inst.interest_due - inst.interest_paid)
            principal_to_apply = min(remaining_principal, inst.principal_due - inst.principal_paid)

            inst.interest_paid = inst.interest_paid + interest_to_apply
            inst.principal_paid = inst.principal_paid + principal_to_apply
            remaining_interest -= interest_to_apply
            remaining_principal -= principal_to_apply

            interest_fully_paid = inst.interest_paid >= inst.interest_due
            principal_fully_paid = inst.principal_paid >= inst.principal_due

            if interest_fully_paid and principal_fully_paid:
                inst.status = "paid"
                inst.paid_at = datetime.now(UTC)
            else:
                inst.status = "partial"

    async def _resolve_penalty_gl_account(self, loan: Loan) -> uuid.UUID | None:
        """Look up the penalty GL account via the loan product's penalty_fee_type_code."""
        from app.modules.credit.models import LoanProduct
        from app.modules.fees.models import FeeType
        from app.modules.ledger.models import ChartOfAccount

        product = await self._session.get(LoanProduct, loan.loan_product_id)
        if product is None or not product.penalty_fee_type_code:
            return None

        fee_type = await self._session.scalar(
            select(FeeType).where(FeeType.code == product.penalty_fee_type_code)
        )
        if fee_type is None:
            return None

        account = await self._session.scalar(
            select(ChartOfAccount).where(ChartOfAccount.code == fee_type.gl_receivable_account_code)
        )
        return account.id if account else None

    async def list_repayments(self, loan_id: uuid.UUID) -> list[LoanRepayment]:
        return list(
            (
                await self._session.execute(
                    select(LoanRepayment)
                    .where(LoanRepayment.loan_id == loan_id)
                    .order_by(LoanRepayment.created_at)
                )
            ).scalars().all()
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/modules/credit/test_service.py -k "repayment" -v
```

Expected: all 7 repayment tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/services/repayment.py tests/modules/credit/test_service.py
git commit -m "feat(credit): LoanRepaymentService — interest-first allocation, GL posting, closure detection"
```

---

## Task 2 — Repayment and Schedule Schemas + API Endpoints

**Files:**
- Modify: `app/modules/credit/schemas.py`
- Modify: `app/modules/credit/api.py`

- [ ] **Step 1: Add repayment schemas to `app/modules/credit/schemas.py`**

```python
# ── Repayment schemas ─────────────────────────────────────────────────────────

class LoanRepaymentCreateIn(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    payment_account_id: uuid.UUID
    narration: str | None = None
    idempotency_key: str
    savings_account_id: uuid.UUID | None = None  # for EXTERNAL_DEBIT

    model_config = ConfigDict(from_attributes=True)


class LoanRepaymentOut(BaseModel):
    id: uuid.UUID
    loan_id: uuid.UUID
    amount: Decimal
    principal_applied: Decimal
    interest_applied: Decimal
    penalties_applied: Decimal
    overpayment: Decimal
    payment_account_id: uuid.UUID
    journal_entry_id: uuid.UUID
    posted_by: uuid.UUID
    narration: str | None
    idempotency_key: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Installment / schedule schemas ────────────────────────────────────────────

class LoanInstallmentOut(BaseModel):
    id: uuid.UUID
    loan_id: uuid.UUID
    period_number: int
    due_date: date
    principal_due: Decimal
    interest_due: Decimal
    total_due: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    status: str
    paid_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 2: Add repayment and schedule endpoints to `app/modules/credit/api.py`**

```python
# ── Repayment endpoints ───────────────────────────────────────────────────────

@router.post("/loans/{loan_id}/repayments", response_model=LoanRepaymentOut, status_code=201)
async def post_repayment(
    loan_id: uuid.UUID,
    body: LoanRepaymentCreateIn,
    session: AsyncSession = Depends(get_tenant_session),
    actor_id: uuid.UUID = Depends(get_actor_id),
) -> LoanRepaymentOut:
    svc = LoanRepaymentService(session)
    repayment = await svc.apply_repayment(
        loan_id=loan_id,
        amount=body.amount,
        payment_account_id=body.payment_account_id,
        posted_by=actor_id,
        narration=body.narration,
        idempotency_key=body.idempotency_key,
        savings_account_id=body.savings_account_id,
    )
    return LoanRepaymentOut.model_validate(repayment)


@router.get("/loans/{loan_id}/repayments", response_model=list[LoanRepaymentOut])
async def list_repayments(
    loan_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[LoanRepaymentOut]:
    svc = LoanRepaymentService(session)
    repayments = await svc.list_repayments(loan_id)
    return [LoanRepaymentOut.model_validate(r) for r in repayments]


# ── Schedule endpoint ─────────────────────────────────────────────────────────

@router.get("/loans/{loan_id}/schedule", response_model=list[LoanInstallmentOut])
async def get_schedule(
    loan_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[LoanInstallmentOut]:
    installments = list(
        (
            await session.execute(
                select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan_id)
                .order_by(LoanInstallment.period_number)
            )
        ).scalars().all()
    )
    return [LoanInstallmentOut.model_validate(i) for i in installments]
```

- [ ] **Step 3: Verify app imports**

```bash
python -c "from app.modules.credit.services.repayment import LoanRepaymentService; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/modules/credit/schemas.py app/modules/credit/api.py
git commit -m "feat(credit): repayment + schedule API endpoints"
```

---

## Verification Criteria

```bash
# 1. Repayment tests pass
pytest tests/modules/credit/test_service.py -k "repayment" -v

# 2. Full suite — no regressions
pytest -x -q
```

All commands must exit 0. Confirm:
- Interest cleared before principal when accrued_interest > 0
- Repayment = total owed → loan.status = 'closed', closed_at set
- Overpayment recorded in repayment row, loan closed
- GL balanced on all repayment entries
- All GL lines tagged `sub_ledger_type='loan'`
- Installment status updated to 'paid' when fully covered
- Same idempotency_key twice → same repayment row, one GL entry
- Repayment on closed loan raises ValueError
