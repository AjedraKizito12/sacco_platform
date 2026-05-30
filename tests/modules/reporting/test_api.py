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
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

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
    from app.modules.reporting.models import ReportLoanPortfolioRow, ReportRun

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
    from app.modules.reporting.models import ReportIncomeStatementLine, ReportRun

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
    from app.modules.reporting.models import ReportFeeCollectionRow, ReportRun

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
