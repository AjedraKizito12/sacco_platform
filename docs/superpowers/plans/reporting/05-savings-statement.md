# Reporting Sub-Plan 05: Savings Statement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `SavingsStatementService` with `materialize()` and `get_savings_statement()`, the nightly Celery beat task, and the Jinja2 HTML template.

**Architecture:** Reads from `savings_transactions` joined to `savings_accounts`. All members are materialized into the summary table. Running balance is computed in Python using a window over all transactions ordered by `posted_at` per savings account. The API endpoint filters by `member_id` at query time from the summary table.

**Tech Stack:** SQLAlchemy 2.0 async, Celery beat, WeasyPrint/Jinja2

**Spec:** `docs/superpowers/specs/2026-05-28-reporting-design.md` — Savings Statement section

**Prerequisite:** Sub-plans 01–04 complete.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/modules/reporting/services/savings_statement.py` | Create | SavingsStatementService |
| `app/modules/reporting/beat.py` | Modify | Add materialize_savings_statement task |
| `app/modules/reporting/templates/savings_statement.html` | Create | Jinja2 PDF template |
| `tests/modules/reporting/test_savings_statement.py` | Create | Service + rendering + beat tests |

---

### Task 1: `SavingsStatementService`

**Files:**
- Create: `app/modules/reporting/services/savings_statement.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/reporting/test_savings_statement.py
"""Tests for SavingsStatementService."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction
from app.modules.ledger.models import JournalEntry
from app.modules.reporting.models import ReportRun, ReportSavingsStatementLine
from app.modules.reporting.services.savings_statement import SavingsStatementService

TEST_SCHEMA = "tenant_test"
_SYSTEM = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _new_session(engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()

    @event.listens_for(session.sync_session, "after_begin")
    def _set_path(sess, tx, conn):
        conn.exec_driver_sql(f"SET LOCAL search_path TO {TEST_SCHEMA}, platform")

    return session


async def _seed_savings(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Seed one member with a savings account and three transactions. Returns (member_id, account_id)."""
    member_id = uuid.uuid4()

    product = SavingsProduct(
        name="Regular Savings",
        interest_rate=Decimal("5.00"),
        minimum_balance=Decimal("0"),
        liability_account_id=uuid.uuid4(),
        is_active=True,
    )
    session.add(product)
    await session.flush()

    account = SavingsAccount(
        member_id=member_id,
        savings_product_id=product.id,
        product_name="Regular Savings",
        interest_rate=Decimal("5.00"),
        minimum_balance=Decimal("0"),
        liability_account_id=product.liability_account_id,
    )
    session.add(account)
    await session.flush()

    # Three transactions — we need JournalEntry rows for FK.
    entries = []
    for i in range(3):
        je = JournalEntry(
            reference=f"SAV-TXN-{i+1:03d}",
            description=f"Savings txn {i+1}",
            posted_by=str(_SYSTEM),
            posted_at=datetime(2026, 1, i + 10, tzinfo=UTC),
            idempotency_key=f"sav-je-{uuid.uuid4()}",
        )
        session.add(je)
        entries.append(je)
    await session.flush()

    amounts = [Decimal("1000"), Decimal("500"), Decimal("200")]
    txn_types = ["deposit", "deposit", "withdrawal"]
    for i, (je, amount, txn_type) in enumerate(zip(entries, amounts, txn_types)):
        txn = SavingsTransaction(
            savings_account_id=account.id,
            transaction_type=txn_type,
            amount=amount,
            narration=f"Txn {i+1}",
            journal_entry_id=je.id,
            posted_by=_SYSTEM,
            posted_at=je.posted_at,
            idempotency_key=f"sav-txn-{uuid.uuid4()}",
        )
        session.add(txn)
    await session.commit()
    return member_id, account.id


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(text("DELETE FROM report_savings_statement_lines"))
    await session.execute(text("DELETE FROM report_runs WHERE report_type = 'savings_statement'"))
    await session.execute(text("DELETE FROM savings_transactions"))
    await session.execute(text("DELETE FROM journal_entries WHERE reference LIKE 'SAV-TXN-%'"))
    await session.execute(text("DELETE FROM savings_accounts"))
    await session.execute(text("DELETE FROM savings_products WHERE name = 'Regular Savings'"))
    await session.commit()


