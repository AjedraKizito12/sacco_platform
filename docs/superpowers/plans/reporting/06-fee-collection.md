# Reporting Sub-Plan 06: Fee Collection

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `FeeCollectionService` with `materialize()` and `get_fee_collection()`, the nightly Celery beat task, the Jinja2 HTML template, and the API integration tests.

**Architecture:** Reads from `fee_assessments` joined to `fee_types` + `fee_collections`. Aggregates per `(fee_type_id, target_type)`: sums assessed, collected, outstanding, and waived amounts. As sub-plan 06 is the final sub-plan, it also adds the full API test suite (`tests/modules/reporting/test_api.py`).

**Tech Stack:** SQLAlchemy 2.0 async, Celery beat, WeasyPrint/Jinja2, pytest + httpx

**Spec:** `docs/superpowers/specs/2026-05-28-reporting-design.md` — Fee Collection + API sections

**Prerequisite:** Sub-plans 01–05 complete.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `app/modules/reporting/services/fee_collection.py` | Create | FeeCollectionService |
| `app/modules/reporting/beat.py` | Modify | Add materialize_fee_collection task |
| `app/modules/reporting/templates/fee_collection.html` | Create | Jinja2 PDF template |
| `tests/modules/reporting/test_fee_collection.py` | Create | Service + rendering + beat tests |
| `tests/modules/reporting/test_api.py` | Create | API integration tests |

---

### Task 1: `FeeCollectionService`

