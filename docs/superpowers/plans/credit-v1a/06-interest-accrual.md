# Sub-plan 06 — Interest Accrual

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Implement the `accrue_reducing_balance_interest` Celery beat task. For each
active tenant, iterates over `disbursed` and `in_arrears` reducing-balance loans with
installments due today that have not yet had interest accrued. Posts a GL entry
(Dr interest_receivable / Cr interest_income) and increments `loans.accrued_interest`.
Flat-method loans are skipped (interest was fully booked at disbursement in sub-plan 04).

**Architecture:** Follows the `fees/beat.py` per-tenant pattern exactly: outer async
runner iterates tenant schemas, inner `_accrue_for_tenant()` opens one session per tenant,
loops over eligible loans, uses `session.begin_nested()` per loan for fault isolation.
Idempotency key: `"loan-accrue-{loan_id}-{due_date.isoformat()}"`.

**Tech Stack:** Celery, SQLAlchemy 2.0 async, `begin_nested()` for per-loan savepoints

---

## Required Reading

- Sub-plans 01, 04, 05 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §5.2, §8
- `app/modules/fees/beat.py` — per-tenant Celery beat task pattern (full file)
- `app/workers/celery_app.py` — beat schedule registration

---

## File Map

```
New
  app/modules/credit/beat.py      accrue_reducing_balance_interest task

Modified
  app/workers/celery_app.py       add credit.beat to include list + beat schedule entries
  tests/modules/credit/test_service.py    append accrual tests
```

---

## Task 1 — `accrue_reducing_balance_interest` Beat Task (TDD)

**Files:**
- Modify: `tests/modules/credit/test_service.py`
- Create: `app/modules/credit/beat.py`

- [ ] **Step 1: Append failing accrual tests to `tests/modules/credit/test_service.py`**

Add imports at top:

```python
from datetime import date, timedelta
from app.modules.credit.services.disbursement import LoanDisbursementService
```

Append tests:

```python
# ── Interest accrual tests ────────────────────────────────────────────────────


async def _make_disbursed_loan(
    engine: AsyncEngine,
    accounts: dict,
    interest_method: str = "reducing_balance",
) -> Loan:
    """Create and disburse a loan. Returns the Loan object."""
    application, product = await _make_approved_application(
        engine, accounts, interest_method
    )
    session = await _new_session(engine)
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=f"accrual-disb-{uuid.uuid4()}",
        )
        await session.commit()
        return loan
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_accrue_interest_posts_gl_entry(test_engine):
    """Reducing balance: accrual for a loan with an installment due today posts a GL entry."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    # Manually backdate first installment due_date to today to trigger accrual.
    today = date.today()
    session = await _new_session(test_engine)
    try:
        installments = list(
            (await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )).scalars().all()
        )
        installments[0].due_date = today
        await session.commit()
    finally:
        await session.close()

    # Import and call the inner accrual function directly (skips Celery infrastructure).
    from app.modules.credit.beat import _accrue_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    # Verify accrued_interest snapshot updated.
    session2 = await _new_session(test_engine)
    try:
        updated_loan = await session2.get(Loan, loan.id)
        assert updated_loan.accrued_interest > Decimal("0")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_accrue_interest_idempotent(test_engine):
    """Running accrual twice on the same day does not double-post."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    today = date.today()
    session = await _new_session(test_engine)
    try:
        installments = list(
            (await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )).scalars().all()
        )
        installments[0].due_date = today
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _accrue_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine)  # second run
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        updated_loan = await session2.get(Loan, loan.id)
        # accrued_interest should not be doubled
        first_run_interest = updated_loan.accrued_interest
        assert first_run_interest > Decimal("0")
    finally:
        await session2.close()

    # Run a third time and check no double-accrual.
    _engine2 = _create_engine(get_settings().database_url)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine2)
    await _engine2.dispose()

    session3 = await _new_session(test_engine)
    try:
        final_loan = await session3.get(Loan, loan.id)
        assert final_loan.accrued_interest == first_run_interest
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_accrue_skips_flat_loans(test_engine):
    """Flat method loans: accrual task does nothing (interest booked at disbursement)."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    today = date.today()
    session = await _new_session(test_engine)
    try:
        installments = list(
            (await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )).scalars().all()
        )
        installments[0].due_date = today
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _accrue_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        updated_loan = await session2.get(Loan, loan.id)
        # Flat loan: accrued_interest stays 0 (interest already in interest_receivable from disbursement)
        assert updated_loan.accrued_interest == Decimal("0")
    finally:
        await session2.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_service.py -k "accrue" -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.modules.credit.beat'`

- [ ] **Step 3: Create `app/modules/credit/beat.py`**

