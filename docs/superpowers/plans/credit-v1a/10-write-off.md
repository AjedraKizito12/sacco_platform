# Sub-plan 10 — Write-Off

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Implement `LoanWriteOffService` and the `credit.write_off` executor. Write-offs
below `write_off_threshold` execute directly; above the threshold they go through
maker-checker (quorum=2). GL: Dr loan_loss_expense / Cr gl_principal_receivable_id.

**Architecture:** Single-writer discipline applies. Direct path and executor path share
the same `_execute_write_off` private method to avoid duplication.

**Tech Stack:** SQLAlchemy 2.0 async, ApprovalService, @approval_executor

---

## Required Reading

- Sub-plans 01, 04, 07 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §9 (Write-Off)
- `app/modules/credit/executors.py` — existing `credit.approve_application` executor pattern
- `app/modules/maker_checker/service.py` — `ApprovalService.submit`, `approve`, `reject`

---

## File Map

```
New
  app/modules/credit/services/write_off.py

Modified
  app/modules/credit/executors.py           add credit.write_off executor
  app/modules/credit/schemas.py             WriteOffIn, WriteOffOut
  app/modules/credit/api.py                 write-off endpoint
  tests/modules/credit/test_service.py      append write-off tests
```

---

## Task 1 — `LoanWriteOffService` and `credit.write_off` Executor (TDD)

**Files:**
- Modify: `tests/modules/credit/test_service.py`
- Create: `app/modules/credit/services/write_off.py`
- Modify: `app/modules/credit/executors.py`

- [ ] **Step 1: Append failing write-off tests to `tests/modules/credit/test_service.py`**

Add import at top:

```python
from app.modules.credit.services.write_off import LoanWriteOffService
```

Append tests:

