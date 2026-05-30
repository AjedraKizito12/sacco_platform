# Sub-plan 09 — Arrears and Derived Status

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Add `mark_loans_in_arrears` Celery beat task to `app/modules/credit/beat.py`.
Loans with any overdue installment transition `disbursed → in_arrears`. Loans where
all previously-overdue installments are now paid transition `in_arrears → disbursed`.

**Architecture:** Follows the `accrue_reducing_balance_interest` pattern in the same
`beat.py` file. Per-tenant inner function, `session.begin_nested()` per loan, idempotent
(status transition only fires if current status differs from derived status).

**Tech Stack:** Celery, SQLAlchemy 2.0 async

---

## Required Reading

- Sub-plans 01, 04, 07 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §4 (Status Machine), §8 (Beat Jobs)
- `app/modules/credit/beat.py` (partial — from sub-plan 06)

---

## File Map

```
Modified
  app/modules/credit/beat.py            add _mark_arrears_for_tenant + task
  app/workers/celery_app.py             add mark-loans-in-arrears to beat schedule
  tests/modules/credit/test_service.py  append arrears tests
```

---

## Task 1 — `mark_loans_in_arrears` Beat Task (TDD)

**Files:**
- Modify: `tests/modules/credit/test_service.py`
- Modify: `app/modules/credit/beat.py`

- [ ] **Step 1: Append failing arrears tests to `tests/modules/credit/test_service.py`**

Append tests:

```python
# ── Arrears beat task tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_in_arrears_when_installment_overdue(test_engine):
    """Loan with an overdue installment → status transitions to in_arrears."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")
    assert loan.status == "disbursed"

    # Backdate first installment to yesterday.
    yesterday = date.today() - timedelta(days=1)
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
        installment.due_date = yesterday
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _mark_arrears_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _mark_arrears_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.status == "in_arrears"
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_clear_arrears_when_caught_up(test_engine):
    """Loan in in_arrears with all installments now paid → status reverts to disbursed."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    # Force loan into in_arrears.
    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.status = "in_arrears"
        await session.commit()
    finally:
        await session.close()

    # Mark all installments as paid to simulate caught up.
    from datetime import timezone
    session2 = await _new_session(test_engine)
    try:
        installments = list(
            (await session2.execute(
                sa_select(LoanInstallment).where(LoanInstallment.loan_id == loan.id)
            )).scalars().all()
        )
        for inst in installments:
            inst.status = "paid"
            inst.principal_paid = inst.principal_due
            inst.interest_paid = inst.interest_due
        await session2.commit()
    finally:
        await session2.close()

    from app.modules.credit.beat import _mark_arrears_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _mark_arrears_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session3 = await _new_session(test_engine)
    try:
        updated = await session3.get(Loan, loan.id)
        assert updated.status == "disbursed"
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_arrears_task_idempotent(test_engine):
    """Running arrears task twice → no double status flips."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    yesterday = date.today() - timedelta(days=1)
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
        installment.due_date = yesterday
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _mark_arrears_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _mark_arrears_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _mark_arrears_for_tenant(TEST_TENANT_SCHEMA, _engine)  # second run
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.status == "in_arrears"
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_arrears_task_skips_closed_written_off(test_engine):
    """Closed and written_off loans are excluded from arrears processing."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    # Force closed.
    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.status = "closed"
        await session.commit()
    finally:
        await session.close()

    # Backdate installment so it looks overdue.
    yesterday = date.today() - timedelta(days=1)
    session2 = await _new_session(test_engine)
    try:
        inst = (
            await session2.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .limit(1)
            )
        ).scalars().first()
        inst.due_date = yesterday
        await session2.commit()
    finally:
        await session2.close()

    from app.modules.credit.beat import _mark_arrears_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _mark_arrears_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session3 = await _new_session(test_engine)
    try:
        updated = await session3.get(Loan, loan.id)
        # Status must remain 'closed' — arrears task should not touch it.
        assert updated.status == "closed"
    finally:
        await session3.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_service.py -k "arrears" -v
```

Expected: `FAILED` — `ImportError: cannot import name '_mark_arrears_for_tenant'`

- [ ] **Step 3: Add `_mark_arrears_for_tenant` to `app/modules/credit/beat.py`**

Append to the existing `beat.py` (after the accrual task):