**Files:**
- Create: `app/modules/reporting/services/fee_collection.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/reporting/test_fee_collection.py
"""Tests for FeeCollectionService."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.fees.models import FeeAssessment, FeeCollection, FeeType
from app.modules.ledger.models import JournalEntry
from app.modules.reporting.models import ReportRun, ReportFeeCollectionRow
from app.modules.reporting.services.fee_collection import FeeCollectionService

TEST_SCHEMA = "tenant_test"
_SYSTEM = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _new_session(engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()

    @event.listens_for(session.sync_session, "after_begin")
    def _set_path(sess, tx, conn):
        conn.exec_driver_sql(f"SET LOCAL search_path TO {TEST_SCHEMA}, platform")

    return session


async def _seed_fees(session: AsyncSession) -> uuid.UUID:
    """Seed one fee type with two assessments (one paid, one assessed). Returns fee_type_id."""
    ft = FeeType(
        code="MEMB-FEE-001",
        name="Membership Fee",
        applicable_to="member",
        amount_kind="fixed",
        amount=Decimal("500.00"),
        currency="UGX",
        trigger_kind="schedule",
        gl_income_account_code="4200",
        gl_receivable_account_code="1300",
        is_active=True,
        requires_collection=True,
    )
    session.add(ft)
    await session.flush()

    # JournalEntry for FK on fee_assessments and fee_collections.
    je1 = JournalEntry(
        reference="FEE-JE-001", description="Assessment 1",
        posted_by=str(_SYSTEM), posted_at=datetime(2026, 1, 5, tzinfo=UTC),
        idempotency_key=f"fee-je-{uuid.uuid4()}",
    )
    je2 = JournalEntry(
        reference="FEE-JE-002", description="Assessment 2",
        posted_by=str(_SYSTEM), posted_at=datetime(2026, 1, 10, tzinfo=UTC),
        idempotency_key=f"fee-je-{uuid.uuid4()}",
    )
    je_coll = JournalEntry(
        reference="FEE-JE-003", description="Collection 1",
        posted_by=str(_SYSTEM), posted_at=datetime(2026, 1, 15, tzinfo=UTC),
        idempotency_key=f"fee-je-{uuid.uuid4()}",
    )
    session.add_all([je1, je2, je_coll])
    await session.flush()

    # Assessment 1: paid (500).
    fa1 = FeeAssessment(
        fee_type_id=ft.id,
        target_type="member",
        target_id=uuid.uuid4(),
        period_start=date(2026, 1, 1),
        amount=Decimal("500.00"),
        currency="UGX",
        status="paid",
        journal_entry_id=je1.id,
    )
    # Assessment 2: assessed (unpaid, 500).
    fa2 = FeeAssessment(
        fee_type_id=ft.id,
        target_type="member",
        target_id=uuid.uuid4(),
        period_start=date(2026, 1, 2),
        amount=Decimal("500.00"),
        currency="UGX",
        status="assessed",
        journal_entry_id=je2.id,
    )
    session.add_all([fa1, fa2])
    await session.flush()

    # Collection for fa1: 500 collected.
    fc = FeeCollection(
        fee_assessment_id=fa1.id,
        amount=Decimal("500.00"),
        method="savings_deduction",
        collected_by=_SYSTEM,
        journal_entry_id=je_coll.id,
        idempotency_key=f"fc-{uuid.uuid4()}",
        source_module="fees",
        source_id=fa1.id,
    )
    session.add(fc)
    await session.commit()
    return ft.id


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(text("DELETE FROM report_fee_collection_rows"))
    await session.execute(text("DELETE FROM report_runs WHERE report_type = 'fee_collection'"))
    await session.execute(text("DELETE FROM fee_collections"))
    await session.execute(text("DELETE FROM fee_assessments"))
    await session.execute(text("DELETE FROM journal_entries WHERE reference LIKE 'FEE-JE-%'"))
    await session.execute(text("DELETE FROM fee_types WHERE code = 'MEMB-FEE-001'"))
    await session.commit()


@pytest.mark.anyio
async def test_materialize_aggregates_correctly(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        fee_type_id = await _seed_fees(session)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    async with _new_session(test_engine) as session:
        svc = FeeCollectionService(session)
        run = await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()

    async with _new_session(test_engine) as session:
        assert run.status == "done"
        row = (await session.execute(
            text(
                "SELECT assessed_total, collected_total, outstanding_total, waived_total "
                "FROM report_fee_collection_rows "
                "WHERE report_run_id = :rid AND fee_type_id = :ftid"
            ),
            {"rid": str(run.id), "ftid": str(fee_type_id)},
        )).one()

        # assessed: 500 + 500 = 1000. collected: 500. outstanding: 500. waived: 0.
        assert row[0] == Decimal("1000.00")
        assert row[1] == Decimal("500.00")
        assert row[2] == Decimal("500.00")
        assert row[3] == Decimal("0")

        await _cleanup(session)


@pytest.mark.anyio
async def test_materialize_idempotent(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        await _seed_fees(session)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    async with _new_session(test_engine) as session:
        svc = FeeCollectionService(session)
        await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()

    async with _new_session(test_engine) as session:
        svc = FeeCollectionService(session)
        await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()

    async with _new_session(test_engine) as session:
        count = (await session.execute(
            text("SELECT COUNT(*) FROM report_fee_collection_rows")
        )).scalar()
        assert count == 1  # One fee type, one row. Second run replaces.
        await _cleanup(session)
```

- [ ] **Step 2: Run — verify failure**

```bash
pytest tests/modules/reporting/test_fee_collection.py::test_materialize_aggregates_correctly -x -v
```

Expected: `FAILED` — service doesn't exist.

- [ ] **Step 3: Write `FeeCollectionService`**

