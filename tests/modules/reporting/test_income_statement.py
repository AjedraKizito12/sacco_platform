# tests/modules/reporting/test_income_statement.py
"""Tests for IncomeStatementService."""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
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

    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
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
            text("SELECT COUNT(*) FROM report_income_statement_lines WHERE period_start = '2026-01-01'")
        )).scalar()
        # 2 accounts (income + expense). Second run replaces, so still 2.
        assert count == 2
        await _cleanup(session)


@pytest.mark.anyio
async def test_render_pdf_returns_pdf_bytes(test_engine: AsyncEngine):
    async with _new_session(test_engine) as session:
        await _seed_income_expense(session)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)
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