@pytest.mark.anyio
async def test_materialize_running_balance_correct(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        member_id, account_id = await _seed_savings(session)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    async with _new_session(test_engine) as session:
        svc = SavingsStatementService(session)
        run = await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()

    async with _new_session(test_engine) as session:
        assert run.status == "done"
        lines = list((await session.execute(
            text(
                "SELECT transaction_type, amount, running_balance "
                "FROM report_savings_statement_lines "
                "WHERE report_run_id = :rid AND savings_account_id = :aid "
                "ORDER BY posted_at"
            ),
            {"rid": str(run.id), "aid": str(account_id)},
        )).all())

        assert len(lines) == 3
        # deposits add, withdrawals subtract
        assert lines[0] == ("deposit", Decimal("1000"), Decimal("1000"))
        assert lines[1] == ("deposit", Decimal("500"), Decimal("1500"))
        assert lines[2] == ("withdrawal", Decimal("200"), Decimal("1300"))

        await _cleanup(session)


@pytest.mark.anyio
async def test_materialize_idempotent(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        await _seed_savings(session)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    async with _new_session(test_engine) as session:
        svc = SavingsStatementService(session)
        await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()

    async with _new_session(test_engine) as session:
        svc = SavingsStatementService(session)
        await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()

    async with _new_session(test_engine) as session:
        count = (await session.execute(
            text("SELECT COUNT(*) FROM report_savings_statement_lines")
        )).scalar()
        assert count == 3  # 3 transactions. Second run replaces — not 6.
        await _cleanup(session)
```

- [ ] **Step 2: Run — verify failure**

```bash
pytest tests/modules/reporting/test_savings_statement.py::test_materialize_running_balance_correct -x -v
```

Expected: `FAILED` — service doesn't exist yet.

- [ ] **Step 3: Write `SavingsStatementService`**

```python
# app/modules/reporting/services/savings_statement.py
"""SavingsStatementService — materialize and retrieve savings statement reports."""
from __future__ import annotations

import traceback
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.savings.models import SavingsAccount, SavingsTransaction
from app.modules.reporting.models import ReportRun, ReportSavingsStatementLine

_log = structlog.get_logger(__name__)


class SavingsStatementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(self, *, period_start: date, period_end: date) -> ReportRun:
        """Materialize all savings transactions into report_savings_statement_lines.

        Running balance is computed per savings account in Python (ordered by posted_at).
        Deposits/SYSTEM_CREDIT/EXTERNAL_CREDIT add to balance.
        Withdrawals/SYSTEM_DEBIT/EXTERNAL_DEBIT subtract.
        as_of_date on ReportRun = period_end.
        """
        run = ReportRun(
            report_type="savings_statement",
            as_of_date=period_end,
            status="running",
            started_at=datetime.now(tz=UTC),
        )
        self._session.add(run)
        await self._session.flush()

        try:
            await self._session.execute(
                delete(ReportSavingsStatementLine).where(
                    ReportSavingsStatementLine.report_run_id == run.id
                )
            )

            period_start_dt = datetime(period_start.year, period_start.month, period_start.day, 0, 0, 0, tzinfo=UTC)
            period_end_dt = datetime(period_end.year, period_end.month, period_end.day, 23, 59, 59, tzinfo=UTC)

            # Load all transactions + account.member_id in period.
            txn_rows = (
                await self._session.execute(
                    select(SavingsTransaction, SavingsAccount.member_id)
                    .join(SavingsAccount, SavingsTransaction.savings_account_id == SavingsAccount.id)
                    .where(
                        SavingsTransaction.posted_at >= period_start_dt,
                        SavingsTransaction.posted_at <= period_end_dt,
                    )
                    .order_by(SavingsTransaction.savings_account_id, SavingsTransaction.posted_at)
                )
            ).all()

            # Compute running balance per savings_account_id.
            # _CREDIT_TYPES: transaction types that increase the balance.
            _CREDIT_TYPES = {"deposit", "SYSTEM_CREDIT", "EXTERNAL_CREDIT"}

            lines = []
            running_balances: dict[uuid.UUID, Decimal] = {}
            for txn, member_id in txn_rows:
                acct_id = txn.savings_account_id
                balance = running_balances.get(acct_id, Decimal("0"))
                if txn.transaction_type in _CREDIT_TYPES:
                    balance = balance + txn.amount
                else:
                    balance = balance - txn.amount
                running_balances[acct_id] = balance

                lines.append(
                    ReportSavingsStatementLine(
                        report_run_id=run.id,
                        period_start=period_start,
                        period_end=period_end,
                        savings_account_id=acct_id,
                        member_id=member_id,
                        posted_at=txn.posted_at,
                        transaction_type=txn.transaction_type,
                        narration=txn.narration,
                        amount=txn.amount,
                        running_balance=balance,
                    )
                )

            self._session.add_all(lines)

            run.status = "done"
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()

            _log.info(
                "reporting.savings_statement.materialized",
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

    async def get_savings_statement(
        self,
        *,
        member_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[ReportRun | None, list[ReportSavingsStatementLine]]:
        """Return (run, lines) for the latest savings statement run, filtered by member_id."""
        run = await self._session.scalar(
            select(ReportRun)
            .where(ReportRun.report_type == "savings_statement", ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        if run is None:
            return None, []

        q = (
            select(ReportSavingsStatementLine)
            .where(
                ReportSavingsStatementLine.report_run_id == run.id,
                ReportSavingsStatementLine.member_id == member_id,
            )
            .order_by(ReportSavingsStatementLine.posted_at)
        )
        if from_date is not None:
            q = q.where(ReportSavingsStatementLine.period_start >= from_date)
        if to_date is not None:
            q = q.where(ReportSavingsStatementLine.period_end <= to_date)
        lines = list((await self._session.execute(q)).scalars().all())
        return run, lines
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/modules/reporting/test_savings_statement.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/reporting/services/savings_statement.py tests/modules/reporting/test_savings_statement.py
git commit -m "feat(reporting): SavingsStatementService — running balance computation + idempotency"
```

---

### Task 2: HTML template + rendering + beat tests

**Files:**
- Create: `app/modules/reporting/templates/savings_statement.html`
- Modify: `app/modules/reporting/beat.py`
- Modify: `tests/modules/reporting/test_savings_statement.py`

- [ ] **Step 1: Write the template**

```html
<!-- app/modules/reporting/templates/savings_statement.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Savings Statement — {{ member_id }}</title>
  <style>
    body { font-family: Arial, sans-serif; font-size: 11px; margin: 20px; }
    h1 { font-size: 16px; margin-bottom: 4px; }
    .meta { color: #555; font-size: 10px; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #1a5276; color: white; padding: 6px 8px; text-align: left; }
    td { padding: 5px 8px; border-bottom: 1px solid #e0e0e0; }
    tr:nth-child(even) td { background: #f8f8f8; }
    .num { text-align: right; }
    .cr { color: #1e8449; }
    .dr { color: #c0392b; }
  </style>
</head>
<body>
  <h1>Savings Statement</h1>
  <div class="meta">
    Member: {{ member_id }} &nbsp;|&nbsp;
    Period: {{ from_date }} to {{ to_date }} &nbsp;|&nbsp;
    Generated: {{ generated_at.strftime('%Y-%m-%d %H:%M UTC') if generated_at else '' }}
  </div>
  <table>
    <thead>
      <tr>
        <th>Date</th>
        <th>Type</th>
        <th>Narration</th>
        <th class="num">Amount</th>
        <th class="num">Running Balance</th>
      </tr>
    </thead>
    <tbody>
      {% for ln in lines %}
      <tr>
        <td>{{ ln.posted_at.strftime('%Y-%m-%d') }}</td>
        <td>{{ ln.transaction_type }}</td>
        <td>{{ ln.narration or '—' }}</td>
        <td class="num {% if ln.transaction_type in ('deposit', 'SYSTEM_CREDIT', 'EXTERNAL_CREDIT') %}cr{% else %}dr{% endif %}">
          {{ "{:,.4f}".format(ln.amount) }}
        </td>
        <td class="num">{{ "{:,.4f}".format(ln.running_balance) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
```

- [ ] **Step 2: Append beat task to `beat.py`**

```python
async def _materialize_savings_statement_for_tenant(schema_name: str, engine) -> None:
    from app.modules.reporting.services.savings_statement import SavingsStatementService  # noqa: PLC0415

    factory = async_sessionmaker(engine, expire_on_commit=False)
    today = date.today()
    period_start = today.replace(day=1)
    period_end = today

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        svc = SavingsStatementService(session)
        await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()


async def _run_materialize_savings_statement() -> dict[str, str]:
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
                await _materialize_savings_statement_for_tenant(schema_name, engine)
                result[schema_name] = "done"
            except Exception as exc:
                _log.error("reporting.beat.savings_statement_error", schema=schema_name, error=str(exc))
                result[schema_name] = f"error: {exc}"
    finally:
        await engine.dispose()
    _log.info("reporting.beat.savings_statement_complete", **result)
    return result


@celery_app.task(name="app.modules.reporting.beat.materialize_savings_statement")  # type: ignore[misc]
def materialize_savings_statement() -> dict[str, str]:
    """Nightly 01:00 UTC: materialize savings statements for all active tenants."""
    return asyncio.run(_run_materialize_savings_statement())
```

- [ ] **Step 3: Add rendering + beat tests**

Append to `tests/modules/reporting/test_savings_statement.py`:

```python
@pytest.mark.anyio
async def test_render_pdf_returns_pdf_bytes(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        member_id, _ = await _seed_savings(session)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    async with _new_session(test_engine) as session:
        svc = SavingsStatementService(session)
        run = await svc.materialize(period_start=period_start, period_end=period_end)
        _, lines = await svc.get_savings_statement(member_id=member_id)
        await session.commit()

    from app.modules.reporting._base import render_pdf
    pdf = render_pdf("savings_statement.html", {
        "run": run, "lines": lines, "member_id": member_id,
        "from_date": period_start, "to_date": period_end,
        "generated_at": datetime.now(tz=UTC),
    })
    assert pdf[:4] == b"%PDF"

    async with _new_session(test_engine) as session:
        await _cleanup(session)


@pytest.mark.anyio
async def test_beat_task_creates_done_run(test_engine: AsyncEngine):
    from app.modules.reporting.beat import _materialize_savings_statement_for_tenant

    async with _new_session(test_engine) as session:
        await _seed_savings(session)

    await _materialize_savings_statement_for_tenant(TEST_SCHEMA, test_engine)

    async with _new_session(test_engine) as session:
        status = (await session.execute(
            text("SELECT status FROM report_runs WHERE report_type = 'savings_statement' ORDER BY started_at DESC LIMIT 1")
        )).scalar()
        assert status == "done"
        await _cleanup(session)
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/modules/reporting/test_savings_statement.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/reporting/services/savings_statement.py app/modules/reporting/templates/savings_statement.html app/modules/reporting/beat.py tests/modules/reporting/test_savings_statement.py
git commit -m "feat(reporting): SavingsStatementService + beat task + HTML template + tests"
```
