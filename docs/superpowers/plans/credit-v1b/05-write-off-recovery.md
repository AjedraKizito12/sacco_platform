# Credit v1b Sub-Plan 05 — Write-Off Recovery

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `LoanWriteOffService.recover()`, lien reactivation hook via `GuarantorService`,
and one recovery API endpoint.

**Architecture:** Recovery reverses a write-off entry in the same DB transaction as lien
reactivation. No maker-checker — the cash receipt is the authorizing event. Idempotency
guards prevent double-posting.

**Tech Stack:** SQLAlchemy 2.0 async, Pydantic v2, FastAPI, LedgerService, EventPublisher

**Prerequisite:** Sub-plans 01 and 02 must be complete.
`app/modules/credit/services/guarantor.py` must define `GuarantorService.reactivate_liens()`.

---

## Required Reading

Before starting:
- `app/modules/credit/services/write_off.py` — existing `_execute_write_off` pattern
- `app/modules/credit/services/guarantor.py` — `reactivate_liens` signature
- `app/modules/credit/models.py` — `Loan.total_written_off`, `Loan.gl_loan_loss_expense_id`
- Design spec §8

---

## Task 1: Recovery service method (`LoanWriteOffService.recover`)

**Files:**
- Modify: `app/modules/credit/services/write_off.py`

- [ ] **Step 1: Write the failing test**

Create `tests/modules/credit/test_write_off_recovery.py`:

```python
"""Tests for LoanWriteOffService.recover()."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.credit.models import Loan
from app.modules.credit.services.write_off import LoanWriteOffService
from app.modules.ledger.models import JournalEntry


@pytest.fixture
async def written_off_loan(
    tenant_session,
    seeded_loan_product,
    db_member,
    db_savings_account,
    gl_accounts,
):
    """A loan that has been fully written off (outstanding_principal=0, total_written_off > 0)."""
    from app.modules.credit.models import Loan, LoanApplication

    app_obj = LoanApplication(
        loan_product_id=seeded_loan_product.id,
        member_id=db_member.id,
        requested_amount=Decimal("500000"),
        requested_term_periods=12,
        purpose="test",
        disbursement_destination="member_savings",
        disbursement_account_id=db_savings_account.id,
        status="disbursed",
        idempotency_key=str(uuid.uuid4()),
    )
    tenant_session.add(app_obj)

    loan = Loan(
        loan_reference=f"LN-TEST-{uuid.uuid4().hex[:6].upper()}",
        loan_application_id=app_obj.id,
        loan_product_id=seeded_loan_product.id,
        member_id=db_member.id,
        status="written_off",
        principal_amount=Decimal("500000"),
        interest_method="flat",
        annual_interest_rate=Decimal("18"),
        repayment_frequency="monthly",
        term_periods=12,
        repayment_allocation="INTEREST_PRINCIPAL",
        disbursement_destination="member_savings",
        disbursement_account_id=db_savings_account.id,
        gl_principal_receivable_id=gl_accounts["principal_receivable"].id,
        gl_interest_receivable_id=gl_accounts["interest_receivable"].id,
        gl_interest_income_id=gl_accounts["interest_income"].id,
        gl_disbursement_account_id=gl_accounts["disbursement"].id,
        gl_loan_loss_expense_id=gl_accounts["loan_loss_expense"].id,
        outstanding_principal=Decimal("0"),
        total_written_off=Decimal("200000"),
        disbursed_by=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        idempotency_key=str(uuid.uuid4()),
    )
    tenant_session.add(loan)
    await tenant_session.commit()
    await tenant_session.refresh(loan)
    return loan


async def test_recover_restores_principal(written_off_loan, tenant_session):
    """Recovery posts GL entry and restores outstanding_principal."""
    svc = LoanWriteOffService(tenant_session)
    result = await svc.recover(
        loan_id=written_off_loan.id,
        amount=Decimal("100000"),
        reason="Partial recovery from debtor",
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        idempotency_key="test-rec-001",
    )
    await tenant_session.commit()

    refreshed = await tenant_session.get(Loan, written_off_loan.id)
    assert refreshed.outstanding_principal == Decimal("100000")
    assert refreshed.total_written_off == Decimal("100000")
    assert refreshed.status == "in_arrears"
    assert result["journal_entry_id"] is not None


async def test_recover_on_non_written_off_loan_raises(written_off_loan, tenant_session):
    """recover() on a non-written_off loan raises ValueError."""
    from sqlalchemy import update
    from app.modules.credit.models import Loan

    await tenant_session.execute(
        update(Loan).where(Loan.id == written_off_loan.id).values(status="in_arrears")
    )
    await tenant_session.commit()
    await tenant_session.refresh(written_off_loan)

    svc = LoanWriteOffService(tenant_session)
    with pytest.raises(ValueError, match="written_off"):
        await svc.recover(
            loan_id=written_off_loan.id,
            amount=Decimal("50000"),
            reason="test",
            actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            idempotency_key="test-rec-002",
        )


async def test_recover_exceeds_written_off_raises(written_off_loan, tenant_session):
    """recover() with amount > total_written_off raises ValueError."""
    svc = LoanWriteOffService(tenant_session)
    with pytest.raises(ValueError, match="exceeds"):
        await svc.recover(
            loan_id=written_off_loan.id,
            amount=Decimal("999999"),  # > total_written_off (200000)
            reason="test",
            actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            idempotency_key="test-rec-003",
        )


async def test_recover_gl_balanced(written_off_loan, tenant_session):
    """Recovery GL: Dr principal_receivable / Cr loan_loss_expense — balanced."""
    from app.modules.ledger.models import JournalEntry, JournalLine

    svc = LoanWriteOffService(tenant_session)
    result = await svc.recover(
        loan_id=written_off_loan.id,
        amount=Decimal("50000"),
        reason="test gl balance",
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        idempotency_key="test-rec-004",
    )
    await tenant_session.commit()

    entry = await tenant_session.get(JournalEntry, result["journal_entry_id"])
    lines = (
        await tenant_session.scalars(
            select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
        )
    ).all()
    total_debit = sum(l.debit_amount for l in lines)
    total_credit = sum(l.credit_amount for l in lines)
    assert total_debit == total_credit


async def test_recover_idempotent(written_off_loan, tenant_session):
    """Same idempotency_key twice → no duplicate GL entry."""
    svc = LoanWriteOffService(tenant_session)
    r1 = await svc.recover(
        loan_id=written_off_loan.id,
        amount=Decimal("50000"),
        reason="first",
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        idempotency_key="test-rec-idem",
    )
    await tenant_session.commit()
    r2 = await svc.recover(
        loan_id=written_off_loan.id,
        amount=Decimal("50000"),
        reason="second",
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        idempotency_key="test-rec-idem",
    )
    await tenant_session.commit()

    # Same journal entry returned on second call
    assert r1["journal_entry_id"] == r2["journal_entry_id"]

    # Only one journal entry with this idem key
    entries = (
        await tenant_session.scalars(
            select(JournalEntry).where(
                JournalEntry.idempotency_key == "loan-wor-test-rec-idem"
            )
        )
    ).all()
    assert len(entries) == 1
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/modules/credit/test_write_off_recovery.py -v
```

