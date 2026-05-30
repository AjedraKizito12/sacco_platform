# Sub-plan 04 — Bulk Payroll Repayments

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans`.

**Goal:** Implement `PayrollBatchService` (CSV + JSON ingestion, validation/preview,
maker-checker approval, per-line application), register the `credit.apply_payroll_batch`
executor, and add four payroll API endpoints.

**Architecture:** Batch submission is always async — validate now, apply after approval.
Lines are applied one per commit so a single failure does not roll back others.
Idempotency per line uses `payroll-{batch_id}-{line_id}`.

**Tech Stack:** SQLAlchemy 2.0 async, FastAPI, Python `csv` stdlib, Pydantic v2

---

## Required Reading

- `app/modules/credit/models.py` — `PayrollBatch`, `PayrollBatchLine`, `Loan`
- `app/modules/credit/services/repayment.py` — `apply_repayment` signature
- `app/modules/credit/executors.py` — executor pattern
- `app/modules/maker_checker/service.py` — `ApprovalService.submit` / `approve`

---

## Task 1: PayrollBatchService — submit

**Files:**
- Create: `app/modules/credit/services/payroll.py`
- Create: `tests/modules/credit/test_payroll_service.py`

- [ ] **Step 1: Write failing tests for batch submission**

```python
# tests/modules/credit/test_payroll_service.py
"""Tests for PayrollBatchService — CSV/JSON submit, apply, error handling."""
from __future__ import annotations

import io
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.modules.credit.models import PayrollBatch, PayrollBatchLine


TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


def _csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    buf.write("member_id,amount\n")
    for r in rows:
        buf.write(f"{r['member_id']},{r['amount']}\n")
    return buf.getvalue().encode()


@pytest.mark.anyio
async def test_submit_json_batch_creates_preview(test_engine: AsyncEngine) -> None:
    """JSON submission creates a batch with matched/unmatched lines."""
    from tests.modules.credit.test_service import _setup_disbursed_loan
    factory = _factory(test_engine)

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)
        member_id = loan.member_id

        # One matched (valid loan), one unmatched (no loan)
        rows = [
            {"member_id": str(member_id), "amount": "500.00"},
            {"member_id": str(uuid.uuid4()), "amount": "200.00"},  # unknown member
        ]

        from app.modules.credit.services.payroll import PayrollBatchService
        from app.modules.ledger.models import ChartOfAccount
        clearing_acct = await session.scalar(select(ChartOfAccount).limit(1))

        svc = PayrollBatchService(session)
        batch = await svc.submit_batch(
            rows=rows,
            source_format="json",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            clearing_account_id=clearing_acct.id,
        )
        await session.commit()

    assert batch.total_rows == 2
    assert batch.matched_rows == 1
    assert batch.unmatched_rows == 1
    assert batch.total_amount == Decimal("500.00")
    assert batch.status == "pending_review"


@pytest.mark.anyio
async def test_submit_csv_batch_creates_preview(test_engine: AsyncEngine) -> None:
    """CSV submission produces the same result as JSON."""
    from tests.modules.credit.test_service import _setup_disbursed_loan
    factory = _factory(test_engine)

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)

        csv_data = _csv_bytes([
            {"member_id": str(loan.member_id), "amount": "750.00"},
        ])

        from app.modules.credit.services.payroll import PayrollBatchService
        from app.modules.ledger.models import ChartOfAccount
        clearing_acct = await session.scalar(select(ChartOfAccount).limit(1))

        svc = PayrollBatchService(session)
        batch = await svc.submit_batch_csv(
            csv_bytes=csv_data,
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            clearing_account_id=clearing_acct.id,
        )
        await session.commit()

    assert batch.matched_rows == 1
    assert batch.total_amount == Decimal("750.00")