```python
# app/modules/credit/beat.py
"""Celery beat tasks for the credit module.

Tasks:
    accrue_reducing_balance_interest  — daily
    mark_loans_in_arrears             — daily (added in sub-plan 09)
    reconcile_loan_snapshots          — daily (added in sub-plan 11)
"""
from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
_SYSTEM_ACTOR = uuid.UUID("00000000-0000-0000-0000-000000000000")


async def _accrue_for_tenant(schema_name: str, engine) -> int:
    """Accrue reducing-balance interest for all eligible loans in one tenant.

    Eligible: status IN ('disbursed', 'in_arrears'), interest_method='reducing_balance',
    with at least one installment where due_date <= today AND interest has not yet been
    accrued for that period (idempotency via LedgerService idempotency_key check).

    Returns count of accruals posted.
    """
    from app.modules.credit.models import Loan, LoanInstallment
    from app.modules.ledger.service import LedgerService

    factory = async_sessionmaker(engine, expire_on_commit=False)
    today = date.today()
    accrued_count = 0

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )

        # Fetch all eligible reducing-balance loans.
        loans = list(
            (
                await session.execute(
                    select(Loan).where(
                        Loan.interest_method == "reducing_balance",
                        Loan.status.in_(["disbursed", "in_arrears"]),
                    )
                )
            ).scalars().all()
        )

        for loan in loans:
            # Find installments due today or earlier that have not yet been accrued.
            # Idempotency: use "loan-accrue-{loan_id}-{due_date}" as the key.
            installments = list(
                (
                    await session.execute(
                        select(LoanInstallment).where(
                            LoanInstallment.loan_id == loan.id,
                            LoanInstallment.due_date <= today,
                            LoanInstallment.status.in_(["pending", "partial", "overdue"]),
                        ).order_by(LoanInstallment.due_date)
                    )
                ).scalars().all()
            )

            for installment in installments:
                idem_key = f"loan-accrue-{loan.id}-{installment.due_date.isoformat()}"

                # Check idempotency: has this period already been accrued?
                from app.modules.ledger.models import JournalEntry as _JE

                existing = await session.scalar(
                    select(_JE).where(_JE.idempotency_key == idem_key)
                )
                if existing is not None:
                    continue  # already accrued for this period

                period_interest = installment.interest_due
                if period_interest <= Decimal("0"):
                    continue

                try:
                    async with session.begin_nested():
                        ledger_svc = LedgerService(session)
                        await ledger_svc.post_journal_entry(
                            reference=f"LOAN-ACCRUE-{loan.id}-P{installment.period_number}",
                            description=(
                                f"Interest accrual: {loan.loan_reference} period {installment.period_number}"
                            ),
                            posted_by=_SYSTEM_ACTOR,
                            idempotency_key=idem_key,
                            lines=[
                                {
                                    "account_id": loan.gl_interest_receivable_id,
                                    "debit_amount": period_interest,
                                    "credit_amount": Decimal("0"),
                                    "sub_ledger_type": "loan",
                                    "sub_ledger_id": loan.id,
                                },
                                {
                                    "account_id": loan.gl_interest_income_id,
                                    "debit_amount": Decimal("0"),
                                    "credit_amount": period_interest,
                                    "sub_ledger_type": "loan",
                                    "sub_ledger_id": loan.id,
                                },
                            ],
                        )
                        loan.accrued_interest = loan.accrued_interest + period_interest
                        accrued_count += 1
                except Exception as exc:
                    _log.error(
                        "credit.beat.accrue_error",
                        schema=schema_name,
                        loan_id=str(loan.id),
                        period=installment.period_number,
                        error=str(exc),
                    )

        await session.commit()

    return accrued_count


async def _run_accrue_interest() -> dict[str, int]:
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
                count = await _accrue_for_tenant(schema_name, engine)
                if count:
                    totals[schema_name] = count
            except Exception as exc:
                _log.error(
                    "credit.beat.accrue_tenant_error",
                    schema=schema_name,
                    error=str(exc),
                )
    finally:
        await engine.dispose()
    _log.info("credit.beat.accrue_interest_complete", **totals)
    return totals


@celery_app.task(name="app.modules.credit.beat.accrue_reducing_balance_interest")  # type: ignore[misc]
def accrue_reducing_balance_interest() -> dict[str, int]:
    """Daily: accrue interest for reducing-balance loans with installments due today."""
    return asyncio.run(_run_accrue_interest())
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/modules/credit/test_service.py -k "accrue" -v
```

Expected: all 3 accrual tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/beat.py tests/modules/credit/test_service.py
git commit -m "feat(credit): accrue_reducing_balance_interest beat task"
```

---

## Task 2 — Register Beat Task in Celery App

**Files:**
- Modify: `app/workers/celery_app.py`

- [ ] **Step 1: Add credit module to celery include list and beat schedule**

In `app/workers/celery_app.py`, add `"app.modules.credit.beat"` to the `include` list:

```python
celery_app = Celery(
    "sacco",
    broker=settings.redis_url,
    include=[
        "app.core.outbox.worker",
        "app.core.outbox.retention",
        "app.platform_.provisioning.tasks",
        "app.modules.iam.beat",
        "app.modules.fees.consumer",
        "app.modules.fees.beat",
        "app.modules.credit.beat",      # ← add this
    ],
)
```

Add to `beat_schedule`:

```python
        "accrue-reducing-balance-interest": {
            "task": "app.modules.credit.beat.accrue_reducing_balance_interest",
            "schedule": 24 * 3600.0,  # daily
        },
```

- [ ] **Step 2: Verify celery app imports**

```bash
python -c "from app.workers.celery_app import celery_app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/workers/celery_app.py
git commit -m "feat(credit): register accrue_reducing_balance_interest in celery beat schedule"
```

---

## Verification Criteria

```bash
# 1. Accrual tests pass
pytest tests/modules/credit/test_service.py -k "accrue" -v

# 2. Full suite — no regressions
pytest -x -q

# 3. Beat task registered
python -c "
from app.workers.celery_app import celery_app
schedule = celery_app.conf.beat_schedule
assert 'accrue-reducing-balance-interest' in schedule
print('Beat task registered OK')
"
```

All commands must exit 0. Confirm:
- Reducing-balance loan with installment due today: `accrued_interest > 0` after task run
- Running task twice on same day: `accrued_interest` unchanged on second run (idempotent)
- Flat method loan: `accrued_interest` stays `0` (task skips it)
- All GL lines tagged `sub_ledger_type='loan'`