```python
# app/modules/reporting/services/fee_collection.py
"""FeeCollectionService — materialize and retrieve fee collection reports."""
from __future__ import annotations

import traceback
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fees.models import FeeAssessment, FeeCollection, FeeType
from app.modules.reporting.models import ReportFeeCollectionRow, ReportRun

_log = structlog.get_logger(__name__)


class FeeCollectionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(self, *, period_start: date, period_end: date) -> ReportRun:
        """Aggregate fee_assessments + fee_collections per (fee_type, target_type).

        assessed_total  = SUM(assessment.amount) for assessments in period
        collected_total = SUM(collection.amount) for collections in period (via FK)
        outstanding_total = assessed_total - collected_total - waived_total
        waived_total    = SUM(assessment.amount) WHERE status = 'waived'
        as_of_date = period_end.
        """
        run = ReportRun(
            report_type="fee_collection",
            as_of_date=period_end,
            status="running",
            started_at=datetime.now(tz=UTC),
        )
        self._session.add(run)
        await self._session.flush()

        try:
            await self._session.execute(
                delete(ReportFeeCollectionRow).where(
                    ReportFeeCollectionRow.report_run_id == run.id
                )
            )

            period_start_dt = datetime(period_start.year, period_start.month, period_start.day, 0, 0, 0, tzinfo=UTC)
            period_end_dt = datetime(period_end.year, period_end.month, period_end.day, 23, 59, 59, tzinfo=UTC)

            # Aggregate assessments per (fee_type_id, target_type).
            assessment_rows = (
                await self._session.execute(
                    select(
                        FeeType.id.label("fee_type_id"),
                        FeeType.name.label("fee_type_name"),
                        FeeAssessment.target_type,
                        func.coalesce(func.sum(FeeAssessment.amount), Decimal("0")).label("assessed_total"),
                        func.coalesce(
                            func.sum(
                                FeeAssessment.amount.op("*")(
                                    func.cast(FeeAssessment.status == "waived", func.Numeric())
                                )
                            ),
                            Decimal("0"),
                        ).label("waived_total"),
                    )
                    .join(FeeAssessment, FeeAssessment.fee_type_id == FeeType.id)
                    .where(
                        FeeAssessment.assessed_at >= period_start_dt,
                        FeeAssessment.assessed_at <= period_end_dt,
                    )
                    .group_by(FeeType.id, FeeType.name, FeeAssessment.target_type)
                    .order_by(FeeType.name, FeeAssessment.target_type)
                )
            ).all()

            rows = []
            for ar in assessment_rows:
                # Sum collections for assessments of this fee_type in the period.
                collected_total = await self._session.scalar(
                    select(func.coalesce(func.sum(FeeCollection.amount), Decimal("0")))
                    .join(FeeAssessment, FeeCollection.fee_assessment_id == FeeAssessment.id)
                    .where(
                        FeeAssessment.fee_type_id == ar.fee_type_id,
                        FeeAssessment.target_type == ar.target_type,
                        FeeAssessment.assessed_at >= period_start_dt,
                        FeeAssessment.assessed_at <= period_end_dt,
                    )
                ) or Decimal("0")

                waived_total = await self._session.scalar(
                    select(func.coalesce(func.sum(FeeAssessment.amount), Decimal("0")))
                    .where(
                        FeeAssessment.fee_type_id == ar.fee_type_id,
                        FeeAssessment.target_type == ar.target_type,
                        FeeAssessment.status == "waived",
                        FeeAssessment.assessed_at >= period_start_dt,
                        FeeAssessment.assessed_at <= period_end_dt,
                    )
                ) or Decimal("0")

                outstanding_total = ar.assessed_total - collected_total - waived_total

                rows.append(
                    ReportFeeCollectionRow(
                        report_run_id=run.id,
                        period_start=period_start,
                        period_end=period_end,
                        fee_type_id=ar.fee_type_id,
                        fee_type_name=ar.fee_type_name,
                        target_type=ar.target_type,
                        assessed_total=ar.assessed_total,
                        collected_total=collected_total,
                        outstanding_total=outstanding_total,
                        waived_total=waived_total,
                    )
                )

            self._session.add_all(rows)

            run.status = "done"
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()

            _log.info(
                "reporting.fee_collection.materialized",
                period_start=str(period_start),
                period_end=str(period_end),
                rows=len(rows),
                run_id=str(run.id),
            )
            return run

        except Exception:
            run.status = "failed"
            run.error_detail = traceback.format_exc()
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()
            raise

    async def get_fee_collection(
        self,
        *,
        period_end: date,
        fee_type_id: uuid.UUID | None = None,
    ) -> tuple[ReportRun | None, list[ReportFeeCollectionRow]]:
        """Return (run, rows) for the fee collection run where as_of_date == period_end."""
        run = await self._session.scalar(
            select(ReportRun)
            .where(
                ReportRun.report_type == "fee_collection",
                ReportRun.status == "done",
                ReportRun.as_of_date == period_end,
            )
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        if run is None:
            return None, []

        q = (
            select(ReportFeeCollectionRow)
            .where(ReportFeeCollectionRow.report_run_id == run.id)
            .order_by(ReportFeeCollectionRow.fee_type_name)
        )
        if fee_type_id is not None:
            q = q.where(ReportFeeCollectionRow.fee_type_id == fee_type_id)
        rows = list((await self._session.execute(q)).scalars().all())
        return run, rows
```

