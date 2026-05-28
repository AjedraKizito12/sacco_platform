# tests/modules/credit/test_payroll_service.py
"""Tests for PayrollBatchService — CSV/JSON submit, apply, error handling."""
from __future__ import annotations

import io
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import app.modules.credit.executors  # noqa: F401 — registers credit executors

from app.modules.credit.models import PayrollBatch, PayrollBatchLine


TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


def _csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    buf.write("member_id,amount\n")
    for r in rows:
        buf.write(f"{r['member_id']},{r['amount']}\n")
    return buf.getvalue().encode()


async def _new_session(engine: AsyncEngine):
    """Open a session that reapplies search_path on every transaction."""
    from sqlalchemy import event as sa_event

    session = _factory(engine)()

    @sa_event.listens_for(session.sync_session, "after_begin")
    def _reapply_search_path(sess, transaction, connection):  # type: ignore[misc]
        connection.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )

    await session.execute(
        text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
    )
    return session


@pytest.mark.anyio
async def test_submit_json_batch_creates_preview(test_engine: AsyncEngine) -> None:
    """JSON submission creates a batch with matched/unmatched lines."""
    from tests.modules.credit.test_service import _setup_disbursed_loan, _cleanup

    session = await _new_session(test_engine)
    try:
        loan = await _setup_disbursed_loan(session)
        member_id = loan.member_id

        # One matched (valid loan), one unmatched (no loan)
        rows = [
            {"member_id": str(member_id), "amount": "500.00"},
            {"member_id": str(uuid.uuid4()), "amount": "200.00"},  # unknown member
        ]

        from app.modules.credit.services.payroll import PayrollBatchService
        clearing_account_id = uuid.uuid4()  # not validated at submit time

        svc = PayrollBatchService(session)
        batch = await svc.submit_batch(
            rows=rows,
            source_format="json",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            clearing_account_id=clearing_account_id,
        )
        await session.commit()
    finally:
        await session.close()
        await _cleanup(test_engine)

    assert batch.total_rows == 2
    assert batch.matched_rows == 1
    assert batch.unmatched_rows == 1
    assert batch.total_amount == Decimal("500.00")
    assert batch.status == "pending_review"


@pytest.mark.anyio
async def test_submit_csv_batch_creates_preview(test_engine: AsyncEngine) -> None:
    """CSV submission produces the same result as JSON."""
    from tests.modules.credit.test_service import _setup_disbursed_loan, _cleanup

    session = await _new_session(test_engine)
    try:
        loan = await _setup_disbursed_loan(session)

        csv_data = _csv_bytes([
            {"member_id": str(loan.member_id), "amount": "750.00"},
        ])

        from app.modules.credit.services.payroll import PayrollBatchService
        clearing_account_id = uuid.uuid4()

        svc = PayrollBatchService(session)
        batch = await svc.submit_batch_csv(
            csv_bytes=csv_data,
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            clearing_account_id=clearing_account_id,
        )
        await session.commit()
    finally:
        await session.close()
        await _cleanup(test_engine)

    assert batch.matched_rows == 1
    assert batch.total_amount == Decimal("750.00")


@pytest.mark.anyio
async def test_apply_batch_applies_matched_lines(test_engine: AsyncEngine) -> None:
    """After approval, apply_batch posts repayments for all matched lines."""
    from tests.modules.credit.test_service import (
        _setup_disbursement_accounts,
        _make_disbursed_loan,
        _cleanup,
        _new_session as _ts_new_session,
    )

    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        from app.modules.credit.services.payroll import PayrollBatchService
        clearing_account_id = accounts["disbursement_account"]

        svc = PayrollBatchService(session)
        batch = await svc.submit_batch(
            rows=[{"member_id": str(loan.member_id), "amount": "500.00"}],
            source_format="json",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            clearing_account_id=clearing_account_id,
        )
        # Simulate approval by setting status directly
        batch.status = "approved"
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        from app.modules.credit.services.payroll import PayrollBatchService
        svc2 = PayrollBatchService(session2)
        await svc2.apply_batch(
            batch_id=batch.id,
            actor_id=uuid.uuid4(),
            clearing_account_id=clearing_account_id,
        )
    finally:
        await session2.close()

    session3 = await _new_session(test_engine)
    try:
        batch_reloaded = await session3.get(PayrollBatch, batch.id)
        assert batch_reloaded.status == "applied"

        lines = (await session3.execute(
            select(PayrollBatchLine).where(PayrollBatchLine.payroll_batch_id == batch.id)
        )).scalars().all()
        applied_lines = [ln for ln in lines if ln.status == "applied"]
        assert len(applied_lines) == 1
        assert applied_lines[0].repayment_id is not None
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.anyio
async def test_apply_before_approval_raises(test_engine: AsyncEngine) -> None:
    from tests.modules.credit.test_service import _setup_disbursed_loan, _cleanup

    session = await _new_session(test_engine)
    try:
        loan = await _setup_disbursed_loan(session)

        from app.modules.credit.services.payroll import PayrollBatchService
        clearing_account_id = uuid.uuid4()

        svc = PayrollBatchService(session)
        batch = await svc.submit_batch(
            rows=[{"member_id": str(loan.member_id), "amount": "500.00"}],
            source_format="json",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            clearing_account_id=clearing_account_id,
        )
        await session.commit()

        with pytest.raises(ValueError, match="not approved"):
            await svc.apply_batch(batch_id=batch.id, actor_id=uuid.uuid4())
    finally:
        await session.close()
        await _cleanup(test_engine)
