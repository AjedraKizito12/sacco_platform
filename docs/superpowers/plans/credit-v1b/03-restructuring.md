# Sub-plan 03 — Schedule Restructuring

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans`.

**Goal:** Implement `LoanRestructuringService` (term extension + payment holiday),
register the `credit.restructure_schedule` executor, and add the two restructuring
API endpoints.

**Architecture:** Restructuring submits a maker-checker approval (quorum=2). The executor
calls `_execute_restructuring()` which marks unpaid installments `is_superseded=True` and
writes a fresh set. Paid installments are never touched. All changes happen in one
DB transaction.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, ApprovalService, pytest-asyncio

---

## Required Reading

- `app/modules/credit/models.py` — `LoanRestructuring`, `LoanInstallment`, `Loan`
- `app/modules/credit/services/_schedule.py` — `compute_schedule` (reused for term extension)
- `app/modules/credit/executors.py` — `@approval_executor` pattern
- `app/modules/maker_checker/service.py` — `ApprovalService.submit`

---

## Task 1: LoanRestructuringService

**Files:**
- Create: `app/modules/credit/services/restructuring.py`
- Create: `tests/modules/credit/test_restructuring_service.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/modules/credit/test_restructuring_service.py
"""Tests for LoanRestructuringService — term extension and payment holiday."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.modules.credit.models import Loan, LoanInstallment, LoanRestructuring


TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_restructure_submits_approval_request(test_engine: AsyncEngine) -> None:
    """restructure() returns an approval_request_id without executing immediately."""
    from tests.modules.credit.test_service import _setup_disbursed_loan
    factory = _factory(test_engine)

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)
        actor_id = uuid.uuid4()

        from app.modules.credit.services.restructuring import LoanRestructuringService
        svc = LoanRestructuringService(session)
        result = await svc.restructure(
            loan_id=loan.id,
            restructuring_type="term_extension",
            periods_added=3,
            reason="Financial hardship",
            actor_id=actor_id,
            idempotency_key=str(uuid.uuid4()),
        )
        await session.commit()

    assert "approval_request_id" in result
    assert result["approval_request_id"] is not None


@pytest.mark.anyio
async def test_execute_term_extension_supersedes_unpaid(test_engine: AsyncEngine) -> None:
    """_execute_restructuring marks all unpaid installments is_superseded=True
    and writes new ones with updated term_periods."""
    from tests.modules.credit.test_service import _setup_disbursed_loan
    factory = _factory(test_engine)

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)
        original_term = loan.term_periods

        from app.modules.credit.services.restructuring import LoanRestructuringService
        svc = LoanRestructuringService(session)
        await svc._execute_restructuring(
            loan_id=loan.id,
            restructuring_type="term_extension",
            periods_added=3,
            reason="Hardship",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            approval_request_id=None,
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan_reloaded = await session.get(Loan, loan.id)
        assert loan_reloaded.term_periods == original_term + 3

        # All unpaid installments superseded
        superseded = (await session.execute(
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == loan.id)
            .where(LoanInstallment.is_superseded.is_(True))
        )).scalars().all()
        assert len(superseded) == original_term

        # New active installments written
        active = (await session.execute(
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == loan.id)
            .where(LoanInstallment.is_superseded.is_(False))
            .order_by(LoanInstallment.period_number)
        )).scalars().all()
        assert len(active) == original_term + 3
        assert sum(i.principal_due for i in active) == pytest.approx(
            float(loan.outstanding_principal), abs=1.0
        )


@pytest.mark.anyio
async def test_execute_payment_holiday_shifts_due_dates(test_engine: AsyncEngine) -> None:
    """Payment holiday shifts the next N installment due dates forward by N periods."""
    from tests.modules.credit.test_service import _setup_disbursed_loan
    factory = _factory(test_engine)

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)

        # Get original first unpaid due date
        first_installment = (await session.execute(
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == loan.id)
            .where(LoanInstallment.status == "pending")
            .order_by(LoanInstallment.period_number)
            .limit(1)
        )).scalar_one()
        original_due = first_installment.due_date

        from app.modules.credit.services.restructuring import LoanRestructuringService
        svc = LoanRestructuringService(session)
        await svc._execute_restructuring(
            loan_id=loan.id,
            restructuring_type="payment_holiday",
            periods_added=2,
            reason="Holiday",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            approval_request_id=None,
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        # The first new active installment should have a later due date
        first_new = (await session.execute(
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == loan.id)
            .where(LoanInstallment.is_superseded.is_(False))
            .order_by(LoanInstallment.period_number)
            .limit(1)
        )).scalar_one()
        # Due date shifted by 2 months (monthly frequency)
        assert first_new.due_date > original_due


@pytest.mark.anyio
async def test_paid_installments_never_superseded(test_engine: AsyncEngine) -> None:
    """Installments with status='paid' are never marked is_superseded."""
    from tests.modules.credit.test_service import _setup_disbursed_loan
    factory = _factory(test_engine)

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)

        # Manually mark first installment as paid
        first = (await session.execute(
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == loan.id)
            .order_by(LoanInstallment.period_number)
            .limit(1)
        )).scalar_one()
        first.status = "paid"
        await session.commit()

        from app.modules.credit.services.restructuring import LoanRestructuringService
        svc = LoanRestructuringService(session)
        await svc._execute_restructuring(
            loan_id=loan.id,
            restructuring_type="term_extension",
            periods_added=2,
            reason="test",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            approval_request_id=None,
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        paid = await session.get(LoanInstallment, first.id)
        assert paid.is_superseded is False  # paid installment never superseded
```

- [ ] **Step 2: Run to confirm failure**

```bash
venv/bin/pytest tests/modules/credit/test_restructuring_service.py -v 2>&1 | head -20
```

Expected: ImportError — `LoanRestructuringService` does not exist.

- [ ] **Step 3: Implement LoanRestructuringService**

```python
# app/modules/credit/services/restructuring.py
"""LoanRestructuringService — term extension and payment holiday (maker-checker)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from dateutil.relativedelta import relativedelta
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanInstallment, LoanRestructuring
from app.modules.credit.services._schedule import compute_schedule
from app.modules.maker_checker.service import ApprovalService