**Note on the waived_total aggregation:** The SQL expression using `func.cast(FeeAssessment.status == "waived", func.Numeric())` is database-dependent. A simpler approach is two separate queries (one for total, one for waived), as done for `collected_total`. Simplify the `assessment_rows` query to drop the complex waived expression and use a separate scalar query instead — matching the pattern used for `collected_total`:

Replace the `assessment_rows` query's `waived_total` expression with `func.coalesce(func.sum(Decimal("0")), Decimal("0")).label("waived_total")` (placeholder), then compute `waived_total` separately per row (already done in the loop). Remove the waived expression from the `assessment_rows` select entirely — it's computed in the loop.

Final clean version of `assessment_rows` select (remove the waived column, compute it separately like collected_total):

```python
            assessment_rows = (
                await self._session.execute(
                    select(
                        FeeType.id.label("fee_type_id"),
                        FeeType.name.label("fee_type_name"),
                        FeeAssessment.target_type,
                        func.coalesce(func.sum(FeeAssessment.amount), Decimal("0")).label("assessed_total"),
                    )
                    .join(FeeAssessment, FeeAssessment.fee_type_id == FeeType.id)
                    .where(
                        FeeAssessment.assessed_at >= period_start_dt,
                        FeeAssessment.assessed_at <= period_end_dt,
                    )
                    .group_by(FeeType.id, FeeType.name, FeeAssessment.target_type)
                    .order_by(FeeType.name, FeeAssessment.target_type)
                )
            ).all()
```

Use this clean version in the service file.

- [ ] **Step 4: Run all tests**

```bash
pytest tests/modules/reporting/test_fee_collection.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/reporting/services/fee_collection.py tests/modules/reporting/test_fee_collection.py
git commit -m "feat(reporting): FeeCollectionService — fee aggregation per fee_type/target_type"
```

---

### Task 2: HTML template + rendering + beat tests

**Files:**
- Create: `app/modules/reporting/templates/fee_collection.html`
- Modify: `app/modules/reporting/beat.py`
- Modify: `tests/modules/reporting/test_fee_collection.py`

- [ ] **Step 1: Write the template**

```html
<!-- app/modules/reporting/templates/fee_collection.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Fee Collection Report</title>
  <style>
    body { font-family: Arial, sans-serif; font-size: 11px; margin: 20px; }
    h1 { font-size: 16px; margin-bottom: 4px; }
    .meta { color: #555; font-size: 10px; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #6c3483; color: white; padding: 6px 8px; text-align: left; }
    td { padding: 5px 8px; border-bottom: 1px solid #e0e0e0; }
    tr:nth-child(even) td { background: #f8f8f8; }
    .num { text-align: right; }
    tfoot td { font-weight: bold; border-top: 2px solid #6c3483; }
  </style>
</head>
<body>
  <h1>Fee Collection Report</h1>
  <div class="meta">
    Period: {{ from_date }} to {{ to_date }} &nbsp;|&nbsp;
    Generated: {{ generated_at.strftime('%Y-%m-%d %H:%M UTC') if generated_at else '' }}
  </div>
  <table>
    <thead>
      <tr>
        <th>Fee Type</th>
        <th>Target Type</th>
        <th class="num">Assessed</th>
        <th class="num">Collected</th>
        <th class="num">Outstanding</th>
        <th class="num">Waived</th>
      </tr>
    </thead>
    <tbody>
      {% for r in rows %}
      <tr>
        <td>{{ r.fee_type_name }}</td>
        <td>{{ r.target_type }}</td>
        <td class="num">{{ "{:,.4f}".format(r.assessed_total) }}</td>
        <td class="num">{{ "{:,.4f}".format(r.collected_total) }}</td>
        <td class="num">{{ "{:,.4f}".format(r.outstanding_total) }}</td>
        <td class="num">{{ "{:,.4f}".format(r.waived_total) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
```

- [ ] **Step 2: Append beat task to `beat.py`**

