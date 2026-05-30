# Sub-plan 11 — Snapshot Reconciliation

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Add `reconcile_loan_snapshots` Celery beat task to `app/modules/credit/beat.py`.
For each active tenant, compares `loans.outstanding_principal` against the GL sum
`(debits − credits)` on `journal_lines WHERE sub_ledger_id=loan.id AND account_id=gl_principal_receivable_id`.
Any mismatch emits a structured `loan_snapshot_drift` log entry and writes an `audit_log` row.
The task is **read-only** — it never modifies the loan row.

**Architecture:** Same per-tenant beat pattern as other tasks in `beat.py`. The GL
comparison is a single SQL query per loan using filtered aggregates. Only checks
`disbursed`, `in_arrears`, and `written_off` loans (not `closed` or `draft`).

**Tech Stack:** Celery, SQLAlchemy 2.0 async, structlog, audit_log

---

## Required Reading

- Sub-plans 01, 04, 06, 07, 08, 10 (completed — all financial operations must exist)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §8 (reconciliation job query)
- `app/modules/credit/beat.py` (partial — accrual + arrears tasks already present)
- `app/core/audit/mixin.py` — AuditableMixin / TenantAuditService pattern

---

## File Map

```
Modified
  app/modules/credit/beat.py            add _reconcile_for_tenant + task
  app/workers/celery_app.py             add reconcile-loan-snapshots to beat schedule
  tests/modules/credit/test_service.py  append reconciliation tests
```

---

## Task 1 — `reconcile_loan_snapshots` Beat Task (TDD)

**Files:**
- Modify: `tests/modules/credit/test_service.py`
- Modify: `app/modules/credit/beat.py`

- [ ] **Step 1: Append failing reconciliation tests to `tests/modules/credit/test_service.py`**

Append tests:

```python
# ── Reconciliation tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconciliation_no_drift_after_clean_lifecycle(test_engine, caplog):
    """After disburse → repay lifecycle, reconciliation finds no drift."""
    import logging
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    # Apply a partial repayment.
    repayment_amount = accrued_interest + Decimal("50.00")
    session = await _new_session(test_engine)
    try:
        from app.modules.credit.services.repayment import LoanRepaymentService
        svc = LoanRepaymentService(session)
        await svc.apply_repayment(
            loan_id=loan.id,
            amount=repayment_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _reconcile_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)

    with caplog.at_level(logging.ERROR):
        drifted = await _reconcile_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    assert drifted == 0, f"Expected no drift, got {drifted} drifted loans"
    assert "loan_snapshot_drift" not in caplog.text

    await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_reconciliation_detects_injected_drift(test_engine):
    """Direct UPDATE to outstanding_principal bypassing service → reconciliation detects drift."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    # Inject drift: directly update the snapshot without touching GL.
    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.outstanding_principal = l.outstanding_principal - Decimal("999.00")
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _reconcile_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    drifted = await _reconcile_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    assert drifted == 1, f"Expected 1 drifted loan, got {drifted}"

    await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_reconciliation_does_not_modify_loan(test_engine):
    """Reconciliation task is read-only — does not update outstanding_principal."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")
    original_principal = loan.outstanding_principal

    # Inject drift.
    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.outstanding_principal = l.outstanding_principal - Decimal("100.00")
        drifted_principal = l.outstanding_principal
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _reconcile_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _reconcile_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    # outstanding_principal must remain at the drifted value (task is read-only).
    session2 = await _new_session(test_engine)
    try:
        after = await session2.get(Loan, loan.id)
        assert after.outstanding_principal == drifted_principal
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_reconciliation_skips_closed_loans(test_engine):
    """Closed loans are excluded from reconciliation checks."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    # Force closed and inject drift.
    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.status = "closed"
        l.outstanding_principal = Decimal("0")
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _reconcile_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    drifted = await _reconcile_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    assert drifted == 0, "Closed loan should not be checked"

    await _cleanup(test_engine)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/credit/test_service.py -k "reconcil" -v
```

Expected: `FAILED` — `ImportError: cannot import name '_reconcile_for_tenant'`

- [ ] **Step 3: Add `_reconcile_for_tenant` to `app/modules/credit/beat.py`**

Append to `beat.py` (after the arrears task):

