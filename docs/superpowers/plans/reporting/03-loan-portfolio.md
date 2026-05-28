# Reporting Sub-Plan 03: Loan Portfolio

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `LoanPortfolioService` with `materialize()` and `get_loan_portfolio()`, the nightly Celery beat task, and the HTML PDF template.

**Architecture:** Reads from `loans` snapshot columns (authoritative per CLAUDE.md) + `loan_installments` for aging bucket computation. Never recomputes from GL. Aging bucket is determined from `date.today() - earliest_overdue_installment.due_date` for `in_arrears` loans. Loans in `disbursed` status with no overdue installments are `current`. Written-off and closed loans are included.

**Tech Stack:** SQLAlchemy 2.0 async, Celery beat, WeasyPrint/Jinja2

**Spec:** `docs/superpowers/specs/2026-05-28-reporting-design.md` — Loan Portfolio section

**Prerequisite:** Sub-plans 01 and 02 complete.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/modules/reporting/services/loan_portfolio.py` | Create | LoanPortfolioService |
| `app/modules/reporting/beat.py` | Modify | Add materialize_loan_portfolio task |
| `app/modules/reporting/templates/loan_portfolio.html` | Create | Jinja2 PDF template |
| `tests/modules/reporting/test_loan_portfolio.py` | Create | Service + rendering + beat tests |

---

### Task 1: `LoanPortfolioService`

**Files:**
- Create: `app/modules/reporting/services/loan_portfolio.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/reporting/test_loan_portfolio.py
"""Tests for LoanPortfolioService."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.credit.models import Loan, LoanInstallment, LoanProduct, LoanApplication
from app.modules.reporting.models import ReportRun, ReportLoanPortfolioRow
from app.modules.reporting.services.loan_portfolio import LoanPortfolioService

TEST_SCHEMA = "tenant_test"
_SYSTEM = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _new_session(engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()

    @event.listens_for(session.sync_session, "after_begin")
    def _set_path(sess, tx, conn):
        conn.exec_driver_sql(f"SET LOCAL search_path TO {TEST_SCHEMA}, platform")

    return session


async def _make_loan(session: AsyncSession, *, status: str = "disbursed", disbursed_days_ago: int = 30) -> Loan:
    """Seed a minimal loan row. GL account IDs use placeholder UUIDs."""
    product = LoanProduct(
        name="Test Product",
        interest_method="flat",
        annual_interest_rate=Decimal("12.0000"),
        repayment_frequency="monthly",
        max_term_periods=12,
        min_amount=Decimal("1000"),
        max_amount=Decimal("100000"),
        required_approvals=1,
        disbursement_destinations=["member_savings"],
        repayment_allocation="INTEREST_PRINCIPAL",
        gl_principal_receivable_code="1100",
        gl_interest_receivable_code="1200",
        gl_interest_income_code="4100",
        write_off_threshold=Decimal("0"),
        required_guarantors=0,
        is_active=True,
    )
    session.add(product)
    await session.flush()

    app_ = LoanApplication(
        loan_product_id=product.id,
        member_id=uuid.uuid4(),
        requested_amount=Decimal("10000"),
        requested_term_periods=12,
        disbursement_destination="member_savings",
        status="disbursed",
        idempotency_key=f"app-{uuid.uuid4()}",
    )
    session.add(app_)
    await session.flush()

    disbursed_at = datetime.now(tz=UTC).replace(
        day=max(1, datetime.now(tz=UTC).day - disbursed_days_ago % 28)
    )
    loan = Loan(
        loan_reference=f"LN-{uuid.uuid4().hex[:8].upper()}",
        loan_application_id=app_.id,
        loan_product_id=product.id,
        member_id=app_.member_id,
        status=status,
        principal_amount=Decimal("10000.0000"),
        interest_method="flat",
        annual_interest_rate=Decimal("12.0000"),
        repayment_frequency="monthly",
        term_periods=12,
        repayment_allocation="INTEREST_PRINCIPAL",
        disbursement_destination="member_savings",
        gl_principal_receivable_id=uuid.uuid4(),
        gl_interest_receivable_id=uuid.uuid4(),
        gl_interest_income_id=uuid.uuid4(),
        gl_disbursement_account_id=uuid.uuid4(),
        outstanding_principal=Decimal("8000.0000"),
        accrued_interest=Decimal("100.0000"),
        accrued_penalties=Decimal("0"),
        total_paid_principal=Decimal("2000.0000"),
        total_paid_interest=Decimal("200.0000"),
        total_paid_penalties=Decimal("0"),
        total_written_off=Decimal("0"),
        disbursed_at=disbursed_at,
        maturity_date=date(2027, 1, 1),
        disbursed_by=_SYSTEM,
        idempotency_key=f"loan-{uuid.uuid4()}",
    )
    session.add(loan)
    await session.flush()
    return loan


async def _add_overdue_installment(session: AsyncSession, loan_id: uuid.UUID, days_overdue: int) -> LoanInstallment:
    from datetime import timedelta
    due = date.today() - timedelta(days=days_overdue)
    inst = LoanInstallment(
        loan_id=loan_id,
        period_number=1,
        due_date=due,
        principal_due=Decimal("833.33"),
        interest_due=Decimal("100.00"),
        total_due=Decimal("933.33"),
        status="overdue",
        is_superseded=False,
    )
    session.add(inst)
    await session.flush()
    return inst


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(text("DELETE FROM report_loan_portfolio_rows"))
    await session.execute(text("DELETE FROM report_runs"))
    await session.execute(text("DELETE FROM loan_installments"))
    await session.execute(text("DELETE FROM loans"))
    await session.execute(text("DELETE FROM loan_applications"))
    await session.execute(text("DELETE FROM loan_products"))
    await session.commit()


@pytest.mark.anyio
async def test_materialize_disbursed_loan_is_current(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        loan = await _make_loan(session, status="disbursed")
        await session.commit()

    as_of = date.today()
    async with _new_session(test_engine) as session:
        svc = LoanPortfolioService(session)
        run = await svc.materialize(as_of_date=as_of)
        await session.commit()

    async with _new_session(test_engine) as session:
        assert run.status == "done"
        row = (await session.execute(
            text("SELECT aging_bucket, days_in_arrears FROM report_loan_portfolio_rows WHERE report_run_id = :rid"),
            {"rid": str(run.id)},
        )).one()
        assert row[0] == "current"
        assert row[1] == 0
        await _cleanup(session)


@pytest.mark.anyio
async def test_materialize_in_arrears_loan_correct_bucket(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        loan = await _make_loan(session, status="in_arrears")
        await _add_overdue_installment(session, loan.id, days_overdue=45)
        await session.commit()

    as_of = date.today()
    async with _new_session(test_engine) as session:
        svc = LoanPortfolioService(session)
        run = await svc.materialize(as_of_date=as_of)
        await session.commit()

    async with _new_session(test_engine) as session:
        row = (await session.execute(
            text("SELECT aging_bucket, days_in_arrears FROM report_loan_portfolio_rows WHERE report_run_id = :rid"),
            {"rid": str(run.id)},
        )).one()
        assert row[0] == "31_60"
        assert row[1] == 45
        await _cleanup(session)


@pytest.mark.anyio
async def test_materialize_idempotent(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        await _make_loan(session, status="disbursed")
        await session.commit()

    as_of = date.today()
    async with _new_session(test_engine) as session:
        svc = LoanPortfolioService(session)
        await svc.materialize(as_of_date=as_of)
        await session.commit()

    async with _new_session(test_engine) as session:
        svc = LoanPortfolioService(session)
        await svc.materialize(as_of_date=as_of)
        await session.commit()

    async with _new_session(test_engine) as session:
        count = (await session.execute(
            text("SELECT COUNT(*) FROM report_loan_portfolio_rows")
        )).scalar()
        assert count == 1  # Second run replaces first.
        await _cleanup(session)
```

- [ ] **Step 2: Run the test — verify failure**

```bash
pytest tests/modules/reporting/test_loan_portfolio.py::test_materialize_disbursed_loan_is_current -x -v
```

Expected: `FAILED` — service doesn't exist yet.

- [ ] **Step 3: Write `LoanPortfolioService`**

```python
# app/modules/reporting/services/loan_portfolio.py
"""LoanPortfolioService — materialize and retrieve loan portfolio reports."""
from __future__ import annotations

import traceback
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanInstallment, LoanProduct
from app.modules.reporting.models import ReportLoanPortfolioRow, ReportRun

_log = structlog.get_logger(__name__)


def _aging_bucket(days: int) -> str:
    if days == 0:
        return "current"
    if days <= 30:
        return "1_30"
    if days <= 60:
        return "31_60"
    if days <= 90:
        return "61_90"
    return "90_plus"


class LoanPortfolioService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(self, *, as_of_date: date) -> ReportRun:
        """Populate report_loan_portfolio_rows from loans snapshot columns.

        Aging buckets computed from loan_installments. Never reads from GL.
        """
        run = ReportRun(
            report_type="loan_portfolio",
            as_of_date=as_of_date,
            status="running",
            started_at=datetime.now(tz=UTC),
        )
        self._session.add(run)
        await self._session.flush()

        try:
            await self._session.execute(
                delete(ReportLoanPortfolioRow).where(
                    ReportLoanPortfolioRow.report_run_id == run.id
                )
            )

            # Load all loans with their product name.
            loan_rows = (
                await self._session.execute(
                    select(Loan, LoanProduct.name.label("product_name"))
                    .join(LoanProduct, Loan.loan_product_id == LoanProduct.id)
                    .where(Loan.status.in_(["disbursed", "in_arrears", "written_off", "closed"]))
                    .order_by(Loan.loan_reference)
                )
            ).all()

            today = date.today()

            portfolio_rows = []
            for loan, product_name in loan_rows:
                # Compute days_in_arrears from earliest overdue installment.
                days_in_arrears = 0
                if loan.status == "in_arrears":
                    earliest_overdue = await self._session.scalar(
                        select(func.min(LoanInstallment.due_date))
                        .where(
                            LoanInstallment.loan_id == loan.id,
                            LoanInstallment.status == "overdue",
                            LoanInstallment.is_superseded.is_(False),
                        )
                    )
                    if earliest_overdue is not None:
                        days_in_arrears = (today - earliest_overdue).days

                bucket = _aging_bucket(days_in_arrears)
                disbursed_at_date = loan.disbursed_at.date() if loan.disbursed_at else as_of_date

                portfolio_rows.append(
                    ReportLoanPortfolioRow(
                        report_run_id=run.id,
                        as_of_date=as_of_date,
                        loan_id=loan.id,
                        loan_reference=loan.loan_reference,
                        member_id=loan.member_id,
                        product_name=product_name,
                        disbursed_at=disbursed_at_date,
                        maturity_date=loan.maturity_date,
                        status=loan.status,
                        outstanding_principal=loan.outstanding_principal,
                        accrued_interest=loan.accrued_interest,
                        total_written_off=loan.total_written_off,
                        days_in_arrears=days_in_arrears,
                        aging_bucket=bucket,
                    )
                )

            self._session.add_all(portfolio_rows)

            run.status = "done"
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()

            _log.info(
                "reporting.loan_portfolio.materialized",
                as_of_date=str(as_of_date),
                rows=len(portfolio_rows),
                run_id=str(run.id),
            )
            return run

        except Exception:
            run.status = "failed"
            run.error_detail = traceback.format_exc()
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()
            raise

    async def get_loan_portfolio(
        self, *, as_of_date: date | None = None, status: str | None = None
    ) -> tuple[ReportRun | None, list[ReportLoanPortfolioRow]]:
        """Return (run, rows) for the latest successful loan portfolio run."""
        q = (
            select(ReportRun)
            .where(ReportRun.report_type == "loan_portfolio", ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        if as_of_date is not None:
            q = q.where(ReportRun.as_of_date == as_of_date)
        run = await self._session.scalar(q)
        if run is None:
            return None, []

        rq = (
            select(ReportLoanPortfolioRow)
            .where(ReportLoanPortfolioRow.report_run_id == run.id)
            .order_by(ReportLoanPortfolioRow.loan_reference)
        )
        if status is not None and status != "all":
            rq = rq.where(ReportLoanPortfolioRow.status == status)
        rows = list((await self._session.execute(rq)).scalars().all())
        return run, rows
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/modules/reporting/test_loan_portfolio.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/reporting/services/loan_portfolio.py tests/modules/reporting/test_loan_portfolio.py
git commit -m "feat(reporting): LoanPortfolioService.materialize() with aging bucket computation"
```

---

### Task 2: HTML template + rendering test

**Files:**
- Create: `app/modules/reporting/templates/loan_portfolio.html`
- Modify: `tests/modules/reporting/test_loan_portfolio.py`

- [ ] **Step 1: Write the template**

```html
<!-- app/modules/reporting/templates/loan_portfolio.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Loan Portfolio — {{ run.as_of_date }}</title>
  <style>
    body { font-family: Arial, sans-serif; font-size: 10px; margin: 20px; }
    h1 { font-size: 15px; margin-bottom: 4px; }
    .meta { color: #555; font-size: 9px; margin-bottom: 12px; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #1a5276; color: white; padding: 5px 6px; text-align: left; font-size: 9px; }
    td { padding: 4px 6px; border-bottom: 1px solid #e0e0e0; }
    tr:nth-child(even) td { background: #f5f5f5; }
    .num { text-align: right; }
    .badge-current { color: #27ae60; }
    .badge-1_30, .badge-31_60 { color: #e67e22; }
    .badge-61_90, .badge-90_plus { color: #c0392b; font-weight: bold; }
  </style>
</head>
<body>
  <h1>Loan Portfolio Report</h1>
  <div class="meta">
    As of: {{ run.as_of_date }} &nbsp;|&nbsp; Generated: {{ generated_at.strftime('%Y-%m-%d %H:%M UTC') if generated_at else '' }}
  </div>
  <table>
    <thead>
      <tr>
        <th>Loan Ref</th>
        <th>Member ID</th>
        <th>Product</th>
        <th>Disbursed</th>
        <th>Maturity</th>
        <th>Status</th>
        <th class="num">Outstanding</th>
        <th class="num">Accrued Int.</th>
        <th class="num">Written Off</th>
        <th class="num">Days Arrears</th>
        <th>Aging</th>
      </tr>
    </thead>
    <tbody>
      {% for r in rows %}
      <tr>
        <td>{{ r.loan_reference }}</td>
        <td>{{ r.member_id }}</td>
        <td>{{ r.product_name }}</td>
        <td>{{ r.disbursed_at }}</td>
        <td>{{ r.maturity_date or '—' }}</td>
        <td>{{ r.status }}</td>
        <td class="num">{{ "{:,.4f}".format(r.outstanding_principal) }}</td>
        <td class="num">{{ "{:,.4f}".format(r.accrued_interest) }}</td>
        <td class="num">{{ "{:,.4f}".format(r.total_written_off) }}</td>
        <td class="num">{{ r.days_in_arrears }}</td>
        <td class="badge-{{ r.aging_bucket }}">{{ r.aging_bucket }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
```

- [ ] **Step 2: Add rendering test**

Append to `tests/modules/reporting/test_loan_portfolio.py`:

```python
@pytest.mark.anyio
async def test_render_pdf_returns_pdf_bytes(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        await _make_loan(session, status="disbursed")
        await session.commit()

    as_of = date.today()
    async with _new_session(test_engine) as session:
        svc = LoanPortfolioService(session)
        run = await svc.materialize(as_of_date=as_of)
        _, rows = await svc.get_loan_portfolio(as_of_date=as_of)
        await session.commit()

    from datetime import datetime, UTC
    from app.modules.reporting._base import render_pdf
    pdf = render_pdf("loan_portfolio.html", {"run": run, "rows": rows, "generated_at": datetime.now(tz=UTC)})
    assert pdf[:4] == b"%PDF"

    async with _new_session(test_engine) as session:
        await _cleanup(session)
```

- [ ] **Step 3: Run all tests**

```bash
pytest tests/modules/reporting/test_loan_portfolio.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/modules/reporting/templates/loan_portfolio.html tests/modules/reporting/test_loan_portfolio.py
git commit -m "feat(reporting): loan portfolio HTML template + PDF rendering test"
```

---

### Task 3: Add beat task to `beat.py`

**Files:**
- Modify: `app/modules/reporting/beat.py`

- [ ] **Step 1: Append the loan portfolio beat task**

Add to the bottom of `app/modules/reporting/beat.py`:

```python
async def _materialize_loan_portfolio_for_tenant(schema_name: str, engine, as_of: date) -> None:
    from app.modules.reporting.services.loan_portfolio import LoanPortfolioService  # noqa: PLC0415

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        svc = LoanPortfolioService(session)
        await svc.materialize(as_of_date=as_of)
        await session.commit()


async def _run_materialize_loan_portfolio() -> dict[str, str]:
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
                await _materialize_loan_portfolio_for_tenant(schema_name, engine, as_of)
                result[schema_name] = "done"
            except Exception as exc:
                _log.error(
                    "reporting.beat.loan_portfolio_error",
                    schema=schema_name,
                    error=str(exc),
                )
                result[schema_name] = f"error: {exc}"
    finally:
        await engine.dispose()
    _log.info("reporting.beat.loan_portfolio_complete", **result)
    return result


@celery_app.task(name="app.modules.reporting.beat.materialize_loan_portfolio")  # type: ignore[misc]
def materialize_loan_portfolio() -> dict[str, str]:
    """Nightly 01:00 UTC: materialize loan portfolio for all active tenants."""
    return asyncio.run(_run_materialize_loan_portfolio())
```

- [ ] **Step 2: Add beat task test**

Append to `tests/modules/reporting/test_loan_portfolio.py`:

```python
@pytest.mark.anyio
async def test_beat_task_creates_done_run(test_engine: AsyncEngine):
    from app.modules.reporting.beat import _materialize_loan_portfolio_for_tenant

    as_of = date.today()
    async with _new_session(test_engine) as session:
        await _make_loan(session, status="disbursed")
        await session.commit()

    await _materialize_loan_portfolio_for_tenant(TEST_SCHEMA, test_engine, as_of)

    async with _new_session(test_engine) as session:
        status = (await session.execute(
            text("SELECT status FROM report_runs WHERE report_type = 'loan_portfolio' AND as_of_date = :d"),
            {"d": str(as_of)},
        )).scalar()
        assert status == "done"
        await _cleanup(session)
```

- [ ] **Step 3: Run all tests**

```bash
pytest tests/modules/reporting/test_loan_portfolio.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/modules/reporting/beat.py tests/modules/reporting/test_loan_portfolio.py
git commit -m "feat(reporting): loan portfolio Celery beat task + beat task test"
```
