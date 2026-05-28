# Reporting Sub-Plan 04: Income Statement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `IncomeStatementService` with `materialize()` and `get_income_statement()`, the nightly Celery beat task, and the Jinja2 HTML template.

**Architecture:** Reads from `journal_lines` joined to `journal_entries` + `chart_of_accounts`, filtered to `account_type IN ('income', 'expense')`. The nightly run always materializes a trailing 12-month period (from 12 months ago to today). The API endpoint filters lines by the requested `from_date`/`to_date` from the materialized summary table.

**Tech Stack:** SQLAlchemy 2.0 async, Celery beat, WeasyPrint/Jinja2

**Spec:** `docs/superpowers/specs/2026-05-28-reporting-design.md` — Income Statement section

**Prerequisite:** Sub-plans 01–03 complete.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/modules/reporting/services/income_statement.py` | Create | IncomeStatementService |
| `app/modules/reporting/beat.py` | Modify | Add materialize_income_statement task |
| `app/modules/reporting/templates/income_statement.html` | Create | Jinja2 PDF template |
| `tests/modules/reporting/test_income_statement.py` | Create | Service + rendering + beat tests |

---

### Task 1: `IncomeStatementService`

**Files:**
- Create: `app/modules/reporting/services/income_statement.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/reporting/test_income_statement.py
"""Tests for IncomeStatementService."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.reporting.models import ReportRun, ReportIncomeStatementLine
from app.modules.reporting.services.income_statement import IncomeStatementService

TEST_SCHEMA = "tenant_test"
_SYSTEM = "00000000-0000-0000-0000-000000000000"


def _new_session(engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()

    @event.listens_for(session.sync_session, "after_begin")
    def _set_path(sess, tx, conn):
        conn.exec_driver_sql(f"SET LOCAL search_path TO {TEST_SCHEMA}, platform")

    return session


async def _seed_income_expense(session: AsyncSession) -> tuple[ChartOfAccount, ChartOfAccount]:
    """Seed one income account and one expense account with journal lines."""
    income_acct = ChartOfAccount(code="4100", name="Interest Income", account_type="income", is_active=True)
    expense_acct = ChartOfAccount(code="5100", name="Loan Loss Expense", account_type="expense", is_active=True)
    # Also seed an asset to verify it is excluded from income statement.
    asset_acct = ChartOfAccount(code="1100", name="Loans Receivable", account_type="asset", is_active=True)
    session.add_all([income_acct, expense_acct, asset_acct])
    await session.flush()

    entry = JournalEntry(
        reference="IS-TEST-001",
        description="Income statement test entry",
        posted_by=_SYSTEM,
        posted_at=datetime(2026, 1, 15, tzinfo=UTC),
        idempotency_key="is-test-001",
    )
    session.add(entry)
    await session.flush()

    session.add_all([
        JournalLine(journal_entry_id=entry.id, account_id=asset_acct.id, debit_amount=Decimal("500"), credit_amount=Decimal("0")),
        JournalLine(journal_entry_id=entry.id, account_id=income_acct.id, debit_amount=Decimal("0"), credit_amount=Decimal("500")),
        JournalLine(journal_entry_id=entry.id, account_id=expense_acct.id, debit_amount=Decimal("200"), credit_amount=Decimal("0")),
        JournalLine(journal_entry_id=entry.id, account_id=asset_acct.id, debit_amount=Decimal("0"), credit_amount=Decimal("200")),
    ])
    await session.commit()
    return income_acct, expense_acct


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(text("DELETE FROM report_income_statement_lines"))
    await session.execute(text("DELETE FROM report_runs WHERE report_type = 'income_statement'"))
    await session.execute(text("DELETE FROM journal_lines"))
    await session.execute(text("DELETE FROM journal_entries"))
    await session.execute(text("DELETE FROM chart_of_accounts WHERE code IN ('4100', '5100', '1100')"))
    await session.commit()


@pytest.mark.anyio
async def test_materialize_includes_only_income_expense(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        income_acct, expense_acct = await _seed_income_expense(session)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    async with _new_session(test_engine) as session:
        svc = IncomeStatementService(session)
        run = await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()

    async with _new_session(test_engine) as session:
        assert run.status == "done"
        lines = list((await session.execute(
            text("SELECT account_code, account_type, debit_total, credit_total, net_movement FROM report_income_statement_lines WHERE report_run_id = :rid ORDER BY account_code"),
            {"rid": str(run.id)},
        )).all())

        # Only income (4100) and expense (5100) — asset (1100) excluded.
        codes = [ln[0] for ln in lines]
        assert "1100" not in codes
        assert "4100" in codes
        assert "5100" in codes

        income_line = next(ln for ln in lines if ln[0] == "4100")
        assert income_line[2] == Decimal("0")     # debit_total
        assert income_line[3] == Decimal("500")   # credit_total
        assert income_line[4] == Decimal("500")   # net_movement = credit - debit (positive = income)

        expense_line = next(ln for ln in lines if ln[0] == "5100")
        assert expense_line[2] == Decimal("200")
        assert expense_line[3] == Decimal("0")
        assert expense_line[4] == Decimal("-200")  # expense: credit - debit (negative)

        await _cleanup(session)


@pytest.mark.anyio
async def test_materialize_idempotent(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        await _seed_income_expense(session)

    period_start = date(2026, 2, 1)
    period_end = date(2026, 2, 28)
    async with _new_session(test_engine) as session:
        svc = IncomeStatementService(session)
        await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()

    async with _new_session(test_engine) as session:
        svc = IncomeStatementService(session)
        await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()

    async with _new_session(test_engine) as session:
        count = (await session.execute(
            text("SELECT COUNT(*) FROM report_income_statement_lines WHERE period_start = '2026-02-01'")
        )).scalar()
        # 2 accounts (income + expense). Second run replaces, so still 2.
        assert count == 2
        await _cleanup(session)
```

- [ ] **Step 2: Run — verify failure**

```bash
pytest tests/modules/reporting/test_income_statement.py::test_materialize_includes_only_income_expense -x -v
```

Expected: `FAILED` — service doesn't exist yet.

- [ ] **Step 3: Write `IncomeStatementService`**

```python
# app/modules/reporting/services/income_statement.py
"""IncomeStatementService — materialize and retrieve income statement reports."""
from __future__ import annotations

import traceback
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.reporting.models import ReportIncomeStatementLine, ReportRun

_log = structlog.get_logger(__name__)


class IncomeStatementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(self, *, period_start: date, period_end: date) -> ReportRun:
        """Aggregate GL journal lines for income/expense accounts in the period.

        as_of_date on the ReportRun is set to period_end.
        net_movement = credit_total - debit_total (positive = net income).
        """
        run = ReportRun(
            report_type="income_statement",
            as_of_date=period_end,
            status="running",
            started_at=datetime.now(tz=UTC),
        )
        self._session.add(run)
        await self._session.flush()

        try:
            await self._session.execute(
                delete(ReportIncomeStatementLine).where(
                    ReportIncomeStatementLine.report_run_id == run.id
                )
            )

            period_start_dt = datetime(period_start.year, period_start.month, period_start.day, 0, 0, 0, tzinfo=UTC)
            period_end_dt = datetime(period_end.year, period_end.month, period_end.day, 23, 59, 59, tzinfo=UTC)

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
                    .where(
                        ChartOfAccount.account_type.in_(["income", "expense"]),
                        JournalEntry.posted_at >= period_start_dt,
                        JournalEntry.posted_at <= period_end_dt,
                    )
                    .group_by(ChartOfAccount.id, ChartOfAccount.code, ChartOfAccount.name, ChartOfAccount.account_type)
                    .order_by(ChartOfAccount.code)
                )
            ).all()

            lines = [
                ReportIncomeStatementLine(
                    report_run_id=run.id,
                    period_start=period_start,
                    period_end=period_end,
                    account_id=row.id,
                    account_code=row.code,
                    account_name=row.name,
                    account_type=row.account_type,
                    debit_total=row.debit_total,
                    credit_total=row.credit_total,
                    net_movement=row.credit_total - row.debit_total,
                )
                for row in rows
            ]
            self._session.add_all(lines)

            run.status = "done"
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()

            _log.info(
                "reporting.income_statement.materialized",
                period_start=str(period_start),
                period_end=str(period_end),
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

    async def get_income_statement(
        self, *, period_end: date
    ) -> tuple[ReportRun | None, list[ReportIncomeStatementLine]]:
        """Return (run, lines) for the income statement run where as_of_date == period_end."""
        run = await self._session.scalar(
            select(ReportRun)
            .where(
                ReportRun.report_type == "income_statement",
                ReportRun.status == "done",
                ReportRun.as_of_date == period_end,
            )
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        if run is None:
            return None, []

        lines = list(
            (
                await self._session.execute(
                    select(ReportIncomeStatementLine)
                    .where(ReportIncomeStatementLine.report_run_id == run.id)
                    .order_by(ReportIncomeStatementLine.account_code)
                )
            )
            .scalars()
            .all()
        )
        return run, lines
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/modules/reporting/test_income_statement.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/reporting/services/income_statement.py tests/modules/reporting/test_income_statement.py
git commit -m "feat(reporting): IncomeStatementService.materialize() — income/expense GL aggregation"
```

---

### Task 2: HTML template + rendering test

**Files:**
- Create: `app/modules/reporting/templates/income_statement.html`
- Modify: `tests/modules/reporting/test_income_statement.py`

- [ ] **Step 1: Write the template**

```html
<!-- app/modules/reporting/templates/income_statement.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Income Statement</title>
  <style>
    body { font-family: Arial, sans-serif; font-size: 11px; margin: 20px; }
    h1 { font-size: 16px; margin-bottom: 4px; }
    .meta { color: #555; font-size: 10px; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #1e8449; color: white; padding: 6px 8px; text-align: left; }
    td { padding: 5px 8px; border-bottom: 1px solid #e0e0e0; }
    tr:nth-child(even) td { background: #f8f8f8; }
    .num { text-align: right; }
    .positive { color: #1e8449; }
    .negative { color: #c0392b; }
    tfoot td { font-weight: bold; border-top: 2px solid #1e8449; }
  </style>
</head>
<body>
  <h1>Income Statement</h1>
  <div class="meta">
    Period: {{ from_date }} to {{ to_date }} &nbsp;|&nbsp;
    Generated: {{ generated_at.strftime('%Y-%m-%d %H:%M UTC') if generated_at else '' }}
  </div>
  <table>
    <thead>
      <tr>
        <th>Code</th>
        <th>Account Name</th>
        <th>Type</th>
        <th class="num">Debit Total</th>
        <th class="num">Credit Total</th>
        <th class="num">Net Movement</th>
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
        <td class="num {% if ln.net_movement >= 0 %}positive{% else %}negative{% endif %}">
          {{ "{:,.4f}".format(ln.net_movement) }}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
```

- [ ] **Step 2: Add rendering test**

Append to `tests/modules/reporting/test_income_statement.py`:

```python
@pytest.mark.anyio
async def test_render_pdf_returns_pdf_bytes(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        await _seed_income_expense(session)

    period_start = date(2026, 3, 1)
    period_end = date(2026, 3, 31)
    async with _new_session(test_engine) as session:
        svc = IncomeStatementService(session)
        run = await svc.materialize(period_start=period_start, period_end=period_end)
        _, lines = await svc.get_income_statement(period_end=period_end)
        await session.commit()

    from app.modules.reporting._base import render_pdf
    pdf = render_pdf("income_statement.html", {
        "run": run, "lines": lines,
        "from_date": period_start, "to_date": period_end,
        "generated_at": datetime.now(tz=UTC),
    })
    assert pdf[:4] == b"%PDF"

    async with _new_session(test_engine) as session:
        await _cleanup(session)


@pytest.mark.anyio
async def test_beat_task_creates_done_run(test_engine: AsyncEngine):
    from app.modules.reporting.beat import _materialize_income_statement_for_tenant

    async with _new_session(test_engine) as session:
        await _seed_income_expense(session)

    await _materialize_income_statement_for_tenant(TEST_SCHEMA, test_engine)

    async with _new_session(test_engine) as session:
        status = (await session.execute(
            text("SELECT status FROM report_runs WHERE report_type = 'income_statement' ORDER BY started_at DESC LIMIT 1")
        )).scalar()
        assert status == "done"
        await _cleanup(session)
```

- [ ] **Step 3: Add beat task to `beat.py`**

Append to `app/modules/reporting/beat.py`:

```python
async def _materialize_income_statement_for_tenant(schema_name: str, engine) -> None:
    from datetime import timedelta
    from app.modules.reporting.services.income_statement import IncomeStatementService  # noqa: PLC0415

    factory = async_sessionmaker(engine, expire_on_commit=False)
    today = date.today()
    period_start = today.replace(day=1)  # First of current month.
    period_end = today

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        svc = IncomeStatementService(session)
        await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()


async def _run_materialize_income_statement() -> dict[str, str]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
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
                await _materialize_income_statement_for_tenant(schema_name, engine)
                result[schema_name] = "done"
            except Exception as exc:
                _log.error("reporting.beat.income_statement_error", schema=schema_name, error=str(exc))
                result[schema_name] = f"error: {exc}"
    finally:
        await engine.dispose()
    _log.info("reporting.beat.income_statement_complete", **result)
    return result


@celery_app.task(name="app.modules.reporting.beat.materialize_income_statement")  # type: ignore[misc]
def materialize_income_statement() -> dict[str, str]:
    """Nightly 01:00 UTC: materialize current-month income statement for all active tenants."""
    return asyncio.run(_run_materialize_income_statement())
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/modules/reporting/test_income_statement.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/reporting/services/income_statement.py app/modules/reporting/templates/income_statement.html app/modules/reporting/beat.py tests/modules/reporting/test_income_statement.py
git commit -m "feat(reporting): IncomeStatementService + beat task + HTML template + tests"
```
