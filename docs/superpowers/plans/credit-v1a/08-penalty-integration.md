# Sub-plan 08 — Penalty Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Implement the credit module's outbox consumer for fee events and the
`CreditQueryService.find_loans_eligible_for_fee` method. The consumer updates
`loans.accrued_penalties` / `total_paid_penalties` when `FeeAssessmentCreated` /
`FeeCollectionCreated` events arrive with `target_type='loan'`. Zero direct imports
from any fees service.

**Architecture:** Follows `app/modules/fees/consumer.py` pattern exactly: outer async
runner iterates tenant schemas, `_process_tenant_events` opens one session per tenant,
`session.begin_nested()` per event, `processed_events` table for idempotency.

**Tech Stack:** Celery, SQLAlchemy 2.0 async, outbox consumer pattern

---

## Required Reading

- Sub-plans 01, 04, 07 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §2.3 (Penalties)
- `app/modules/fees/consumer.py` — full file (pattern to follow exactly)
- `app/modules/fees/models.py` — `FeeAssessment` fields (`target_type`, `target_id`, `amount`)
- `app/core/outbox/models.py` — `TenantOutboxEvent` structure

---

## File Map

```
New
  app/modules/credit/consumer.py        outbox consumer
  app/modules/credit/services/query.py  CreditQueryService

Modified
  app/workers/celery_app.py             add credit.consumer to include list + beat schedule
  tests/modules/credit/test_service.py  append penalty + query tests
```

---

## Task 1 — `CreditQueryService.find_loans_eligible_for_fee` (TDD)

**Files:**
- Modify: `tests/modules/credit/test_service.py`
- Create: `app/modules/credit/services/query.py`

- [ ] **Step 1: Append failing query tests to `tests/modules/credit/test_service.py`**

Add import at top:

```python
from app.modules.credit.services.query import CreditQueryService
```

Append tests:

```python
# ── CreditQueryService tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_loans_eligible_for_fee_overdue(test_engine):
    """Loans with overdue installments appear in the eligibility query."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    # Backdate ALL installments to simulate fully overdue loan.
    yesterday = date.today() - timedelta(days=1)
    session = await _new_session(test_engine)
    try:
        installments = list(
            (await session.execute(
                sa_select(LoanInstallment).where(LoanInstallment.loan_id == loan.id)
            )).scalars().all()
        )
        for inst in installments:
            inst.due_date = yesterday
            inst.status = "overdue"
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = CreditQueryService(session2)
        eligible = await svc.find_loans_eligible_for_fee(
            as_of_date=date.today(),
            min_days_past_due=0,
        )
        loan_ids = [e["loan_id"] for e in eligible]
        assert loan.id in loan_ids
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_find_loans_eligible_for_fee_not_overdue(test_engine):
    """Loans with no overdue installments do not appear in eligibility query."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")
    # All installments have future due dates (default from disbursement).

    session = await _new_session(test_engine)
    try:
        svc = CreditQueryService(session)
        eligible = await svc.find_loans_eligible_for_fee(
            as_of_date=date.today(),
            min_days_past_due=0,
        )
        loan_ids = [e["loan_id"] for e in eligible]
        assert loan.id not in loan_ids
    finally:
        await session.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_service.py -k "find_loans_eligible" -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.modules.credit.services.query'`

- [ ] **Step 3: Create `app/modules/credit/services/query.py`**