```python
# ── Write-off tests ───────────────────────────────────────────────────────────


async def _make_loan_below_threshold(engine, accounts) -> Loan:
    """Disburse a loan with write_off_threshold=0 (threshold below any amount)."""
    # The default loan product created by _make_approved_application has write_off_threshold=0.
    loan = await _make_disbursed_loan(engine, accounts, "reducing_balance")
    return loan


@pytest.mark.asyncio
async def test_write_off_below_threshold_direct(test_engine):
    """Write-off amount <= threshold → direct execution, no approval_request, status=written_off."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    # Product write_off_threshold defaults to 0; set it high so our amount is below threshold.
    # Update product to set write_off_threshold = 999999 so any write-off is direct.
    session = await _new_session(test_engine)
    try:
        from app.modules.credit.models import LoanProduct
        product = await session.get(LoanProduct, loan.loan_product_id)
        product.write_off_threshold = Decimal("999999.00")
        await session.commit()
    finally:
        await session.close()

    write_off_amount = loan.outstanding_principal  # full write-off

    session2 = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session2)
        result = await svc.write_off(
            loan_id=loan.id,
            amount=write_off_amount,
            reason="Non-recoverable debt",
            actor_id=accounts["actor"],
            idempotency_key=f"wo-{uuid.uuid4()}",
        )
        await session2.commit()
    finally:
        await session2.close()

    assert result["direct"] is True
    assert result["approval_request_id"] is None

    session3 = await _new_session(test_engine)
    try:
        updated = await session3.get(Loan, loan.id)
        assert updated.status == "written_off"
        assert updated.outstanding_principal == Decimal("0")
        assert updated.total_written_off == write_off_amount
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_write_off_gl_balanced(test_engine):
    """Write-off GL entry: Dr loan_loss_expense / Cr gl_principal_receivable_id — balanced."""
    from app.modules.ledger.models import JournalLine
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        from app.modules.credit.models import LoanProduct
        product = await session.get(LoanProduct, loan.loan_product_id)
        product.write_off_threshold = Decimal("999999.00")
        await session.commit()
    finally:
        await session.close()

    write_off_amount = Decimal("100.00")

    session2 = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session2)
        result = await svc.write_off(
            loan_id=loan.id,
            amount=write_off_amount,
            reason="Partial write-off",
            actor_id=accounts["actor"],
            idempotency_key=f"wo-{uuid.uuid4()}",
        )
        await session2.commit()
        journal_entry_id = result["journal_entry_id"]
    finally:
        await session2.close()

    session3 = await _new_session(test_engine)
    try:
        lines = list(
            (await session3.execute(
                sa_select(JournalLine).where(JournalLine.journal_entry_id == journal_entry_id)
            )).scalars().all()
        )
        total_debit = sum(l.debit_amount for l in lines)
        total_credit = sum(l.credit_amount for l in lines)
        assert total_debit == total_credit == write_off_amount

        for line in lines:
            assert line.sub_ledger_type == "loan"
            assert line.sub_ledger_id == loan.id
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_write_off_above_threshold_creates_approval_request(test_engine):
    """Write-off amount > threshold → approval_request created, GL not yet posted."""
    from app.modules.ledger.models import JournalEntry
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    # Product has write_off_threshold=0 by default → any amount > 0 needs approval.
    write_off_amount = Decimal("500.00")

    session = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session)
        result = await svc.write_off(
            loan_id=loan.id,
            amount=write_off_amount,
            reason="Needs approval",
            actor_id=accounts["actor"],
            idempotency_key=f"wo-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    assert result["direct"] is False
    assert result["approval_request_id"] is not None

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        # Status should NOT be written_off yet.
        assert updated.status != "written_off"
        assert updated.total_written_off == Decimal("0")

        # No GL entry posted yet.
        count = await session2.scalar(
            sa_select(func.count()).select_from(JournalEntry).where(
                JournalEntry.reference.like(f"LOAN-WO-%")
            )
        )
        assert count == 0
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_write_off_already_written_off_raises(test_engine):
    """Write-off on a written_off loan raises ValueError."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    # Force status to written_off.
    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.status = "written_off"
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session2)
        with pytest.raises(ValueError, match="written_off"):
            await svc.write_off(
                loan_id=loan.id,
                amount=Decimal("100.00"),
                reason="Double write-off",
                actor_id=accounts["actor"],
                idempotency_key=f"wo-{uuid.uuid4()}",
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_write_off_amount_exceeds_principal_raises(test_engine):
    """Write-off amount > outstanding_principal raises ValueError."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        from app.modules.credit.models import LoanProduct
        product = await session.get(LoanProduct, loan.loan_product_id)
        product.write_off_threshold = Decimal("999999.00")
        await session.commit()
    finally:
        await session.close()

    too_much = loan.outstanding_principal + Decimal("1.00")
    session2 = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session2)
        with pytest.raises(ValueError, match="outstanding_principal"):
            await svc.write_off(
                loan_id=loan.id,
                amount=too_much,
                reason="Too much",
                actor_id=accounts["actor"],
                idempotency_key=f"wo-{uuid.uuid4()}",
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_write_off_idempotency(test_engine):
    """Same idempotency_key twice → second call is no-op, returns same result."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        from app.modules.credit.models import LoanProduct
        product = await session.get(LoanProduct, loan.loan_product_id)
        product.write_off_threshold = Decimal("999999.00")
        await session.commit()
    finally:
        await session.close()

    idem_key = f"wo-idem-{uuid.uuid4()}"
    write_off_amount = Decimal("100.00")

    session2 = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session2)
        r1 = await svc.write_off(
            loan_id=loan.id, amount=write_off_amount, reason="First",
            actor_id=accounts["actor"], idempotency_key=idem_key,
        )
        await session2.commit()
    finally:
        await session2.close()

    session3 = await _new_session(test_engine)
    try:
        svc2 = LoanWriteOffService(session3)
        r2 = await svc2.write_off(
            loan_id=loan.id, amount=write_off_amount, reason="Second",
            actor_id=accounts["actor"], idempotency_key=idem_key,
        )
        await session3.commit()
    finally:
        await session3.close()

    assert r1["journal_entry_id"] == r2["journal_entry_id"]

    session4 = await _new_session(test_engine)
    try:
        updated = await session4.get(Loan, loan.id)
        assert updated.total_written_off == write_off_amount  # not doubled
    finally:
        await session4.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_service.py -k "write_off" -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.modules.credit.services.write_off'`

- [ ] **Step 3: Create `app/modules/credit/services/write_off.py`**