```python
async def _materialize_fee_collection_for_tenant(schema_name: str, engine) -> None:
    from app.modules.reporting.services.fee_collection import FeeCollectionService  # noqa: PLC0415

    factory = async_sessionmaker(engine, expire_on_commit=False)
    today = date.today()
    period_start = today.replace(day=1)
    period_end = today

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        svc = FeeCollectionService(session)
        await svc.materialize(period_start=period_start, period_end=period_end)
        await session.commit()


async def _run_materialize_fee_collection() -> dict[str, str]:
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
                await _materialize_fee_collection_for_tenant(schema_name, engine)
                result[schema_name] = "done"
            except Exception as exc:
                _log.error("reporting.beat.fee_collection_error", schema=schema_name, error=str(exc))
                result[schema_name] = f"error: {exc}"
    finally:
        await engine.dispose()
    _log.info("reporting.beat.fee_collection_complete", **result)
    return result


@celery_app.task(name="app.modules.reporting.beat.materialize_fee_collection")  # type: ignore[misc]
def materialize_fee_collection() -> dict[str, str]:
    """Nightly 01:00 UTC: materialize fee collection report for all active tenants."""
    return asyncio.run(_run_materialize_fee_collection())
```

- [ ] **Step 3: Add rendering + beat tests**

Append to `tests/modules/reporting/test_fee_collection.py`:

```python
@pytest.mark.anyio
async def test_render_pdf_returns_pdf_bytes(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        await _seed_fees(session)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    async with _new_session(test_engine) as session:
        svc = FeeCollectionService(session)
        run = await svc.materialize(period_start=period_start, period_end=period_end)
        _, rows = await svc.get_fee_collection(period_end=period_end)
        await session.commit()

    from app.modules.reporting._base import render_pdf
    pdf = render_pdf("fee_collection.html", {
        "run": run, "rows": rows,
        "from_date": period_start, "to_date": period_end,
        "generated_at": datetime.now(tz=UTC),
    })
    assert pdf[:4] == b"%PDF"

    async with _new_session(test_engine) as session:
        await _cleanup(session)


@pytest.mark.anyio
async def test_beat_task_creates_done_run(test_engine: AsyncEngine):
    from app.modules.reporting.beat import _materialize_fee_collection_for_tenant

    async with _new_session(test_engine) as session:
        await _seed_fees(session)

    await _materialize_fee_collection_for_tenant(TEST_SCHEMA, test_engine)

    async with _new_session(test_engine) as session:
        status = (await session.execute(
            text("SELECT status FROM report_runs WHERE report_type = 'fee_collection' ORDER BY started_at DESC LIMIT 1")
        )).scalar()
        assert status == "done"
        await _cleanup(session)
```

- [ ] **Step 4: Run all fee collection tests**

```bash
pytest tests/modules/reporting/test_fee_collection.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/reporting/services/fee_collection.py app/modules/reporting/templates/fee_collection.html app/modules/reporting/beat.py tests/modules/reporting/test_fee_collection.py
git commit -m "feat(reporting): FeeCollectionService + beat task + HTML template + tests"
```

---

### Task 3: API integration tests

**Files:**
- Create: `tests/modules/reporting/test_api.py`

- [ ] **Step 1: Write the API tests**

One test per endpoint per format (json, pdf, csv), plus one test per endpoint for 404 when no data exists.