```python
# ── Snapshot reconciliation ───────────────────────────────────────────────────


async def _reconcile_for_tenant(schema_name: str, engine) -> int:
    """Compare loan snapshot fields to GL sums for one tenant.

    Checks outstanding_principal vs GL net (debits - credits) on the
    gl_principal_receivable_id account per loan.

    Returns count of drifted loans.
    """
    from app.modules.credit.models import Loan
    from app.modules.ledger.models import JournalLine

    factory = async_sessionmaker(engine, expire_on_commit=False)
    drift_count = 0

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )

        # Check disbursed, in_arrears, and written_off loans only.
        loans = list(
            (
                await session.execute(
                    select(Loan).where(
                        Loan.status.in_(["disbursed", "in_arrears", "written_off"])
                    )
                )
            ).scalars().all()
        )

        for loan in loans:
            # Compute GL net for this loan's principal receivable account.
            gl_net = await session.scalar(
                select(
                    func.coalesce(func.sum(JournalLine.debit_amount), Decimal("0"))
                    - func.coalesce(func.sum(JournalLine.credit_amount), Decimal("0"))
                ).where(
                    JournalLine.sub_ledger_type == "loan",
                    JournalLine.sub_ledger_id == loan.id,
                    JournalLine.account_id == loan.gl_principal_receivable_id,
                )
            ) or Decimal("0")

            snapshot = loan.outstanding_principal

            if abs(gl_net - snapshot) > Decimal("0.01"):
                drift_count += 1
                _log.error(
                    "loan_snapshot_drift",
                    schema=schema_name,
                    loan_id=str(loan.id),
                    loan_reference=loan.loan_reference,
                    snapshot_outstanding_principal=str(snapshot),
                    gl_net_principal=str(gl_net),
                    diff=str(gl_net - snapshot),
                )
                # Write audit log entry.
                try:
                    from app.core.audit.service import TenantAuditService
                    audit_svc = TenantAuditService(session)
                    await audit_svc.record(
                        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
                        actor_type="system",
                        action="loan_snapshot_drift_detected",
                        resource_type="loan",
                        resource_id=loan.id,
                        before_state={"outstanding_principal": str(snapshot)},
                        after_state={"gl_net_principal": str(gl_net)},
                    )
                except Exception as audit_exc:
                    _log.error(
                        "credit.beat.reconcile_audit_error",
                        loan_id=str(loan.id),
                        error=str(audit_exc),
                    )

        await session.commit()

    return drift_count


async def _run_reconcile_snapshots() -> dict[str, int]:
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
                count = await _reconcile_for_tenant(schema_name, engine)
                if count:
                    totals[schema_name] = count
            except Exception as exc:
                _log.error(
                    "credit.beat.reconcile_tenant_error",
                    schema=schema_name,
                    error=str(exc),
                )
    finally:
        await engine.dispose()
    _log.info("credit.beat.reconcile_complete", **totals)
    return totals


@celery_app.task(name="app.modules.credit.beat.reconcile_loan_snapshots")  # type: ignore[misc]
def reconcile_loan_snapshots() -> dict[str, int]:
    """Daily: compare loan snapshot fields to GL sums; alert on mismatch."""
    return asyncio.run(_run_reconcile_snapshots())
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/modules/credit/test_service.py -k "reconcil" -v
```

Expected: all 4 reconciliation tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/beat.py tests/modules/credit/test_service.py
git commit -m "feat(credit): reconcile_loan_snapshots beat task"
```

---

## Task 2 — Register Beat Task in Celery App

**Files:**
- Modify: `app/workers/celery_app.py`

- [ ] **Step 1: Add to beat schedule**

Add to `beat_schedule` in `app/workers/celery_app.py`:

```python
        "reconcile-loan-snapshots": {
            "task": "app.modules.credit.beat.reconcile_loan_snapshots",
            "schedule": 24 * 3600.0,  # daily
        },
```

- [ ] **Step 2: Verify all credit tasks registered**

```bash
python -c "
from app.workers.celery_app import celery_app
sched = celery_app.conf.beat_schedule
assert 'accrue-reducing-balance-interest' in sched
assert 'mark-loans-in-arrears' in sched
assert 'reconcile-loan-snapshots' in sched
print('All 3 credit beat tasks registered OK')
"
```

Expected: `All 3 credit beat tasks registered OK`

- [ ] **Step 3: Commit**

```bash
git add app/workers/celery_app.py
git commit -m "feat(credit): register reconcile_loan_snapshots in celery beat schedule"
```

---

## Verification Criteria

```bash
# 1. Reconciliation tests pass
pytest tests/modules/credit/test_service.py -k "reconcil" -v

# 2. All credit beat tasks registered
python -c "
from app.workers.celery_app import celery_app
sched = celery_app.conf.beat_schedule
for task in ['accrue-reducing-balance-interest', 'mark-loans-in-arrears', 'reconcile-loan-snapshots']:
    assert task in sched, f'Missing: {task}'
print('OK')
"

# 3. Full suite — no regressions
pytest -x -q
```

All commands must exit 0. Confirm:
- Clean lifecycle (disburse → repay): reconciliation finds 0 drifted loans
- Injected `UPDATE loans SET outstanding_principal` bypassing service: reconciliation detects drift (returns 1)
- Reconciliation does NOT modify loan row (read-only + alert only)
- `closed` loans excluded from checks
- Structured `loan_snapshot_drift` log emitted on mismatch