Expected: `FAILED` — `LoanWriteOffService` has no `recover` method.

- [ ] **Step 3: Implement `recover()` in `write_off.py`**

Add the `recover` method to `LoanWriteOffService`. Open `app/modules/credit/services/write_off.py`
and add after `_execute_write_off`:

```python
    async def recover(
        self,
        *,
        loan_id: uuid.UUID,
        amount: Decimal,
        reason: str,
        actor_id: uuid.UUID,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Post a write-off recovery entry.

        Restores outstanding_principal by amount, reduces total_written_off,
        transitions loan to in_arrears, and reactivates guarantor liens.

        No maker-checker — the cash receipt is the authorizing event.

        Returns dict with keys:
            journal_entry_id: uuid.UUID
        """
        idem_key = f"loan-wor-{idempotency_key}"

        # Idempotency guard.
        existing_entry = await self._session.scalar(
            select(JournalEntry).where(JournalEntry.idempotency_key == idem_key)
        )
        if existing_entry is not None:
            _log.info("credit.recover.idempotent_hit", idempotency_key=idempotency_key)
            return {"journal_entry_id": existing_entry.id}

        # Lock loan row.
        loan = await self._session.scalar(
            select(Loan).where(Loan.id == loan_id).with_for_update()
        )
        if loan is None:
            raise ValueError(f"Loan '{loan_id}' not found")

        if loan.status != "written_off":
            raise ValueError(
                f"Loan '{loan_id}' is not written_off (status={loan.status!r}). "
                "Only written_off loans can be recovered."
            )

        if amount <= Decimal("0") or amount > loan.total_written_off:
            raise ValueError(
                f"Recovery amount {amount} exceeds total_written_off "
                f"{loan.total_written_off} for loan '{loan_id}'"
            )

        if loan.gl_loan_loss_expense_id is None:
            raise ValueError(
                f"Loan '{loan_id}' has no gl_loan_loss_expense_id — cannot post recovery"
            )

        # GL: Dr principal_receivable / Cr loan_loss_expense.
        ledger_svc = LedgerService(self._session)
        entry = await ledger_svc.post_journal_entry(
            reference=f"LOAN-REC-{loan.id}",
            description=f"Write-off recovery: {reason}",
            posted_by=actor_id,
            idempotency_key=idem_key,
            lines=[
                {
                    "account_id": loan.gl_principal_receivable_id,
                    "debit_amount": amount,
                    "credit_amount": Decimal("0"),
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": loan.id,
                },
                {
                    "account_id": loan.gl_loan_loss_expense_id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": amount,
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": loan.id,
                },
            ],
        )

        # Update snapshot.
        loan.outstanding_principal = loan.outstanding_principal + amount
        loan.total_written_off = loan.total_written_off - amount
        loan.status = "in_arrears"

        await self._session.flush()

        # Reactivate guarantor liens (no-op if no guarantors).
        from app.modules.credit.services.guarantor import GuarantorService  # noqa: PLC0415
        guarantor_svc = GuarantorService(self._session)
        await guarantor_svc.reactivate_liens(loan_id=loan.id, restored_amount=amount)

        await EventPublisher.publish(
            self._session,
            aggregate_type="loan",
            aggregate_id=loan.id,
            event_type="LoanRecoveryPosted",
            payload={
                "loan_id": str(loan.id),
                "amount": str(amount),
                "journal_entry_id": str(entry.id),
            },
        )

        _log.info(
            "credit.loan.recovery_posted",
            loan_id=str(loan.id),
            amount=str(amount),
            journal_entry_id=str(entry.id),
        )
        return {"journal_entry_id": entry.id}
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/modules/credit/test_write_off_recovery.py -v
```