```python
# tests/modules/reporting/test_api.py
"""API integration tests for the reporting module.

One test per endpoint per format + one 404 test per endpoint.
Uses ASGITransport + real Postgres.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan

TEST_TENANT_SCHEMA = "tenant_test"
ACTOR_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-Slug": "test-tenant", "X-Actor-ID": ACTOR_ID}


async def _make_session_override(engine: AsyncEngine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override():
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


@pytest.fixture
async def client(test_engine: AsyncEngine):
    override = await _make_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


async def _seed_trial_balance_run(engine: AsyncEngine) -> date:
    """Insert a done trial_balance ReportRun + one line. Returns as_of_date."""
    from app.modules.reporting.models import ReportRun, ReportTrialBalanceLine

    factory = async_sessionmaker(engine, expire_on_commit=False)
    as_of = date(2026, 1, 31)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        run = ReportRun(
            report_type="trial_balance", as_of_date=as_of, status="done",
            started_at=datetime.now(tz=UTC), completed_at=datetime.now(tz=UTC),
        )
        session.add(run)
        await session.flush()
        session.add(ReportTrialBalanceLine(
            report_run_id=run.id, as_of_date=as_of,
            account_id=uuid.uuid4(), account_code="1000", account_name="Cash",
            account_type="asset", debit_total=Decimal("5000"), credit_total=Decimal("0"),
            balance=Decimal("5000"),
        ))
        await session.commit()
    return as_of


async def _seed_loan_portfolio_run(engine: AsyncEngine) -> date:
    from app.modules.reporting.models import ReportRun, ReportLoanPortfolioRow

    factory = async_sessionmaker(engine, expire_on_commit=False)
    as_of = date(2026, 2, 28)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        run = ReportRun(
            report_type="loan_portfolio", as_of_date=as_of, status="done",
            started_at=datetime.now(tz=UTC), completed_at=datetime.now(tz=UTC),
        )
        session.add(run)
        await session.flush()
        session.add(ReportLoanPortfolioRow(
            report_run_id=run.id, as_of_date=as_of,
            loan_id=uuid.uuid4(), loan_reference="LN-TEST-001", member_id=uuid.uuid4(),
            product_name="Test Product", disbursed_at=date(2025, 6, 1), maturity_date=date(2026, 6, 1),
            status="disbursed", outstanding_principal=Decimal("9000"), accrued_interest=Decimal("0"),
            total_written_off=Decimal("0"), days_in_arrears=0, aging_bucket="current",
        ))
        await session.commit()
    return as_of


async def _seed_income_statement_run(engine: AsyncEngine) -> tuple[date, date]:
    from app.modules.reporting.models import ReportRun, ReportIncomeStatementLine

    factory = async_sessionmaker(engine, expire_on_commit=False)
    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        run = ReportRun(
            report_type="income_statement", as_of_date=period_end, status="done",
            started_at=datetime.now(tz=UTC), completed_at=datetime.now(tz=UTC),
        )
        session.add(run)
        await session.flush()
        session.add(ReportIncomeStatementLine(
            report_run_id=run.id, period_start=period_start, period_end=period_end,
            account_id=uuid.uuid4(), account_code="4100", account_name="Interest Income",
            account_type="income", debit_total=Decimal("0"), credit_total=Decimal("2000"),
            net_movement=Decimal("2000"),
        ))
        await session.commit()
    return period_start, period_end


async def _seed_savings_statement_run(engine: AsyncEngine) -> tuple[uuid.UUID, date, date]:
    from app.modules.reporting.models import ReportRun, ReportSavingsStatementLine

    factory = async_sessionmaker(engine, expire_on_commit=False)
    member_id = uuid.uuid4()
    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        run = ReportRun(
            report_type="savings_statement", as_of_date=period_end, status="done",
            started_at=datetime.now(tz=UTC), completed_at=datetime.now(tz=UTC),
        )
        session.add(run)
        await session.flush()
        session.add(ReportSavingsStatementLine(
            report_run_id=run.id, period_start=period_start, period_end=period_end,
            savings_account_id=uuid.uuid4(), member_id=member_id,
            posted_at=datetime(2026, 1, 15, tzinfo=UTC), transaction_type="deposit",
            narration="Initial deposit", amount=Decimal("1000"), running_balance=Decimal("1000"),
        ))
        await session.commit()
    return member_id, period_start, period_end


async def _seed_fee_collection_run(engine: AsyncEngine) -> tuple[date, date]:
    from app.modules.reporting.models import ReportRun, ReportFeeCollectionRow

    factory = async_sessionmaker(engine, expire_on_commit=False)
    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        run = ReportRun(
            report_type="fee_collection", as_of_date=period_end, status="done",
            started_at=datetime.now(tz=UTC), completed_at=datetime.now(tz=UTC),
        )
        session.add(run)
        await session.flush()
        session.add(ReportFeeCollectionRow(
            report_run_id=run.id, period_start=period_start, period_end=period_end,
            fee_type_id=uuid.uuid4(), fee_type_name="Membership Fee", target_type="member",
            assessed_total=Decimal("1000"), collected_total=Decimal("800"),
            outstanding_total=Decimal("200"), waived_total=Decimal("0"),
        ))
        await session.commit()
    return period_start, period_end


async def _cleanup_all_runs(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(text("DELETE FROM report_trial_balance_lines"))
        await session.execute(text("DELETE FROM report_loan_portfolio_rows"))
        await session.execute(text("DELETE FROM report_income_statement_lines"))
        await session.execute(text("DELETE FROM report_savings_statement_lines"))
        await session.execute(text("DELETE FROM report_fee_collection_rows"))
        await session.execute(text("DELETE FROM report_runs"))
        await session.commit()


# ── Trial Balance ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_trial_balance_json(client, test_engine):
    as_of = await _seed_trial_balance_run(test_engine)
    resp = await client.get(f"/reporting/trial-balance?as_of={as_of}&format=json", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["as_of_date"] == str(as_of)
    assert len(data["lines"]) == 1
    assert data["lines"][0]["account_code"] == "1000"
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_trial_balance_pdf(client, test_engine):
    as_of = await _seed_trial_balance_run(test_engine)
    resp = await client.get(f"/reporting/trial-balance?as_of={as_of}&format=pdf", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_trial_balance_csv(client, test_engine):
    as_of = await _seed_trial_balance_run(test_engine)
    resp = await client.get(f"/reporting/trial-balance?as_of={as_of}&format=csv", headers=HEADERS)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_trial_balance_404(client, test_engine):
    await _cleanup_all_runs(test_engine)
    resp = await client.get("/reporting/trial-balance?as_of=2020-01-01", headers=HEADERS)
    assert resp.status_code == 404


# ── Loan Portfolio ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_loan_portfolio_json(client, test_engine):
    as_of = await _seed_loan_portfolio_run(test_engine)
    resp = await client.get(f"/reporting/loan-portfolio?as_of={as_of}&format=json", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 1
    assert data["rows"][0]["loan_reference"] == "LN-TEST-001"
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_loan_portfolio_pdf(client, test_engine):
    as_of = await _seed_loan_portfolio_run(test_engine)
    resp = await client.get(f"/reporting/loan-portfolio?as_of={as_of}&format=pdf", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_loan_portfolio_csv(client, test_engine):
    as_of = await _seed_loan_portfolio_run(test_engine)
    resp = await client.get(f"/reporting/loan-portfolio?as_of={as_of}&format=csv", headers=HEADERS)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_loan_portfolio_404(client, test_engine):
    await _cleanup_all_runs(test_engine)
    resp = await client.get("/reporting/loan-portfolio?as_of=2020-01-01", headers=HEADERS)
    assert resp.status_code == 404


# ── Income Statement ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_income_statement_json(client, test_engine):
    period_start, period_end = await _seed_income_statement_run(test_engine)
    resp = await client.get(
        f"/reporting/income-statement?from_date={period_start}&to_date={period_end}&format=json",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["lines"]) == 1
    assert data["lines"][0]["account_code"] == "4100"
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_income_statement_pdf(client, test_engine):
    period_start, period_end = await _seed_income_statement_run(test_engine)
    resp = await client.get(
        f"/reporting/income-statement?from_date={period_start}&to_date={period_end}&format=pdf",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_income_statement_csv(client, test_engine):
    period_start, period_end = await _seed_income_statement_run(test_engine)
    resp = await client.get(
        f"/reporting/income-statement?from_date={period_start}&to_date={period_end}&format=csv",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_income_statement_missing_required_params(client):
    resp = await client.get("/reporting/income-statement", headers=HEADERS)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_get_income_statement_404(client, test_engine):
    await _cleanup_all_runs(test_engine)
    resp = await client.get(
        "/reporting/income-statement?from_date=2020-01-01&to_date=2020-01-31",
        headers=HEADERS,
    )
    assert resp.status_code == 404


# ── Savings Statement ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_savings_statement_json(client, test_engine):
    member_id, period_start, period_end = await _seed_savings_statement_run(test_engine)
    resp = await client.get(
        f"/reporting/savings-statement?member_id={member_id}&format=json",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["lines"]) == 1
    assert data["lines"][0]["transaction_type"] == "deposit"
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_savings_statement_pdf(client, test_engine):
    member_id, _, _ = await _seed_savings_statement_run(test_engine)
    resp = await client.get(
        f"/reporting/savings-statement?member_id={member_id}&format=pdf",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_savings_statement_csv(client, test_engine):
    member_id, _, _ = await _seed_savings_statement_run(test_engine)
    resp = await client.get(
        f"/reporting/savings-statement?member_id={member_id}&format=csv",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_savings_statement_missing_member_id(client):
    resp = await client.get("/reporting/savings-statement", headers=HEADERS)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_get_savings_statement_404(client, test_engine):
    await _cleanup_all_runs(test_engine)
    resp = await client.get(
        f"/reporting/savings-statement?member_id={uuid.uuid4()}",
        headers=HEADERS,
    )
    assert resp.status_code == 404


# ── Fee Collection ─────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_fee_collection_json(client, test_engine):
    period_start, period_end = await _seed_fee_collection_run(test_engine)
    resp = await client.get(
        f"/reporting/fee-collection?from_date={period_start}&to_date={period_end}&format=json",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 1
    assert data["rows"][0]["fee_type_name"] == "Membership Fee"
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_fee_collection_pdf(client, test_engine):
    period_start, period_end = await _seed_fee_collection_run(test_engine)
    resp = await client.get(
        f"/reporting/fee-collection?from_date={period_start}&to_date={period_end}&format=pdf",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_fee_collection_csv(client, test_engine):
    period_start, period_end = await _seed_fee_collection_run(test_engine)
    resp = await client.get(
        f"/reporting/fee-collection?from_date={period_start}&to_date={period_end}&format=csv",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_get_fee_collection_missing_params(client):
    resp = await client.get("/reporting/fee-collection", headers=HEADERS)
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_get_fee_collection_404(client, test_engine):
    await _cleanup_all_runs(test_engine)
    resp = await client.get(
        "/reporting/fee-collection?from_date=2020-01-01&to_date=2020-01-31",
        headers=HEADERS,
    )
    assert resp.status_code == 404


# ── /reporting/runs ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_list_runs(client, test_engine):
    await _seed_trial_balance_run(test_engine)
    resp = await client.get("/reporting/runs", headers=HEADERS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1
    await _cleanup_all_runs(test_engine)


@pytest.mark.anyio
async def test_list_runs_filter_by_type(client, test_engine):
    await _seed_trial_balance_run(test_engine)
    await _seed_loan_portfolio_run(test_engine)
    resp = await client.get("/reporting/runs?report_type=trial_balance", headers=HEADERS)
    assert resp.status_code == 200
    runs = resp.json()
    assert all(r["report_type"] == "trial_balance" for r in runs)
    await _cleanup_all_runs(test_engine)
```

- [ ] **Step 2: Run the API tests**

```bash
pytest tests/modules/reporting/test_api.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Run the full reporting test suite**

```bash
pytest tests/modules/reporting/ -v
```

Expected: all tests across all 5 report test files + api + base pass.

- [ ] **Step 4: Commit**

```bash
git add tests/modules/reporting/test_api.py
git commit -m "test(reporting): API integration tests — one test per endpoint per format"
```

---

### Task 4: Run full test suite and final cleanup

- [ ] **Step 1: Run the entire test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass with no new failures.

- [ ] **Step 2: Run ruff and mypy**

```bash
ruff check app/modules/reporting/ tests/modules/reporting/
mypy app/modules/reporting/ --ignore-missing-imports
```

Fix any issues found. Common ones to watch for:
- Missing `from __future__ import annotations` at top of files
- Bare `dict` without type params (use `dict[str, str]`)
- `TYPE_CHECKING` imports used at runtime (move to runtime imports)

- [ ] **Step 3: Final commit**

```bash
git add -u
git commit -m "fix(reporting): ruff/mypy lint fixes across reporting module"
```

Only create this commit if there are actual lint fixes. Skip if everything was clean.
