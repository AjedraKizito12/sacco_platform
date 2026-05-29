# tests/modules/reporting/test_trial_balance.py
"""Tests for TrialBalanceService."""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
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
    await session.execute(
        text("DELETE FROM chart_of_accounts WHERE id IN (:a, :i)"),
        {"a": str(asset_id), "i": str(income_id)},
    )
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