```python
# app/modules/credit/services/write_off.py
"""Loan write-off: direct execution or maker-checker (quorum=2 above threshold)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanProduct

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
        loan_loss_account_code: str = "LOAN-LOSS-EXPENSE",
    ) -> dict[str, Any]:
        """Submit or directly execute a loan write-off.

        Returns:
            dict with keys:
              - direct: bool (True = executed immediately)
              - approval_request_id: UUID | None
              - journal_entry_id: UUID | None (only set for direct execution)
        """
        from app.modules.ledger.models import JournalEntry

        idem_key = f"loan-wo-{idempotency_key}"

        # Idempotency guard.
        existing_entry = await self._session.scalar(
            select(JournalEntry).where(JournalEntry.idempotency_key == idem_key)
        )
        if existing_entry is not None:
            return {
                "direct": True,
                "approval_request_id": None,
                "journal_entry_id": existing_entry.id,
            }

        loan = await self._session.scalar(
            select(Loan).where(Loan.id == loan_id).with_for_update()
        )
        if loan is None:
            raise ValueError(f"Loan {loan_id} not found")
        if loan.status == "written_off":
            raise ValueError(f"Loan is already written_off")
        if amount > loan.outstanding_principal:
            raise ValueError(
                f"Write-off amount {amount} exceeds outstanding_principal {loan.outstanding_principal}"
            )

        product = await self._session.get(LoanProduct, loan.loan_product_id)
        if product is None:
            raise ValueError(f"Loan product {loan.loan_product_id} not found")

        # Decide: direct or maker-checker.
        if amount > product.write_off_threshold:
            return await self._submit_for_approval(
                loan=loan,
                amount=amount,
                reason=reason,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
            )
        else:
            journal_entry = await self._execute_write_off(
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
                "journal_entry_id": journal_entry.id,
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
    ):
        """Post the write-off GL entry and update loan snapshot."""
        from app.modules.ledger.models import ChartOfAccount
        from app.modules.ledger.service import LedgerService

        # Resolve loan loss expense account.
        loss_account = await self._session.scalar(
            select(ChartOfAccount).where(ChartOfAccount.code == loan_loss_account_code)
        )
        if loss_account is None:
            raise ValueError(f"GL account '{loan_loss_account_code}' not found")

        ledger_svc = LedgerService(self._session)
        journal_entry = await ledger_svc.post_journal_entry(
            reference=f"LOAN-WO-{loan.loan_reference}",
            description=f"Write-off: {loan.loan_reference} — {reason}",
            posted_by=actor_id,
            idempotency_key=idem_key,
            lines=[
                {
                    "account_id": loss_account.id,
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

        loan.outstanding_principal = loan.outstanding_principal - amount
        loan.total_written_off = loan.total_written_off + amount
        loan.status = "written_off"

        from app.core.outbox.publisher import EventPublisher
        publisher = EventPublisher(self._session)
        await publisher.publish(
            "LoanWrittenOff",
            {
                "loan_id": str(loan.id),
                "amount": str(amount),
                "reason": reason,
            },
        )

        _log.info(
            "credit.write_off.executed",
            loan_id=str(loan.id),
            amount=str(amount),
        )
        return journal_entry

    async def _submit_for_approval(
        self,
        *,
        loan: Loan,
        amount: Decimal,
        reason: str,
        actor_id: uuid.UUID,
        idempotency_key: str,
    ) -> dict:
        """Submit write-off to maker-checker (quorum=2)."""
        from app.modules.maker_checker.service import ApprovalService

        svc = ApprovalService(self._session)
        approval_request = await svc.submit(
            operation_type="credit.write_off",
            payload={
                "loan_id": str(loan.id),
                "amount": str(amount),
                "reason": reason,
                "idempotency_key": idempotency_key,
            },
            requested_by=actor_id,
            required_approvals=2,
            idempotency_key=f"wo-approval-{idempotency_key}",
        )
        _log.info(
            "credit.write_off.submitted_for_approval",
            loan_id=str(loan.id),
            approval_request_id=str(approval_request.id),
        )
        return {
            "direct": False,
            "approval_request_id": approval_request.id,
            "journal_entry_id": None,
        }
```

- [ ] **Step 4: Add `credit.write_off` executor to `app/modules/credit/executors.py`**