```python
# app/modules/credit/services/query.py
"""Read-only queries used by external callers (fees engine, reporting)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanInstallment

_log = structlog.get_logger(__name__)


class CreditQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_loans_eligible_for_fee(
        self,
        *,
        as_of_date: date,
        min_days_past_due: int = 0,
    ) -> list[dict[str, Any]]:
        """Return loans with at least one overdue installment.

        Called by the fees engine's schedule job to determine which loans
        are eligible for a penalty fee type.

        Returns:
            List of dicts with keys:
              - loan_id: UUID
              - member_id: UUID
              - outstanding_principal: Decimal
              - days_past_due: int (days since earliest overdue installment)
        """
        from sqlalchemy import and_, cast, Integer
        from sqlalchemy.dialects.postgresql import INTERVAL

        # Find loans in disbursed/in_arrears status with overdue installments.
        rows = list(
            (
                await self._session.execute(
                    select(
                        Loan.id.label("loan_id"),
                        Loan.member_id,
                        Loan.outstanding_principal,
                        func.min(LoanInstallment.due_date).label("earliest_due"),
                    )
                    .join(LoanInstallment, LoanInstallment.loan_id == Loan.id)
                    .where(
                        Loan.status.in_(["disbursed", "in_arrears"]),
                        LoanInstallment.due_date < as_of_date,
                        LoanInstallment.status.in_(["pending", "partial", "overdue"]),
                    )
                    .group_by(Loan.id, Loan.member_id, Loan.outstanding_principal)
                )
            ).all()
        )

        result = []
        for row in rows:
            days_past_due = (as_of_date - row.earliest_due).days
            if days_past_due >= min_days_past_due:
                result.append(
                    {
                        "loan_id": row.loan_id,
                        "member_id": row.member_id,
                        "outstanding_principal": row.outstanding_principal,
                        "days_past_due": days_past_due,
                    }
                )
        return result
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/modules/credit/test_service.py -k "find_loans_eligible" -v
```

Expected: both query tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/services/query.py tests/modules/credit/test_service.py
git commit -m "feat(credit): CreditQueryService.find_loans_eligible_for_fee"
```

---

## Task 2 — Outbox Consumer for Fee Events (TDD)

**Files:**
- Modify: `tests/modules/credit/test_service.py`
- Create: `app/modules/credit/consumer.py`

- [ ] **Step 1: Append failing consumer tests to `tests/modules/credit/test_service.py`**

Append tests:

```python
# ── Penalty consumer tests ────────────────────────────────────────────────────


async def _insert_outbox_event(
    engine: AsyncEngine,
    event_type: str,
    payload: dict,
) -> uuid.UUID:
    """Insert a TenantOutboxEvent directly for testing."""
    import json
    event_id = uuid.uuid4()
    session = await _new_session(engine)
    try:
        await session.execute(
            text(
                "INSERT INTO outbox_events (id, event_type, payload, occurred_at, published_at) "
                "VALUES (:id, :etype, :payload::jsonb, now(), NULL)"
            ),
            {"id": event_id, "etype": event_type, "payload": json.dumps(payload)},
        )
        await session.commit()
    finally:
        await session.close()
    return event_id