@pytest.mark.anyio
async def test_apply_batch_applies_matched_lines(test_engine: AsyncEngine) -> None:
    """After approval, apply_batch posts repayments for all matched lines."""
    from tests.modules.credit.test_service import _setup_disbursed_loan
    factory = _factory(test_engine)

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)

        from app.modules.credit.services.payroll import PayrollBatchService
        from app.modules.ledger.models import ChartOfAccount
        clearing_acct = await session.scalar(select(ChartOfAccount).limit(1))

        svc = PayrollBatchService(session)
        batch = await svc.submit_batch(
            rows=[{"member_id": str(loan.member_id), "amount": "500.00"}],
            source_format="json",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            clearing_account_id=clearing_acct.id,
        )
        # Simulate approval by setting status directly
        batch.status = "approved"
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        from app.modules.credit.services.payroll import PayrollBatchService
        svc = PayrollBatchService(session)
        await svc.apply_batch(batch_id=batch.id, actor_id=uuid.uuid4())

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        batch_reloaded = await session.get(PayrollBatch, batch.id)
        assert batch_reloaded.status == "applied"

        lines = (await session.execute(
            select(PayrollBatchLine).where(PayrollBatchLine.payroll_batch_id == batch.id)
        )).scalars().all()
        applied_lines = [l for l in lines if l.status == "applied"]
        assert len(applied_lines) == 1
        assert applied_lines[0].repayment_id is not None


@pytest.mark.anyio
async def test_apply_before_approval_raises(test_engine: AsyncEngine) -> None:
    from tests.modules.credit.test_service import _setup_disbursed_loan
    factory = _factory(test_engine)

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)

        from app.modules.credit.services.payroll import PayrollBatchService
        from app.modules.ledger.models import ChartOfAccount
        clearing_acct = await session.scalar(select(ChartOfAccount).limit(1))

        svc = PayrollBatchService(session)
        batch = await svc.submit_batch(
            rows=[{"member_id": str(loan.member_id), "amount": "500.00"}],
            source_format="json",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            clearing_account_id=clearing_acct.id,
        )
        await session.commit()

        with pytest.raises(ValueError, match="not approved"):
            await svc.apply_batch(batch_id=batch.id, actor_id=uuid.uuid4())
