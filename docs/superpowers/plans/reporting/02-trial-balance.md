# Reporting Sub-Plan 02: Trial Balance

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `TrialBalanceService` with `materialize()` and `get_trial_balance()`, the nightly Celery beat task, and the Jinja2 HTML template.

**Architecture:** `TrialBalanceService.materialize(as_of_date)` aggregates all GL journal lines up to `as_of_date`, groups by account, inserts rows into `report_trial_balance_lines`, and wraps the run in a `ReportRun` audit record. The API endpoint (already stubbed in sub-plan 01) reads from the summary table — no changes needed to `api.py`.

**Tech Stack:** SQLAlchemy 2.0 async, Celery beat, WeasyPrint/Jinja2

**Spec:** `docs/superpowers/specs/2026-05-28-reporting-design.md` — Trial Balance section

**Prerequisite:** Sub-plan 01 complete (models, schemas, _base.py, api.py stub all exist).

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/modules/reporting/services/trial_balance.py` | Create | TrialBalanceService |
| `app/modules/reporting/beat.py` | Create | beat task for trial balance (other tasks added in sub-plans 03–06) |
| `app/modules/reporting/templates/trial_balance.html` | Create | Jinja2 PDF template |
| `tests/modules/reporting/test_trial_balance.py` | Create | Service + rendering tests |

---

### Task 1: `TrialBalanceService`

**Files:**
- Create: `app/modules/reporting/services/trial_balance.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/reporting/test_trial_balance.py
"""Tests for TrialBalanceService."""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.reporting.models import ReportRun, ReportTrialBalanceLine
from app.modules.reporting.services.trial_balance import TrialBalanceService

TEST_SCHEMA = "tenant_test"
_SYSTEM = "00000000-0000-0000-0000-000000000000"