_log = structlog.get_logger(__name__)

_FREQ_DELTA = {
    "weekly": relativedelta(weeks=1),
    "biweekly": relativedelta(weeks=2),
    "monthly": relativedelta(months=1),
    "quarterly": relativedelta(months=3),
    "lump_sum": relativedelta(months=1),
}


class LoanRestructuringService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def restructure(
        self,
        *,
        loan_id: uuid.UUID,
        restructuring_type: str,
        periods_added: int,
        reason: str,
        actor_id: uuid.UUID,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Submit restructuring for maker-checker approval (quorum=2)."""
        loan = await self._session.get(Loan, loan_id)
        if loan is None:
            raise ValueError(f"Loan '{loan_id}' not found")
        if loan.status not in ("disbursed", "in_arrears"):
            raise ValueError(
                f"Cannot restructure loan with status '{loan.status}'"
            )
        if restructuring_type not in ("term_extension", "payment_holiday"):
            raise ValueError(f"Invalid restructuring_type '{restructuring_type}'")
        if periods_added < 1:
            raise ValueError("periods_added must be >= 1")

        approval_svc = ApprovalService(self._session)
        request = await approval_svc.submit(
            operation_type="credit.restructure_schedule",
            payload={
                "loan_id": str(loan_id),
                "restructuring_type": restructuring_type,
                "periods_added": periods_added,
                "reason": reason,
                "idempotency_key": idempotency_key,
            },
            requested_by=actor_id,
            required_approvals=2,
        )
        _log.info(
            "credit.restructuring.submitted",
            loan_id=str(loan_id),
            type=restructuring_type,
            approval_request_id=str(request.id),
        )
        return {"approval_request_id": request.id}

    async def _execute_restructuring(
        self,
        *,
        loan_id: uuid.UUID,
        restructuring_type: str,
        periods_added: int,
        reason: str,
        actor_id: uuid.UUID,
        idempotency_key: str,
        approval_request_id: uuid.UUID | None,
    ) -> LoanRestructuring:
        """Execute restructuring: supersede unpaid installments, write new schedule."""
        from app.core.outbox import EventPublisher

        # Idempotency guard
        existing = await self._session.scalar(
            select(LoanRestructuring).where(LoanRestructuring.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

        # Lock loan row
        loan = await self._session.scalar(
            select(Loan).where(Loan.id == loan_id).with_for_update()
        )
        if loan is None:
            raise ValueError(f"Loan '{loan_id}' not found")

        # Fetch all active installments ordered by period_number
        result = await self._session.execute(
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == loan_id)
            .where(LoanInstallment.is_superseded.is_(False))
            .order_by(LoanInstallment.period_number)
        )
        active_installments = list(result.scalars().all())

        # Separate paid vs unpaid
        paid = [i for i in active_installments if i.status == "paid"]
        unpaid = [i for i in active_installments if i.status != "paid"]
        last_paid_period = max((i.period_number for i in paid), default=0)

        # Mark unpaid as superseded
        for inst in unpaid:
            inst.is_superseded = True

        # Compute new installments
        new_installments: list[LoanInstallment] = []
        freq = loan.repayment_frequency
        delta = _FREQ_DELTA[freq]

        if restructuring_type == "term_extension":
            # Recompute schedule from outstanding_principal over (remaining + added) periods
            remaining_periods = len(unpaid) + periods_added
            new_term_periods = last_paid_period + remaining_periods

            # Use compute_schedule with outstanding_principal as new principal
            start_date = date.today()
            schedule = compute_schedule(
                principal=loan.outstanding_principal,
                annual_rate=loan.annual_interest_rate,
                term_periods=remaining_periods,
                frequency=freq,
                interest_method=loan.interest_method,
                start_date=start_date,
            )
            for idx, row in enumerate(schedule):
                inst = LoanInstallment(
                    loan_id=loan_id,
                    period_number=last_paid_period + 1 + idx,
                    due_date=row["due_date"],
                    principal_due=row["principal_due"],
                    interest_due=row["interest_due"],
                    total_due=row["principal_due"] + row["interest_due"],
                    restructuring_id=None,  # set after LoanRestructuring is created
                )
                self._session.add(inst)
                new_installments.append(inst)

            new_maturity_date = schedule[-1]["due_date"] if schedule else date.today()

        else:  # payment_holiday
            # Shift due dates of unpaid installments by periods_added periods
            new_term_periods = loan.term_periods + periods_added
            if not unpaid:
                new_maturity_date = loan.maturity_date
            else:
                first_unpaid_due = unpaid[0].due_date
                for idx, orig in enumerate(unpaid):
                    shifted_date = first_unpaid_due + (delta * (idx + periods_added))
                    inst = LoanInstallment(
                        loan_id=loan_id,
                        period_number=orig.period_number + periods_added,
                        due_date=shifted_date,
                        principal_due=orig.principal_due,
                        interest_due=orig.interest_due,
                        total_due=orig.total_due,
                        restructuring_id=None,
                    )
                    self._session.add(inst)
                    new_installments.append(inst)
                new_maturity_date = new_installments[-1].due_date if new_installments else date.today()

        # Update loan
        loan.term_periods = new_term_periods
        loan.maturity_date = new_maturity_date
        await self._session.flush()

        # Create restructuring record
        restructuring = LoanRestructuring(
            loan_id=loan_id,
            restructuring_type=restructuring_type,
            periods_added=periods_added,
            new_term_periods=new_term_periods,
            new_maturity_date=new_maturity_date,
            reason=reason,
            approval_request_id=approval_request_id,
            executed_by=actor_id,
            executed_at=datetime.now(UTC),
            idempotency_key=idempotency_key,
        )
        self._session.add(restructuring)
        await self._session.flush()

        # Tag new installments with restructuring_id
        for inst in new_installments:
            inst.restructuring_id = restructuring.id

        await self._session.flush()

        await EventPublisher.publish(
            self._session,
            aggregate_type="loan",
            aggregate_id=loan_id,
            event_type="LoanRestructured",
            payload={
                "loan_id": str(loan_id),
                "restructuring_id": str(restructuring.id),
                "type": restructuring_type,
                "periods_added": periods_added,
            },
        )

        _log.info(
            "credit.restructuring.executed",
            loan_id=str(loan_id),
            restructuring_id=str(restructuring.id),
            type=restructuring_type,
        )
        return restructuring
```

Note: `compute_schedule` in `_schedule.py` returns a list of dicts. Confirm the existing
signature returns `{"due_date": date, "principal_due": Decimal, "interest_due": Decimal}`.
Read `_schedule.py` before running tests and adjust field names if different.

Also ensure `python-dateutil` is available (it is a transitive dependency of many packages).
If not, install it: `venv/bin/pip install python-dateutil` and add to requirements.

- [ ] **Step 4: Run tests**

```bash
venv/bin/pytest tests/modules/credit/test_restructuring_service.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/services/restructuring.py tests/modules/credit/test_restructuring_service.py
git commit -m "feat(credit): LoanRestructuringService — term extension and payment holiday"
```

---

## Task 2: Register Executor

**Files:**
- Modify: `app/modules/credit/executors.py`

- [ ] **Step 1: Add restructure_schedule executor**

Append to `app/modules/credit/executors.py`:

```python
@approval_executor("credit.restructure_schedule")
async def execute_restructure_schedule(session: AsyncSession, payload: dict) -> dict:
    """Executor: called by ApprovalService when quorum=2 is met for restructuring."""
    loan_id = uuid.UUID(payload["loan_id"])
    restructuring_type = str(payload["restructuring_type"])
    periods_added = int(payload["periods_added"])
    reason = str(payload["reason"])
    idempotency_key = str(payload["idempotency_key"])

    from app.modules.credit.services.restructuring import LoanRestructuringService  # noqa: PLC0415

    svc = LoanRestructuringService(session)
    restructuring = await svc._execute_restructuring(
        loan_id=loan_id,
        restructuring_type=restructuring_type,
        periods_added=periods_added,
        reason=reason,
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        idempotency_key=idempotency_key,
        approval_request_id=None,  # approval_request_id set by caller if needed
    )
    return {"status": "restructured", "restructuring_id": str(restructuring.id)}
```

- [ ] **Step 2: Verify import**

```bash
venv/bin/python -c "import app.modules.credit.executors; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/modules/credit/executors.py
git commit -m "feat(credit): register credit.restructure_schedule executor"
```

---

## Task 3: Restructuring API Endpoints

**Files:**
- Modify: `app/modules/credit/schemas.py`
- Modify: `app/modules/credit/api.py`

- [ ] **Step 1: Add restructuring schemas**

In `app/modules/credit/schemas.py`, append:

```python
# ── Restructuring schemas ─────────────────────────────────────────────────────

class RestructureIn(BaseModel):
    restructuring_type: str  # 'term_extension' | 'payment_holiday'
    periods_added: int
    reason: str
    idempotency_key: str

class RestructuringOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    loan_id: uuid.UUID
    restructuring_type: str
    periods_added: int
    new_term_periods: int
    new_maturity_date: date
    reason: str
    executed_at: datetime
```

- [ ] **Step 2: Add endpoints to api.py**

```python
@router.post("/loans/{loan_id}/restructure", status_code=202)
async def restructure_loan(
    loan_id: uuid.UUID,
    body: RestructureIn,
    session: AsyncSession = Depends(get_tenant_session),
    actor_id: uuid.UUID = Depends(get_actor_id),
) -> dict:
    from app.modules.credit.services.restructuring import LoanRestructuringService
    svc = LoanRestructuringService(session)
    result = await svc.restructure(
        loan_id=loan_id,
        restructuring_type=body.restructuring_type,
        periods_added=body.periods_added,
        reason=body.reason,
        actor_id=actor_id,
        idempotency_key=body.idempotency_key,
    )
    return {"approval_request_id": str(result["approval_request_id"])}


@router.get("/loans/{loan_id}/restructurings")
async def list_restructurings(
    loan_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_session),
) -> list[RestructuringOut]:
    from sqlalchemy import select as sa_select
    from app.modules.credit.models import LoanRestructuring
    result = await session.execute(
        sa_select(LoanRestructuring)
        .where(LoanRestructuring.loan_id == loan_id)
        .order_by(LoanRestructuring.executed_at)
    )
    return [RestructuringOut.model_validate(r) for r in result.scalars().all()]
```

- [ ] **Step 3: Run full credit test suite**

```bash
venv/bin/pytest tests/modules/credit/ -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/modules/credit/schemas.py app/modules/credit/api.py
git commit -m "feat(credit): restructuring API endpoints — POST restructure, GET restructurings"
```

---

## Verification Criteria

```bash
venv/bin/pytest tests/modules/credit/test_restructuring_service.py -v
venv/bin/pytest tests/modules/credit/ -q  # no regressions
venv/bin/python -c "import app.modules.credit.executors; print('OK')"
```