```

- [ ] **Step 2: Run to confirm failure**

```bash
venv/bin/pytest tests/modules/credit/test_payroll_service.py -v 2>&1 | head -20
```

Expected: ImportError — `PayrollBatchService` does not exist.

- [ ] **Step 3: Implement PayrollBatchService**

```python
# app/modules/credit/services/payroll.py
"""PayrollBatchService — CSV/JSON batch submission, preview, and application."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, UTC
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, PayrollBatch, PayrollBatchLine
from app.modules.maker_checker.service import ApprovalService

_log = structlog.get_logger(__name__)


class PayrollBatchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Submission ────────────────────────────────────────────────────────────

    async def submit_batch(
        self,
        *,
        rows: list[dict[str, str]],
        source_format: str,
        actor_id: uuid.UUID,
        idempotency_key: str,
        clearing_account_id: uuid.UUID,
    ) -> PayrollBatch:
        """Validate rows, create batch + lines, submit for approval."""
        # Idempotency guard
        existing = await self._session.scalar(
            select(PayrollBatch).where(PayrollBatch.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

        matched_rows, unmatched_rows, total_amount = await self._match_rows(rows)

        # Generate reference
        seq = await self._session.scalar(
            text("SELECT nextval('payroll_batch_number_seq')")
        )
        reference = f"PAY-{datetime.now(UTC).strftime('%Y%m')}-{seq:06d}"

        batch = PayrollBatch(
            reference=reference,
            status="pending_review",
            submitted_by=actor_id,
            total_rows=len(rows),
            matched_rows=len(matched_rows),
            unmatched_rows=len(unmatched_rows),
            total_amount=total_amount,
            source_format=source_format,
            idempotency_key=idempotency_key,
        )
        self._session.add(batch)
        await self._session.flush()

        for row in matched_rows + unmatched_rows:
            line = PayrollBatchLine(
                payroll_batch_id=batch.id,
                member_id=row.get("member_id"),
                raw_member_ref=row["raw_member_ref"],
                amount=Decimal(str(row["amount"])),
                loan_id=row.get("loan_id"),
                status=row["status"],
                error_reason=row.get("error_reason"),
            )
            self._session.add(line)

        await self._session.flush()

        # Submit for approval
        approval_svc = ApprovalService(self._session)
        request = await approval_svc.submit(
            operation_type="credit.apply_payroll_batch",
            payload={
                "batch_id": str(batch.id),
                "clearing_account_id": str(clearing_account_id),
            },
            requested_by=actor_id,
            required_approvals=1,
        )
        batch.approval_request_id = request.id
        await self._session.flush()

        _log.info(
            "credit.payroll_batch.submitted",
            batch_id=str(batch.id),
            matched=len(matched_rows),
            unmatched=len(unmatched_rows),
        )
        return batch

    async def submit_batch_csv(
        self,
        *,
        csv_bytes: bytes,
        actor_id: uuid.UUID,
        idempotency_key: str,
        clearing_account_id: uuid.UUID,
    ) -> PayrollBatch:
        """Parse CSV and delegate to submit_batch."""
        rows = self._parse_csv(csv_bytes)
        return await self.submit_batch(
            rows=rows,
            source_format="csv",
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            clearing_account_id=clearing_account_id,
        )

    def _parse_csv(self, csv_bytes: bytes) -> list[dict[str, str]]:
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        rows = []
        for row in reader:
            rows.append({"member_id": row.get("member_id", "").strip(),
                         "amount": row.get("amount", "").strip()})
        return rows

    async def _match_rows(
        self, rows: list[dict[str, str]]
    ) -> tuple[list[dict], list[dict], Decimal]:
        """For each row, find member + active loan. Returns (matched, unmatched, total)."""
        from app.modules.members.models import Member

        matched: list[dict] = []
        unmatched: list[dict] = []
        total = Decimal("0")

        for row in rows:
            raw_ref = str(row.get("member_id", "")).strip()
            amount_str = str(row.get("amount", "")).strip()

            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    raise ValueError("amount must be > 0")
            except Exception:
                unmatched.append({
                    "raw_member_ref": raw_ref,
                    "amount": amount_str or "0",
                    "status": "unmatched",
                    "error_reason": f"Invalid amount: {amount_str!r}",
                })
                continue

            # Try to find member by UUID
            member_id: uuid.UUID | None = None
            try:
                member_id = uuid.UUID(raw_ref)
            except ValueError:
                pass

            if member_id is None:
                unmatched.append({
                    "raw_member_ref": raw_ref,
                    "amount": str(amount),
                    "status": "unmatched",
                    "error_reason": "member_id is not a valid UUID",
                })
                continue

            # Find active loan for member
            loan = await self._session.scalar(
                select(Loan)
                .where(Loan.member_id == member_id)
                .where(Loan.status.in_(["disbursed", "in_arrears"]))
                .limit(1)
            )
            if loan is None:
                unmatched.append({
                    "raw_member_ref": raw_ref,
                    "member_id": member_id,
                    "amount": str(amount),
                    "status": "unmatched",
                    "error_reason": "no_active_loan",
                })
                continue

            matched.append({
                "raw_member_ref": raw_ref,
                "member_id": member_id,
                "amount": str(amount),
                "loan_id": loan.id,
                "status": "matched",
            })
            total += amount

        return matched, unmatched, total

    # ── Application ───────────────────────────────────────────────────────────

    async def apply_batch(
        self,
        *,
        batch_id: uuid.UUID,
        actor_id: uuid.UUID,
        clearing_account_id: uuid.UUID | None = None,
    ) -> PayrollBatch:
        """Apply all matched lines. Each line committed independently."""
        batch = await self._session.scalar(
            select(PayrollBatch).where(PayrollBatch.id == batch_id).with_for_update()
        )
        if batch is None:
            raise ValueError(f"PayrollBatch '{batch_id}' not found")
        if batch.status != "approved":
            raise ValueError(f"Batch '{batch_id}' is not approved — status: {batch.status}")

        lines = (await self._session.execute(
            select(PayrollBatchLine)
            .where(PayrollBatchLine.payroll_batch_id == batch_id)
            .where(PayrollBatchLine.status == "matched")
        )).scalars().all()

        from app.modules.credit.services.repayment import LoanRepaymentService

        for line in lines:
            idem_key = f"payroll-{batch_id}-{line.id}"
            try:
                repayment_svc = LoanRepaymentService(self._session)
                repayment = await repayment_svc.apply_repayment(
                    loan_id=line.loan_id,
                    amount=line.amount,
                    payment_account_id=clearing_account_id or uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    posted_by=actor_id,
                    narration=f"Payroll deduction batch {batch.reference}",
                    idempotency_key=idem_key,
                )
                line.status = "applied"
                line.repayment_id = repayment.id
            except Exception as exc:
                line.status = "error"
                line.error_reason = str(exc)
                _log.warning(
                    "credit.payroll_batch.line_error",
                    batch_id=str(batch_id),
                    line_id=str(line.id),
                    error=str(exc),
                )
            await self._session.commit()

        # Re-fetch batch after per-line commits
        batch = await self._session.get(PayrollBatch, batch_id)
        batch.status = "applied"
        await self._session.flush()

        from app.core.outbox import EventPublisher
        applied_count = sum(1 for l in lines if l.status == "applied")
        error_count = len(lines) - applied_count
        await EventPublisher.publish(
            self._session,
            aggregate_type="payroll_batch",
            aggregate_id=batch_id,
            event_type="PayrollBatchApplied",
            payload={
                "batch_id": str(batch_id),
                "applied_count": applied_count,
                "error_count": error_count,
                "total_amount": str(batch.total_amount),
            },
        )

        _log.info(
            "credit.payroll_batch.applied",
            batch_id=str(batch_id),
            applied=applied_count,
            errors=error_count,
        )
        return batch
```

- [ ] **Step 4: Run tests**

```bash
venv/bin/pytest tests/modules/credit/test_payroll_service.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/services/payroll.py tests/modules/credit/test_payroll_service.py
git commit -m "feat(credit): PayrollBatchService — CSV/JSON batch submit, preview, apply"
```

---

## Task 2: Register Executor

**Files:**
- Modify: `app/modules/credit/executors.py`

- [ ] **Step 1: Add payroll batch executor**

Append to `app/modules/credit/executors.py`:

```python
@approval_executor("credit.apply_payroll_batch")
async def execute_apply_payroll_batch(session: AsyncSession, payload: dict) -> dict:
    """Executor: called by ApprovalService when payroll batch is approved."""
    batch_id = uuid.UUID(payload["batch_id"])
    clearing_account_id = uuid.UUID(payload["clearing_account_id"])

    from app.modules.credit.services.payroll import PayrollBatchService  # noqa: PLC0415

    svc = PayrollBatchService(session)

    # Mark batch as approved before applying
    from app.modules.credit.models import PayrollBatch  # noqa: PLC0415
    batch = await session.get(PayrollBatch, batch_id)
    if batch is not None and batch.status == "pending_review":
        batch.status = "approved"
        await session.flush()

    await svc.apply_batch(
        batch_id=batch_id,
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        clearing_account_id=clearing_account_id,
    )
    return {"status": "applied", "batch_id": str(batch_id)}
```

- [ ] **Step 2: Verify import**

```bash
venv/bin/python -c "import app.modules.credit.executors; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/modules/credit/executors.py
git commit -m "feat(credit): register credit.apply_payroll_batch executor"
```

---

## Task 3: Payroll API Endpoints

**Files:**
- Modify: `app/modules/credit/schemas.py`
- Modify: `app/modules/credit/api.py`

- [ ] **Step 1: Add payroll schemas**

In `app/modules/credit/schemas.py`, append:

```python
# ── Payroll batch schemas ─────────────────────────────────────────────────────

class PayrollRowIn(BaseModel):
    member_id: str
    amount: Decimal

class PayrollBatchJsonIn(BaseModel):
    rows: list[PayrollRowIn]
    clearing_account_id: uuid.UUID
    idempotency_key: str

class PayrollBatchLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    raw_member_ref: str
    member_id: uuid.UUID | None
    loan_id: uuid.UUID | None
    amount: Decimal
    status: str
    error_reason: str | None

class PayrollBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    reference: str
    status: str
    total_rows: int
    matched_rows: int
    unmatched_rows: int
    total_amount: Decimal
    source_format: str
    approval_request_id: uuid.UUID | None
```

- [ ] **Step 2: Add payroll endpoints to api.py**

```python
@router.post("/payroll-batches", status_code=201)
async def submit_payroll_batch_json(
    body: PayrollBatchJsonIn,
    session: AsyncSession = Depends(get_tenant_session),
    actor_id: uuid.UUID = Depends(get_actor_id),
) -> PayrollBatchOut:
    from app.modules.credit.services.payroll import PayrollBatchService
    svc = PayrollBatchService(session)
    rows = [{"member_id": r.member_id, "amount": str(r.amount)} for r in body.rows]
    batch = await svc.submit_batch(
        rows=rows,
        source_format="json",
        actor_id=actor_id,
        idempotency_key=body.idempotency_key,
        clearing_account_id=body.clearing_account_id,
    )
    return PayrollBatchOut.model_validate(batch)


@router.post("/payroll-batches/csv", status_code=201)
async def submit_payroll_batch_csv(
    file: UploadFile,
    clearing_account_id: uuid.UUID,
    idempotency_key: str,
    session: AsyncSession = Depends(get_tenant_session),
    actor_id: uuid.UUID = Depends(get_actor_id),
) -> PayrollBatchOut:
    from fastapi import UploadFile  # already imported at top of api.py if not, add it
    from app.modules.credit.services.payroll import PayrollBatchService
    svc = PayrollBatchService(session)
    contents = await file.read()
    batch = await svc.submit_batch_csv(
        csv_bytes=contents,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        clearing_account_id=clearing_account_id,
    )
    return PayrollBatchOut.model_validate(batch)


@router.get("/payroll-batches/{batch_id}")
async def get_payroll_batch(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_session),
) -> PayrollBatchOut:
    from app.modules.credit.models import PayrollBatch
    batch = await session.get(PayrollBatch, batch_id)
    if batch is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Payroll batch not found")
    return PayrollBatchOut.model_validate(batch)


@router.post("/payroll-batches/{batch_id}/reject")
async def reject_payroll_batch(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_session),
    actor_id: uuid.UUID = Depends(get_actor_id),
) -> PayrollBatchOut:
    from app.modules.credit.models import PayrollBatch
    batch = await session.scalar(
        __import__("sqlalchemy", fromlist=["select"]).select(PayrollBatch)
        .where(PayrollBatch.id == batch_id).with_for_update()
    )
    if batch is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Payroll batch not found")
    if batch.status != "pending_review":
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail=f"Batch status is '{batch.status}'")
    batch.status = "rejected"
    batch.approved_by = actor_id
    return PayrollBatchOut.model_validate(batch)
```

Note: The approve endpoint is handled by the existing maker-checker `POST /maker-checker/requests/{id}/approve`. The payroll batch executor fires automatically when quorum is met.

- [ ] **Step 3: Add `UploadFile` import to api.py**

At the top of `app/modules/credit/api.py`, ensure:
```python
from fastapi import Depends, HTTPException, UploadFile
```

- [ ] **Step 4: Run full credit tests**

```bash
venv/bin/pytest tests/modules/credit/ -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/schemas.py app/modules/credit/api.py
git commit -m "feat(credit): payroll batch API endpoints — JSON submit, CSV upload, get, reject"
```

---

## Verification Criteria

```bash
venv/bin/pytest tests/modules/credit/test_payroll_service.py -v
venv/bin/pytest tests/modules/credit/ -q  # no regressions
venv/bin/python -c "from app.main import app; print('OK')"
```