@pytest.mark.asyncio
async def test_consumer_fee_assessment_increments_accrued_penalties(test_engine):
    """FeeAssessmentCreated with target_type='loan' increments loans.accrued_penalties."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    assessment_id = uuid.uuid4()
    penalty_amount = Decimal("500.00")
    event_id = await _insert_outbox_event(
        test_engine,
        "FeeAssessmentCreated",
        {
            "assessment_id": str(assessment_id),
            "target_type": "loan",
            "target_id": str(loan.id),
            "amount": str(penalty_amount),
        },
    )

    from app.modules.credit.consumer import _process_tenant_events
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _process_tenant_events(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session = await _new_session(test_engine)
    try:
        updated = await session.get(Loan, loan.id)
        assert updated.accrued_penalties == penalty_amount
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_consumer_fee_assessment_idempotent(test_engine):
    """Replaying FeeAssessmentCreated does not double-increment accrued_penalties."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    penalty_amount = Decimal("300.00")
    event_id = await _insert_outbox_event(
        test_engine,
        "FeeAssessmentCreated",
        {
            "assessment_id": str(uuid.uuid4()),
            "target_type": "loan",
            "target_id": str(loan.id),
            "amount": str(penalty_amount),
        },
    )

    from app.modules.credit.consumer import _process_tenant_events
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings

    _engine = _create_engine(get_settings().database_url)
    await _process_tenant_events(TEST_TENANT_SCHEMA, _engine)
    await _process_tenant_events(TEST_TENANT_SCHEMA, _engine)  # replay
    await _engine.dispose()

    session = await _new_session(test_engine)
    try:
        updated = await session.get(Loan, loan.id)
        assert updated.accrued_penalties == penalty_amount  # not doubled
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_consumer_fee_collection_decrements_accrued_penalties(test_engine):
    """FeeCollectionCreated with target_type='loan' decrements accrued_penalties, increments total_paid_penalties."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    # Set up accrued_penalties manually.
    penalty_amount = Decimal("200.00")
    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.accrued_penalties = penalty_amount
        await session.commit()
    finally:
        await session.close()

    collected_amount = Decimal("150.00")
    await _insert_outbox_event(
        test_engine,
        "FeeCollectionCreated",
        {
            "collection_id": str(uuid.uuid4()),
            "target_type": "loan",
            "target_id": str(loan.id),
            "amount_collected": str(collected_amount),
        },
    )

    from app.modules.credit.consumer import _process_tenant_events
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _process_tenant_events(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.accrued_penalties == penalty_amount - collected_amount
        assert updated.total_paid_penalties == collected_amount
    finally:
        await session2.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_service.py -k "consumer" -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.modules.credit.consumer'`

- [ ] **Step 3: Create `app/modules/credit/consumer.py`**

```python
# app/modules/credit/consumer.py
"""Credit module outbox consumer.

Handles fee events where target_type='loan':
  - FeeAssessmentCreated → increment loans.accrued_penalties
  - FeeCollectionCreated → decrement loans.accrued_penalties, increment total_paid_penalties