Append to the existing `executors.py` (after the `execute_approve_application` function):

```python
@approval_executor("credit.write_off")
async def execute_write_off(session: AsyncSession, payload: dict) -> None:
    """Executor for credit.write_off approval requests (quorum=2 path)."""
    from app.modules.credit.models import Loan
    from app.modules.credit.services.write_off import LoanWriteOffService

    loan_id = uuid.UUID(payload["loan_id"])
    amount = Decimal(payload["amount"])
    reason = str(payload["reason"])
    idempotency_key = str(payload["idempotency_key"])

    # Idempotency: if already written off with this key, skip.
    from app.modules.ledger.models import JournalEntry
    idem_key = f"loan-wo-{idempotency_key}"
    existing = await session.scalar(
        select(JournalEntry).where(JournalEntry.idempotency_key == idem_key)
    )
    if existing is not None:
        return  # already executed

    loan = await session.scalar(select(Loan).where(Loan.id == loan_id).with_for_update())
    if loan is None:
        raise ValueError(f"Loan {loan_id} not found")

    svc = LoanWriteOffService(session)
    await svc._execute_write_off(
        loan=loan,
        amount=amount,
        reason=reason,
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        idem_key=idem_key,
        loan_loss_account_code="LOAN-LOSS-EXPENSE",
    )
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/modules/credit/test_service.py -k "write_off" -v
```

Expected: all 6 write-off tests `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add app/modules/credit/services/write_off.py app/modules/credit/executors.py tests/modules/credit/test_service.py
git commit -m "feat(credit): LoanWriteOffService + credit.write_off executor"
```

---

## Task 2 — Write-Off Schemas and API Endpoint

**Files:**
- Modify: `app/modules/credit/schemas.py`
- Modify: `app/modules/credit/api.py`

- [ ] **Step 1: Add write-off schemas to `app/modules/credit/schemas.py`**

```python
# ── Write-off schemas ─────────────────────────────────────────────────────────

class WriteOffIn(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    reason: str
    idempotency_key: str
    loan_loss_account_code: str = "LOAN-LOSS-EXPENSE"

    model_config = ConfigDict(from_attributes=True)


class WriteOffOut(BaseModel):
    direct: bool
    approval_request_id: uuid.UUID | None
    journal_entry_id: uuid.UUID | None

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 2: Add write-off endpoint to `app/modules/credit/api.py`**

```python
# ── Write-off endpoint ────────────────────────────────────────────────────────

@router.post("/loans/{loan_id}/write-off", response_model=WriteOffOut, status_code=201)
async def write_off_loan(
    loan_id: uuid.UUID,
    body: WriteOffIn,
    session: AsyncSession = Depends(get_tenant_session),
    actor_id: uuid.UUID = Depends(get_actor_id),
) -> WriteOffOut:
    svc = LoanWriteOffService(session)
    result = await svc.write_off(
        loan_id=loan_id,
        amount=body.amount,
        reason=body.reason,
        actor_id=actor_id,
        idempotency_key=body.idempotency_key,
        loan_loss_account_code=body.loan_loss_account_code,
    )
    return WriteOffOut(**result)
```

- [ ] **Step 3: Verify import**

```bash
python -c "from app.modules.credit.services.write_off import LoanWriteOffService; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/modules/credit/schemas.py app/modules/credit/api.py
git commit -m "feat(credit): write-off API endpoint"
```

---

## Verification Criteria

```bash
# 1. Write-off tests pass
pytest tests/modules/credit/test_service.py -k "write_off" -v

# 2. Full suite — no regressions
pytest -x -q
```

All commands must exit 0. Confirm:
- `amount <= write_off_threshold` → direct execution, `status=written_off`, GL posted
- `amount > write_off_threshold` → `approval_request` created, GL not posted, status unchanged
- GL: Dr loan_loss_expense / Cr gl_principal_receivable_id — balanced
- GL lines tagged `sub_ledger_type='loan'`
- `outstanding_principal` decremented, `total_written_off` incremented
- Status → `written_off` after direct execution
- Write-off on `written_off` loan raises `ValueError`
- `amount > outstanding_principal` raises `ValueError`
- Same idempotency_key twice → second call is no-op, `total_written_off` not doubled
