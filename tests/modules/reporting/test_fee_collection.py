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

    # Assessment 1: paid (500). Explicit assessed_at — server_default would put it outside the test window.
    fa1 = FeeAssessment(
        fee_type_id=ft.id,
        target_type="member",
        target_id=uuid.uuid4(),
        period_start=date(2026, 1, 1),
        amount=Decimal("500.00"),
        currency="UGX",
        status="paid",
        journal_entry_id=je1.id,
        assessed_at=datetime(2026, 1, 5, tzinfo=UTC),
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
        assessed_at=datetime(2026, 1, 10, tzinfo=UTC),
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