"""
from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
_CONSUMER_NAME = "credit.event_consumer"
_BATCH = 50
_HANDLED_EVENTS = {"FeeAssessmentCreated", "FeeCollectionCreated"}


async def _process_tenant_events(schema_name: str, engine) -> int:
    """Process unhandled fee events for one tenant schema.

    Returns count of events processed.
    """
    from app.core.outbox.models import TenantOutboxEvent
    from app.modules.credit.models import Loan

    factory = async_sessionmaker(engine, expire_on_commit=False)
    processed = 0

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )

        rows = list(
            (
                await session.execute(
                    select(TenantOutboxEvent)
                    .where(
                        TenantOutboxEvent.event_type.in_(_HANDLED_EVENTS),
                        ~TenantOutboxEvent.id.in_(
                            select(text("event_id"))
                            .select_from(text("processed_events"))
                            .where(text(f"consumer_name = '{_CONSUMER_NAME}'"))  # noqa: S608
                        ),
                    )
                    .order_by(TenantOutboxEvent.occurred_at)
                    .limit(_BATCH)
                )
            ).scalars().all()
        )

        for event in rows:
            try:
                async with session.begin_nested():
                    already = await session.scalar(
                        text(
                            "SELECT 1 FROM processed_events "
                            "WHERE event_id = :eid AND consumer_name = :cn"
                        ),
                        {"eid": event.id, "cn": _CONSUMER_NAME},
                    )
                    if already:
                        continue

                    payload = event.payload
                    target_type = payload.get("target_type")
                    if target_type != "loan":
                        # Mark processed but do nothing (not a loan event).
                        pass
                    else:
                        await _handle_loan_fee_event(session, event.event_type, payload)

                    await session.execute(
                        text(
                            "INSERT INTO processed_events (event_id, consumer_name, processed_at) "
                            "VALUES (:eid, :cn, now())"
                        ),
                        {"eid": event.id, "cn": _CONSUMER_NAME},
                    )
                    processed += 1
            except Exception as exc:
                _log.error(
                    "credit.consumer.event_error",
                    event_id=str(event.id),
                    event_type=event.event_type,
                    schema=schema_name,
                    error=str(exc),
                )

        await session.commit()

    return processed


async def _handle_loan_fee_event(session, event_type: str, payload: dict) -> None:
    """Update loan penalty snapshot fields based on fee event."""
    from app.modules.credit.models import Loan

    loan_id = uuid.UUID(payload["target_id"])

    loan = await session.scalar(
        select(Loan).where(Loan.id == loan_id).with_for_update()
    )
    if loan is None:
        _log.warning("credit.consumer.loan_not_found", loan_id=str(loan_id))
        return

    if event_type == "FeeAssessmentCreated":
        amount = Decimal(str(payload["amount"]))
        loan.accrued_penalties = loan.accrued_penalties + amount
        _log.info(
            "credit.consumer.penalties_incremented",
            loan_id=str(loan_id),
            amount=str(amount),
        )

    elif event_type == "FeeCollectionCreated":
        collected = Decimal(str(payload["amount_collected"]))
        # Floor at zero — should never go negative.
        new_accrued = max(Decimal("0"), loan.accrued_penalties - collected)
        loan.accrued_penalties = new_accrued
        loan.total_paid_penalties = loan.total_paid_penalties + collected
        _log.info(
            "credit.consumer.penalties_collected",
            loan_id=str(loan_id),
            amount=str(collected),
        )


async def _run_consume_credit_events() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    totals: dict[str, int] = {}
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            schemas = [row[0] for row in result.fetchall()]
        for schema_name in schemas:
            if not _SCHEMA_RE.match(schema_name):
                continue
            try:
                count = await _process_tenant_events(schema_name, engine)
                if count:
                    totals[schema_name] = count
            except Exception as exc:
                _log.error(
                    "credit.consumer.tenant_error", schema=schema_name, error=str(exc)
                )
    finally:
        await engine.dispose()
    return totals


@celery_app.task(name="app.modules.credit.consumer.consume_credit_events")  # type: ignore[misc]
def consume_credit_events() -> dict[str, int]:
    """Every 60 s: process fee events targeting loans for all tenants."""
    return asyncio.run(_run_consume_credit_events())
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/modules/credit/test_service.py -k "consumer" -v
```

Expected: all 3 consumer tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/consumer.py tests/modules/credit/test_service.py
git commit -m "feat(credit): outbox consumer for FeeAssessmentCreated/FeeCollectionCreated"
```

---

## Task 3 — Register Consumer in Celery App

**Files:**
- Modify: `app/workers/celery_app.py`

- [ ] **Step 1: Add consumer to include list and beat schedule**

In `app/workers/celery_app.py`, add to `include`:

```python
        "app.modules.credit.consumer",
```

Add to `beat_schedule`:

```python
        "consume-credit-events": {
            "task": "app.modules.credit.consumer.consume_credit_events",
            "schedule": 60.0,  # every minute
        },
```

- [ ] **Step 2: Verify import**

```bash
python -c "from app.workers.celery_app import celery_app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/workers/celery_app.py
git commit -m "feat(credit): register consume_credit_events in celery beat schedule"
```

---

## Verification Criteria

```bash
# 1. Query tests pass
pytest tests/modules/credit/test_service.py -k "find_loans_eligible" -v

# 2. Consumer tests pass
pytest tests/modules/credit/test_service.py -k "consumer" -v

# 3. Full suite — no regressions
pytest -x -q

# 4. No direct fees service import in consumer
python -c "
import ast, sys
with open('app/modules/credit/consumer.py') as f:
    src = f.read()
if 'from app.modules.fees.service' in src or 'import FeeAssessmentService' in src:
    print('FAIL: direct fees service import found'); sys.exit(1)
print('OK: no direct fees service import')
"
```

All commands must exit 0. Confirm:
- `FeeAssessmentCreated` with `target_type='loan'` → `accrued_penalties` incremented
- `FeeCollectionCreated` with `target_type='loan'` → `accrued_penalties` decremented, `total_paid_penalties` incremented
- Consumer idempotent: replayed event → no second update
- `find_loans_eligible_for_fee` returns loans with overdue installments only
- No direct import of `app.modules.fees.service` in consumer
- `accrued_penalties` never goes below zero
