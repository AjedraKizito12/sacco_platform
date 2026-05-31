# tests/modules/reporting/test_savings_statement.py
"""Tests for SavingsStatementService."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.ledger.models import JournalEntry
from app.modules.members.models import Member
from app.modules.reporting.services.savings_statement import SavingsStatementService
from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction

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
    member = Member(
        member_number=f"M-{uuid.uuid4().hex[:8]}",
        full_name="Stmt Test Member",
        date_of_birth=date(1990, 1, 1),
        gender="female",
        status="active",
    )
    session.add(member)
    await session.flush()
    member_id = member.id

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
    for i, (je, amount, txn_type) in enumerate(zip(entries, amounts, txn_types, strict=False)):
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
    await session.execute(text("DELETE FROM members WHERE full_name = 'Stmt Test Member'"))
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


@pytest.mark.anyio
async def test_get_savings_statement_groups_by_savings_account(test_engine: AsyncEngine):
    """Multi-account members get rows ordered by (savings_account_id, posted_at)
    so the statement is grouped per account rather than interleaved."""
    async with _new_session(test_engine) as session:
        member_id, account_a_id = await _seed_savings(session)

        # Add a second account for the same member with one transaction.
        product = SavingsProduct(
            name="Second Savings",
            interest_rate=Decimal("3.00"),
            minimum_balance=Decimal("0"),
            liability_account_id=uuid.uuid4(),
            is_active=True,
        )
        session.add(product)
        await session.flush()
        account_b = SavingsAccount(
            member_id=member_id,
            savings_product_id=product.id,
            product_name="Second Savings",
            interest_rate=Decimal("3.00"),
            minimum_balance=Decimal("0"),
            liability_account_id=product.liability_account_id,
        )
        session.add(account_b)
        await session.flush()
        je = JournalEntry(
            reference="SAV-TXN-201",
            description="Second account deposit",
            posted_by=str(_SYSTEM),
            # Posted mid-stream so the broken-ordering path would interleave it.
            posted_at=datetime(2026, 1, 11, tzinfo=UTC),
            idempotency_key=f"sav-je-{uuid.uuid4()}",
        )
        session.add(je)
        await session.flush()
        session.add(SavingsTransaction(
            savings_account_id=account_b.id,
            transaction_type="deposit",
            amount=Decimal("300"),
            narration="Second account opener",
            journal_entry_id=je.id,
            posted_by=_SYSTEM,
            posted_at=je.posted_at,
            idempotency_key=f"sav-txn-{uuid.uuid4()}",
        ))
        await session.commit()

    period_end = date(2026, 1, 31)
    async with _new_session(test_engine) as session:
        svc = SavingsStatementService(session)
        await svc.materialize(period_start=date(2026, 1, 1), period_end=period_end)
        await session.commit()

    async with _new_session(test_engine) as session:
        svc = SavingsStatementService(session)
        _, lines = await svc.get_savings_statement(member_id=member_id)

        # 3 lines for account A + 1 for account B = 4.
        assert len(lines) == 4
        # All lines for a given account must be contiguous (grouped).
        account_ids_in_order = [ln.savings_account_id for ln in lines]
        # The block for account A is contiguous and so is the block for B.
        # Equivalent: the run-length-compressed sequence has length 2.
        compressed = [account_ids_in_order[0]]
        for aid in account_ids_in_order[1:]:
            if aid != compressed[-1]:
                compressed.append(aid)
        assert len(compressed) == 2, (
            f"Lines are interleaved between accounts: {account_ids_in_order}"
        )

        # Within each account, posted_at is ascending.
        from itertools import groupby
        for _, group in groupby(lines, key=lambda ln: ln.savings_account_id):
            timestamps = [ln.posted_at for ln in group]
            assert timestamps == sorted(timestamps)

        await _cleanup(session)
        await session.execute(text("DELETE FROM savings_products WHERE name = 'Second Savings'"))
        await session.commit()


@pytest.mark.anyio
async def test_get_savings_statement_respects_to_date_for_run_selection(
    test_engine: AsyncEngine,
):
    """If multiple runs exist, the picked run must cover the caller's to_date.

    Seeds two runs (as_of_date Jan 31 and Feb 28). A request with to_date=Jan 31
    must pick the Jan 31 run, not the latest one — because the latest run's
    materialized period may not contain the data the caller is asking about.
    """
    from app.modules.reporting.models import ReportRun, ReportSavingsStatementLine

    async with _new_session(test_engine) as session:
        member_id, account_id = await _seed_savings(session)

        # Insert two completed runs by hand.
        run_jan = ReportRun(
            report_type="savings_statement",
            as_of_date=date(2026, 1, 31),
            status="done",
            started_at=datetime.now(tz=UTC),
            completed_at=datetime.now(tz=UTC),
        )
        session.add(run_jan)
        await session.flush()
        session.add(ReportSavingsStatementLine(
            report_run_id=run_jan.id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            savings_account_id=account_id,
            member_id=member_id,
            posted_at=datetime(2026, 1, 10, tzinfo=UTC),
            transaction_type="deposit",
            narration="January line",
            amount=Decimal("100"),
            running_balance=Decimal("100"),
        ))

        run_feb = ReportRun(
            report_type="savings_statement",
            as_of_date=date(2026, 2, 28),
            status="done",
            started_at=datetime.now(tz=UTC),
            completed_at=datetime.now(tz=UTC),
        )
        session.add(run_feb)
        await session.flush()
        session.add(ReportSavingsStatementLine(
            report_run_id=run_feb.id,
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            savings_account_id=account_id,
            member_id=member_id,
            posted_at=datetime(2026, 2, 14, tzinfo=UTC),
            transaction_type="deposit",
            narration="February line",
            amount=Decimal("200"),
            running_balance=Decimal("300"),
        ))
        await session.commit()

    async with _new_session(test_engine) as session:
        svc = SavingsStatementService(session)
        # Caller asks for data up to Jan 31 — the Jan 31 run is the smallest
        # run whose as_of_date >= to_date and must be selected.
        run, lines = await svc.get_savings_statement(
            member_id=member_id, to_date=date(2026, 1, 31),
        )
        assert run is not None
        assert run.as_of_date == date(2026, 1, 31), (
            f"Expected the Jan 31 run, got {run.as_of_date}"
        )
        # Only the January line is in that run (since the Feb line lives in
        # the Feb run).
        narrations = [ln.narration for ln in lines]
        assert narrations == ["January line"]

        await _cleanup(session)