```python
# ── Arrears marking ───────────────────────────────────────────────────────────


async def _mark_arrears_for_tenant(schema_name: str, engine) -> int:
    """Set/clear in_arrears status for all active loans in one tenant.

    Returns count of loans whose status changed.
    """
    from app.modules.credit.models import Loan, LoanInstallment

    factory = async_sessionmaker(engine, expire_on_commit=False)
    today = date.today()
    changed_count = 0

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )

        # Fetch all active (disbursed + in_arrears) loans.
        loans = list(
            (
                await session.execute(
                    select(Loan).where(Loan.status.in_(["disbursed", "in_arrears"]))
                )
            ).scalars().all()
        )

        for loan in loans:
            try:
                async with session.begin_nested():
                    # Check for any overdue unpaid installments.
                    overdue_count = await session.scalar(
                        select(func.count()).select_from(LoanInstallment).where(
                            LoanInstallment.loan_id == loan.id,
                            LoanInstallment.due_date < today,
                            LoanInstallment.status.in_(["pending", "partial", "overdue"]),
                        )
                    )
                    has_overdue = (overdue_count or 0) > 0

                    if has_overdue and loan.status == "disbursed":
                        # Mark overdue installments as overdue status.
                        overdue_insts = list(
                            (
                                await session.execute(
                                    select(LoanInstallment).where(
                                        LoanInstallment.loan_id == loan.id,
                                        LoanInstallment.due_date < today,
                                        LoanInstallment.status.in_(["pending", "partial"]),
                                    )
                                )
                            ).scalars().all()
                        )
                        for inst in overdue_insts:
                            inst.status = "overdue"
                        loan.status = "in_arrears"
                        changed_count += 1

                    elif not has_overdue and loan.status == "in_arrears":
                        loan.status = "disbursed"
                        changed_count += 1

                    # Already in correct status — no change needed.

            except Exception as exc:
                _log.error(
                    "credit.beat.arrears_error",
                    schema=schema_name,
                    loan_id=str(loan.id),
                    error=str(exc),
                )

        await session.commit()

    return changed_count


async def _run_mark_arrears() -> dict[str, int]:
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
                count = await _mark_arrears_for_tenant(schema_name, engine)
                if count:
                    totals[schema_name] = count
            except Exception as exc:
                _log.error(
                    "credit.beat.arrears_tenant_error",
                    schema=schema_name,
                    error=str(exc),
                )
    finally:
        await engine.dispose()
    _log.info("credit.beat.mark_arrears_complete", **totals)
    return totals


@celery_app.task(name="app.modules.credit.beat.mark_loans_in_arrears")  # type: ignore[misc]
def mark_loans_in_arrears() -> dict[str, int]:
    """Daily: transition disbursed ↔ in_arrears based on overdue installments."""
    return asyncio.run(_run_mark_arrears())
```

Also add `func` to the existing `sqlalchemy` import at the top of `beat.py`:

```python
from sqlalchemy import func, select, text
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/modules/credit/test_service.py -k "arrears" -v
```

Expected: all 4 arrears tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/beat.py tests/modules/credit/test_service.py
git commit -m "feat(credit): mark_loans_in_arrears beat task"
```

---

## Task 2 — Register Beat Task in Celery App

**Files:**
- Modify: `app/workers/celery_app.py`

- [ ] **Step 1: Add to beat schedule**

Add to `beat_schedule` in `app/workers/celery_app.py`:

```python
        "mark-loans-in-arrears": {
            "task": "app.modules.credit.beat.mark_loans_in_arrears",
            "schedule": 24 * 3600.0,  # daily
        },
```

- [ ] **Step 2: Verify import**

```bash
python -c "
from app.workers.celery_app import celery_app
assert 'mark-loans-in-arrears' in celery_app.conf.beat_schedule
print('Beat task registered OK')
"
```

Expected: `Beat task registered OK`

- [ ] **Step 3: Commit**

```bash
git add app/workers/celery_app.py
git commit -m "feat(credit): register mark_loans_in_arrears in celery beat schedule"
```

---

## Verification Criteria

```bash
# 1. Arrears tests pass
pytest tests/modules/credit/test_service.py -k "arrears" -v

# 2. Beat task registered
python -c "
from app.workers.celery_app import celery_app
assert 'mark-loans-in-arrears' in celery_app.conf.beat_schedule
print('OK')
"

# 3. Full suite — no regressions
pytest -x -q
```

All commands must exit 0. Confirm:
- Loan with overdue installment → `status=in_arrears` after task run
- Loan in `in_arrears` with all installments paid → `status=disbursed` after task run
- Task is idempotent: run twice → no double flip
- `closed` and `written_off` loans excluded from processing
