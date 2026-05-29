# tests/modules/reporting/test_loan_portfolio.py
"""Tests for LoanPortfolioService."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.credit.models import Loan, LoanApplication, LoanInstallment, LoanProduct
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

    from app.modules.reporting._base import render_pdf
    pdf = render_pdf("loan_portfolio.html", {"run": run, "rows": rows, "generated_at": datetime.now(tz=UTC)})
    assert pdf[:4] == b"%PDF"

    async with _new_session(test_engine) as session:
        await _cleanup(session)


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
            {"d": as_of},
        )).scalar()
        assert status == "done"
        await _cleanup(session)