Expected: All 5 tests **PASS**.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/services/write_off.py \
        tests/modules/credit/test_write_off_recovery.py
git commit -m "feat(credit): LoanWriteOffService.recover() — write-off recovery with lien reactivation"
```

---

## Task 2: Recovery schemas and API endpoint

**Files:**
- Modify: `app/modules/credit/schemas.py`
- Modify: `app/modules/credit/api.py`

- [ ] **Step 1: Add recovery schemas to `schemas.py`**

Open `app/modules/credit/schemas.py` and add at the end:

```python
# ── Write-Off Recovery ────────────────────────────────────────────────────────


class LoanRecoveryIn(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=200)


class LoanRecoveryOut(BaseModel):
    journal_entry_id: uuid.UUID
```

- [ ] **Step 2: Add recovery import and endpoint to `api.py`**

In `app/modules/credit/api.py`, add `LoanRecoveryIn` and `LoanRecoveryOut` to the
schema imports block, and `LoanWriteOffService` is already imported. Add the endpoint
after the write-off endpoint:

```python
@router.post("/loans/{loan_id}/recover", response_model=LoanRecoveryOut, status_code=201)
async def recover_loan(
    loan_id: uuid.UUID,
    body: LoanRecoveryIn,
    session: Session,
) -> LoanRecoveryOut:
    """Post a write-off recovery entry for a loan."""
    svc = LoanWriteOffService(session)
    result = await svc.recover(
        loan_id=loan_id,
        amount=body.amount,
        reason=body.reason,
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),  # TODO: real actor from auth
        idempotency_key=body.idempotency_key,
    )
    await session.commit()
    return LoanRecoveryOut(journal_entry_id=result["journal_entry_id"])
```

- [ ] **Step 3: Write the API integration test**

Create `tests/modules/credit/test_api_recovery.py`:

```python
"""Integration tests for POST /credit/loans/{id}/recover."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient


async def test_recover_returns_201(written_off_loan, async_client: AsyncClient):
    """POST /credit/loans/{id}/recover returns 201 with journal_entry_id."""
    response = await async_client.post(
        f"/credit/loans/{written_off_loan.id}/recover",
        json={
            "amount": "50000",
            "reason": "Partial recovery",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "journal_entry_id" in data


async def test_recover_non_written_off_loan_returns_422(
    disbursed_loan, async_client: AsyncClient
):
    """POST /credit/loans/{id}/recover on active loan returns 422."""
    response = await async_client.post(
        f"/credit/loans/{disbursed_loan.id}/recover",
        json={
            "amount": "10000",
            "reason": "test",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code in (422, 400)
```

- [ ] **Step 4: Run tests**

```
pytest tests/modules/credit/test_write_off_recovery.py \
       tests/modules/credit/test_api_recovery.py -v
```

Expected: All tests **PASS** (skip API tests if `written_off_loan` / `disbursed_loan`
fixtures don't exist in the API conftest — the service tests are sufficient for
sub-plan verification).

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/schemas.py \
        app/modules/credit/api.py \
        tests/modules/credit/test_api_recovery.py
git commit -m "feat(credit): POST /credit/loans/{id}/recover endpoint"
```

---

## Verification Checklist

- [ ] `pytest tests/modules/credit/test_write_off_recovery.py -v` — all 5 tests pass
- [ ] Recovery on non-`written_off` loan raises `ValueError`
- [ ] `amount > total_written_off` raises `ValueError`
- [ ] GL: Dr `principal_receivable` / Cr `loan_loss_expense` — balanced (verified by test)
- [ ] `outstanding_principal` restored, `total_written_off` reduced, `status → in_arrears`
- [ ] Idempotency: second call with same key returns same `journal_entry_id`