def _new_session(engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()

    @event.listens_for(session.sync_session, "after_begin")
    def _set_path(sess, tx, conn):
        conn.exec_driver_sql(f"SET LOCAL search_path TO {TEST_SCHEMA}, platform")

    return session


async def _seed_gl(session: AsyncSession) -> tuple[ChartOfAccount, ChartOfAccount]:
    """Seed two GL accounts and one journal entry with two lines."""
    asset = ChartOfAccount(
        code="1000", name="Cash", account_type="asset",
        is_active=True,
    )
    income = ChartOfAccount(
        code="4000", name="Interest Income", account_type="income",
        is_active=True,
    )
    session.add_all([asset, income])
    await session.flush()

    entry = JournalEntry(
        reference="TEST-JE-001",
        description="Test journal entry",
        posted_by=_SYSTEM,
        posted_at=datetime(2026, 1, 15, tzinfo=UTC),
        idempotency_key="test-je-001",
    )
    session.add(entry)
    await session.flush()

    line_dr = JournalLine(
        journal_entry_id=entry.id,
        account_id=asset.id,
        debit_amount=Decimal("1000.00"),
        credit_amount=Decimal("0"),
    )
    line_cr = JournalLine(
        journal_entry_id=entry.id,
        account_id=income.id,
        debit_amount=Decimal("0"),
        credit_amount=Decimal("1000.00"),
    )
    session.add_all([line_dr, line_cr])
    await session.commit()
    return asset, income


async def _cleanup(session: AsyncSession, asset_id, income_id) -> None:
    await session.execute(text("DELETE FROM report_trial_balance_lines"))
    await session.execute(text("DELETE FROM report_runs"))
    await session.execute(text("DELETE FROM journal_lines"))
    await session.execute(text("DELETE FROM journal_entries"))
    await session.execute(text(f"DELETE FROM chart_of_accounts WHERE id IN ('{asset_id}', '{income_id}')"))
    await session.commit()


@pytest.mark.anyio
async def test_materialize_creates_run_and_lines(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        asset, income = await _seed_gl(session)

    as_of = date(2026, 1, 31)
    async with _new_session(test_engine) as session:
        svc = TrialBalanceService(session)
        run = await svc.materialize(as_of_date=as_of)
        await session.commit()

    async with _new_session(test_engine) as session:
        assert run.status == "done"
        assert run.as_of_date == as_of

        lines = list(
            (await session.execute(
                text("SELECT account_code, debit_total, credit_total, balance FROM report_trial_balance_lines WHERE report_run_id = :rid ORDER BY account_code"),
                {"rid": str(run.id)},
            )).all()
        )
        assert len(lines) == 2
        cash_line = next(ln for ln in lines if ln[0] == "1000")
        assert cash_line[1] == Decimal("1000.00")  # debit_total
        assert cash_line[2] == Decimal("0")         # credit_total
        assert cash_line[3] == Decimal("1000.00")   # balance (asset: debit - credit)

        income_line = next(ln for ln in lines if ln[0] == "4000")
        assert income_line[1] == Decimal("0")
        assert income_line[2] == Decimal("1000.00")
        assert income_line[3] == Decimal("-1000.00")  # income: debit - credit (negative = income)

        await _cleanup(session, asset.id, income.id)


@pytest.mark.anyio
async def test_materialize_idempotent(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        asset, income = await _seed_gl(session)

    as_of = date(2026, 1, 31)
    async with _new_session(test_engine) as session:
        svc = TrialBalanceService(session)
        await svc.materialize(as_of_date=as_of)
        await session.commit()

    async with _new_session(test_engine) as session:
        svc = TrialBalanceService(session)
        run2 = await svc.materialize(as_of_date=as_of)
        await session.commit()

    async with _new_session(test_engine) as session:
        count = (await session.execute(
            text("SELECT COUNT(*) FROM report_trial_balance_lines")
        )).scalar()
        assert count == 2  # Not 4 — second run replaces first.

        run_count = (await session.execute(
            text("SELECT COUNT(*) FROM report_runs WHERE report_type = 'trial_balance' AND as_of_date = '2026-01-31'")
        )).scalar()
        assert run_count == 2  # Two ReportRun rows (one per materialization run).

        await _cleanup(session, asset.id, income.id)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/modules/reporting/test_trial_balance.py::test_materialize_creates_run_and_lines -x -v
```

Expected: `FAILED` with `ModuleNotFoundError` or `ImportError` — service doesn't exist yet.

- [ ] **Step 3: Write `TrialBalanceService`**

```python
# app/modules/reporting/services/trial_balance.py
"""TrialBalanceService — materialize and retrieve trial balance reports."""
from __future__ import annotations

import traceback
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select, text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.reporting.models import ReportRun, ReportTrialBalanceLine

_log = structlog.get_logger(__name__)


class TrialBalanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(self, *, as_of_date: date) -> ReportRun:
        """Aggregate GL journal lines up to as_of_date and populate report_trial_balance_lines.

        Flow:
        1. Insert ReportRun(status='running').
        2. Delete any existing lines for this run_id (clean slate).
        3. Aggregate journal_lines grouped by account.
        4. Bulk-insert results.
        5. Set status='done'.
        On exception: set status='failed', store traceback, re-raise.
        """
        run = ReportRun(
            report_type="trial_balance",
            as_of_date=as_of_date,
            status="running",
            started_at=datetime.now(tz=UTC),
        )
        self._session.add(run)
        await self._session.flush()

        try:
            # Delete existing lines for this run (idempotency within a run).
            await self._session.execute(
                delete(ReportTrialBalanceLine).where(
                    ReportTrialBalanceLine.report_run_id == run.id
                )
            )

            # Aggregate: SUM(debit_amount), SUM(credit_amount) per account,
            # filtered to journal_entries.posted_at <= as_of_date.
            rows = (
                await self._session.execute(
                    select(
                        ChartOfAccount.id,
                        ChartOfAccount.code,
                        ChartOfAccount.name,
                        ChartOfAccount.account_type,
                        func.coalesce(func.sum(JournalLine.debit_amount), Decimal("0")).label("debit_total"),
                        func.coalesce(func.sum(JournalLine.credit_amount), Decimal("0")).label("credit_total"),
                    )
                    .join(JournalLine, JournalLine.account_id == ChartOfAccount.id)
                    .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
                    .where(JournalEntry.posted_at <= datetime(as_of_date.year, as_of_date.month, as_of_date.day, 23, 59, 59, tzinfo=UTC))
                    .group_by(ChartOfAccount.id, ChartOfAccount.code, ChartOfAccount.name, ChartOfAccount.account_type)
                    .order_by(ChartOfAccount.code)
                )
            ).all()

            lines = [
                ReportTrialBalanceLine(
                    report_run_id=run.id,
                    as_of_date=as_of_date,
                    account_id=row.id,
                    account_code=row.code,
                    account_name=row.name,
                    account_type=row.account_type,
                    debit_total=row.debit_total,
                    credit_total=row.credit_total,
                    balance=row.debit_total - row.credit_total,
                )
                for row in rows
            ]
            self._session.add_all(lines)

            run.status = "done"
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()

            _log.info(
                "reporting.trial_balance.materialized",
                as_of_date=str(as_of_date),
                lines=len(lines),
                run_id=str(run.id),
            )
            return run

        except Exception:
            run.status = "failed"
            run.error_detail = traceback.format_exc()
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()
            raise

    async def get_trial_balance(self, *, as_of_date: date | None = None) -> tuple[ReportRun, list[ReportTrialBalanceLine]]:
        """Return (run, lines) for the latest successful trial balance run.

        If as_of_date is provided, returns the run for that date.
        Returns (None, []) if no run exists.
        """
        q = (
            select(ReportRun)
            .where(ReportRun.report_type == "trial_balance", ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        if as_of_date is not None:
            q = q.where(ReportRun.as_of_date == as_of_date)
        run = await self._session.scalar(q)
        if run is None:
            return None, []

        lines = list(
            (
                await self._session.execute(
                    select(ReportTrialBalanceLine)
                    .where(ReportTrialBalanceLine.report_run_id == run.id)
                    .order_by(ReportTrialBalanceLine.account_code)
                )
            )
            .scalars()
            .all()
        )
        return run, lines
```

- [ ] **Step 4: Run the tests**

```bash
pytest tests/modules/reporting/test_trial_balance.py -v
```

Expected:
```
PASSED tests/modules/reporting/test_trial_balance.py::test_materialize_creates_run_and_lines
PASSED tests/modules/reporting/test_trial_balance.py::test_materialize_idempotent
```

- [ ] **Step 5: Commit**

```bash
git add app/modules/reporting/services/trial_balance.py tests/modules/reporting/test_trial_balance.py
git commit -m "feat(reporting): TrialBalanceService.materialize() + idempotency test"
```

---

### Task 2: PDF template + render test

**Files:**
- Create: `app/modules/reporting/templates/trial_balance.html`
- Modify: `tests/modules/reporting/test_trial_balance.py`

- [ ] **Step 1: Write the HTML template**

```html
<!-- app/modules/reporting/templates/trial_balance.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Trial Balance — {{ run.as_of_date }}</title>
  <style>
    body { font-family: Arial, sans-serif; font-size: 11px; margin: 20px; }
    h1 { font-size: 16px; margin-bottom: 4px; }
    .meta { color: #555; font-size: 10px; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #2c3e50; color: white; padding: 6px 8px; text-align: left; }
    td { padding: 5px 8px; border-bottom: 1px solid #e0e0e0; }
    tr:nth-child(even) td { background: #f8f8f8; }
    .num { text-align: right; }
    tfoot td { font-weight: bold; border-top: 2px solid #2c3e50; }
  </style>
</head>
<body>
  <h1>Trial Balance</h1>
  <div class="meta">
    As of: {{ run.as_of_date }} &nbsp;|&nbsp; Generated: {{ generated_at.strftime('%Y-%m-%d %H:%M UTC') if generated_at else '' }}
  </div>
  <table>
    <thead>
      <tr>
        <th>Code</th>
        <th>Account Name</th>
        <th>Type</th>
        <th class="num">Debit Total</th>
        <th class="num">Credit Total</th>
        <th class="num">Balance</th>
      </tr>
    </thead>
    <tbody>
      {% for ln in lines %}
      <tr>
        <td>{{ ln.account_code }}</td>
        <td>{{ ln.account_name }}</td>
        <td>{{ ln.account_type }}</td>
        <td class="num">{{ "{:,.4f}".format(ln.debit_total) }}</td>
        <td class="num">{{ "{:,.4f}".format(ln.credit_total) }}</td>
        <td class="num">{{ "{:,.4f}".format(ln.balance) }}</td>
      </tr>
      {% endfor %}
    </tbody>
    <tfoot>
      <tr>
        <td colspan="3">Total</td>
        <td class="num">{{ "{:,.4f}".format(lines | sum(attribute='debit_total')) }}</td>
        <td class="num">{{ "{:,.4f}".format(lines | sum(attribute='credit_total')) }}</td>
        <td class="num">{{ "{:,.4f}".format(lines | sum(attribute='balance')) }}</td>
      </tr>
    </tfoot>
  </table>
</body>
</html>
```

- [ ] **Step 2: Add PDF rendering test to `test_trial_balance.py`**

Add these tests at the end of the existing test file:

```python
@pytest.mark.anyio
async def test_render_pdf_returns_pdf_bytes(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        asset, income = await _seed_gl(session)

    as_of = date(2026, 2, 28)
    async with _new_session(test_engine) as session:
        svc = TrialBalanceService(session)
        run, lines = await _get_or_materialize(svc, as_of)
        await session.commit()

    from app.modules.reporting._base import render_pdf
    pdf = render_pdf("trial_balance.html", {
        "run": run, "lines": lines, "generated_at": datetime.now(tz=UTC),
    })
    assert pdf[:4] == b"%PDF"

    async with _new_session(test_engine) as session:
        await _cleanup(session, asset.id, income.id)


@pytest.mark.anyio
async def test_render_csv_trial_balance(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        asset, income = await _seed_gl(session)

    as_of = date(2026, 3, 31)
    async with _new_session(test_engine) as session:
        svc = TrialBalanceService(session)
        run, lines = await _get_or_materialize(svc, as_of)
        await session.commit()

    from app.modules.reporting._base import render_csv
    import csv, io
    headers = ["Account Code", "Account Name", "Account Type", "Debit Total", "Credit Total", "Balance"]
    rows = [[ln.account_code, ln.account_name, ln.account_type, ln.debit_total, ln.credit_total, ln.balance] for ln in lines]
    result = render_csv(headers, rows)
    assert result[:3] == b"\xef\xbb\xbf"
    text_content = result.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text_content)))
    assert reader[0] == headers

    async with _new_session(test_engine) as session:
        await _cleanup(session, asset.id, income.id)


async def _get_or_materialize(svc: TrialBalanceService, as_of: date):
    run = await svc.materialize(as_of_date=as_of)
    run2, lines = await svc.get_trial_balance(as_of_date=as_of)
    return run2 or run, lines
```

Also add `import csv, io` is handled inside the test. The helper `_get_or_materialize` must be added before the tests that call it.

- [ ] **Step 3: Run the rendering tests**

```bash
pytest tests/modules/reporting/test_trial_balance.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/modules/reporting/templates/trial_balance.html tests/modules/reporting/test_trial_balance.py
git commit -m "feat(reporting): trial balance HTML template + PDF/CSV rendering tests"
```

---

### Task 3: Celery beat task

**Files:**
- Create: `app/modules/reporting/beat.py`

- [ ] **Step 1: Write the beat module with trial balance task only**

Sub-plans 03–06 will append to this file. Start with just the trial balance task.

```python
# app/modules/reporting/beat.py
"""Celery beat tasks for the reporting module.

Five nightly tasks, one per report type:
    materialize_trial_balance        — 01:00 UTC
    materialize_loan_portfolio       — 01:00 UTC  (added in sub-plan 03)
    materialize_income_statement     — 01:00 UTC  (added in sub-plan 04)
    materialize_savings_statement    — 01:00 UTC  (added in sub-plan 05)
    materialize_fee_collection       — 01:00 UTC  (added in sub-plan 06)

Each task:
1. Lists all active tenant schemas from platform.tenants.
2. For each schema: opens a session, sets search_path, runs materialize().
3. Failures per tenant are logged and skipped — other tenants continue.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


async def _materialize_trial_balance_for_tenant(schema_name: str, engine, as_of: date) -> None:
    from app.modules.reporting.services.trial_balance import TrialBalanceService  # noqa: PLC0415

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        svc = TrialBalanceService(session)
        await svc.materialize(as_of_date=as_of)
        await session.commit()


async def _run_materialize_trial_balance() -> dict[str, str]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    as_of = date.today()
    result: dict[str, str] = {}
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            schemas = [row[0] for row in rows.fetchall()]
        for schema_name in schemas:
            if not _SCHEMA_RE.match(schema_name):
                continue
            try:
                await _materialize_trial_balance_for_tenant(schema_name, engine, as_of)
                result[schema_name] = "done"
            except Exception as exc:
                _log.error(
                    "reporting.beat.trial_balance_error",
                    schema=schema_name,
                    error=str(exc),
                )
                result[schema_name] = f"error: {exc}"
    finally:
        await engine.dispose()
    _log.info("reporting.beat.trial_balance_complete", **result)
    return result


@celery_app.task(name="app.modules.reporting.beat.materialize_trial_balance")  # type: ignore[misc]
def materialize_trial_balance() -> dict[str, str]:
    """Nightly 01:00 UTC: materialize trial balance for all active tenants."""
    return asyncio.run(_run_materialize_trial_balance())
```

- [ ] **Step 2: Write the beat task test**

Add to `tests/modules/reporting/test_trial_balance.py`:

```python
@pytest.mark.anyio
async def test_beat_task_creates_done_run(test_engine: AsyncEngine):
    """Call the task function directly (not via worker) and assert ReportRun status=done."""
    from sqlalchemy import text as sql_text
    from app.modules.reporting.beat import _materialize_trial_balance_for_tenant

    as_of = date(2026, 4, 30)
    await _materialize_trial_balance_for_tenant(TEST_SCHEMA, test_engine, as_of)

    async with _new_session(test_engine) as session:
        run = await session.scalar(
            sql_text(
                "SELECT status FROM report_runs WHERE report_type = 'trial_balance' AND as_of_date = :d"
            ),
            {"d": str(as_of)},
        )
        assert run == "done"
        # Cleanup
        await session.execute(sql_text("DELETE FROM report_trial_balance_lines"))
        await session.execute(sql_text("DELETE FROM report_runs WHERE report_type = 'trial_balance'"))
        await session.commit()
```

- [ ] **Step 3: Run all trial balance tests**

```bash
pytest tests/modules/reporting/test_trial_balance.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/modules/reporting/beat.py tests/modules/reporting/test_trial_balance.py
git commit -m "feat(reporting): trial balance Celery beat task + beat task test"
```
