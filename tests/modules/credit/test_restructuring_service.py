# tests/modules/credit/test_restructuring_service.py
"""Tests for LoanRestructuringService — term extension and payment holiday."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

import app.modules.credit.executors  # noqa: F401 — registers executors

from app.modules.credit.models import (
    Loan,
    LoanApplication,
    LoanGuarantor,
    LoanGuarantorLien,
    LoanInstallment,
    LoanProduct,
    LoanRepayment,
    LoanRestructuring,
)

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _cleanup(engine: AsyncEngine) -> None:
    """Delete credit rows in dependency order."""
    async with _factory(engine)() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(delete(LoanGuarantorLien))
        await session.execute(delete(LoanGuarantor))
        await session.execute(delete(LoanRepayment))
        await session.execute(delete(LoanInstallment))
        await session.execute(delete(LoanRestructuring))
        await session.execute(delete(Loan))
        await session.execute(delete(LoanApplication))
        await session.execute(delete(LoanProduct))
        await session.commit()


@pytest.mark.anyio
async def test_restructure_submits_approval_request(test_engine: AsyncEngine) -> None:
    """restructure() returns an approval_request_id without executing immediately."""
    from tests.modules.credit.test_service import _setup_disbursed_loan

    factory = _factory(test_engine)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)
        actor_id = uuid.uuid4()

        from app.modules.credit.services.restructuring import LoanRestructuringService

        svc = LoanRestructuringService(session)
        result = await svc.restructure(
            loan_id=loan.id,
            restructuring_type="term_extension",
            periods_added=3,
            reason="Financial hardship",
            actor_id=actor_id,
            idempotency_key=str(uuid.uuid4()),
        )
        await session.commit()

    assert "approval_request_id" in result
    assert result["approval_request_id"] is not None

    await _cleanup(test_engine)


@pytest.mark.anyio
async def test_restructure_closed_loan_raises(test_engine: AsyncEngine) -> None:
    """restructure() on a closed loan raises ValueError."""
    from tests.modules.credit.test_service import _setup_disbursed_loan

    factory = _factory(test_engine)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)
        loan.status = "closed"
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        from app.modules.credit.services.restructuring import LoanRestructuringService

        svc = LoanRestructuringService(session)
        with pytest.raises(ValueError, match="status"):
            await svc.restructure(
                loan_id=loan.id,
                restructuring_type="term_extension",
                periods_added=1,
                reason="test",
                actor_id=uuid.uuid4(),
                idempotency_key=str(uuid.uuid4()),
            )

    await _cleanup(test_engine)


@pytest.mark.anyio
async def test_restructure_written_off_loan_raises(test_engine: AsyncEngine) -> None:
    """restructure() on a written_off loan raises ValueError."""
    from tests.modules.credit.test_service import _setup_disbursed_loan

    factory = _factory(test_engine)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)
        loan.status = "written_off"
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        from app.modules.credit.services.restructuring import LoanRestructuringService

        svc = LoanRestructuringService(session)
        with pytest.raises(ValueError, match="status"):
            await svc.restructure(
                loan_id=loan.id,
                restructuring_type="term_extension",
                periods_added=1,
                reason="test",
                actor_id=uuid.uuid4(),
                idempotency_key=str(uuid.uuid4()),
            )

    await _cleanup(test_engine)


@pytest.mark.anyio
async def test_execute_term_extension_supersedes_unpaid(test_engine: AsyncEngine) -> None:
    """_execute_restructuring marks all unpaid installments is_superseded=True
    and writes new ones with updated term_periods."""
    from tests.modules.credit.test_service import _setup_disbursed_loan

    factory = _factory(test_engine)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)
        original_term = loan.term_periods
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan_obj = await session.get(Loan, loan.id)

        from app.modules.credit.services.restructuring import LoanRestructuringService

        svc = LoanRestructuringService(session)
        await svc._execute_restructuring(
            loan_id=loan.id,
            restructuring_type="term_extension",
            periods_added=3,
            reason="Hardship",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            approval_request_id=None,
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan_reloaded = await session.get(Loan, loan.id)
        assert loan_reloaded is not None
        assert loan_reloaded.term_periods == original_term + 3

        # All original installments should be superseded
        superseded = (
            await session.execute(
                select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .where(LoanInstallment.is_superseded.is_(True))
            )
        ).scalars().all()
        assert len(superseded) == original_term

        # New active installments written
        active = (
            await session.execute(
                select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .where(LoanInstallment.is_superseded.is_(False))
                .order_by(LoanInstallment.period_number)
            )
        ).scalars().all()
        assert len(active) == original_term + 3
        assert sum(float(i.principal_due) for i in active) == pytest.approx(
            float(loan.outstanding_principal), abs=1.0
        )

    await _cleanup(test_engine)


@pytest.mark.anyio
async def test_execute_payment_holiday_shifts_due_dates(test_engine: AsyncEngine) -> None:
    """Payment holiday shifts the next N installment due dates forward by N periods."""
    from tests.modules.credit.test_service import _setup_disbursed_loan

    factory = _factory(test_engine)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        # Get original first unpaid due date
        first_installment = (
            await session.execute(
                select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .where(LoanInstallment.status == "pending")
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalar_one()
        original_due = first_installment.due_date

        from app.modules.credit.services.restructuring import LoanRestructuringService

        svc = LoanRestructuringService(session)
        await svc._execute_restructuring(
            loan_id=loan.id,
            restructuring_type="payment_holiday",
            periods_added=2,
            reason="Holiday",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            approval_request_id=None,
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        # The first new active installment should have a later due date
        first_new = (
            await session.execute(
                select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .where(LoanInstallment.is_superseded.is_(False))
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalar_one()
        # Due date shifted forward
        assert first_new.due_date > original_due

    await _cleanup(test_engine)


@pytest.mark.anyio
async def test_paid_installments_never_superseded(test_engine: AsyncEngine) -> None:
    """Installments with status='paid' are never marked is_superseded."""
    from tests.modules.credit.test_service import _setup_disbursed_loan

    factory = _factory(test_engine)
    first_id: uuid.UUID | None = None

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        # Mark first installment as paid
        first = (
            await session.execute(
                select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalar_one()
        first_id = first.id
        first.status = "paid"
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        from app.modules.credit.services.restructuring import LoanRestructuringService

        svc = LoanRestructuringService(session)
        await svc._execute_restructuring(
            loan_id=loan.id,
            restructuring_type="term_extension",
            periods_added=2,
            reason="test",
            actor_id=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
            approval_request_id=None,
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        assert first_id is not None
        paid = await session.get(LoanInstallment, first_id)
        assert paid is not None
        assert paid.is_superseded is False  # paid installment never superseded

    await _cleanup(test_engine)


@pytest.mark.anyio
async def test_execute_restructuring_idempotent(test_engine: AsyncEngine) -> None:
    """Calling _execute_restructuring twice with same idempotency_key returns the same record."""
    from tests.modules.credit.test_service import _setup_disbursed_loan

    factory = _factory(test_engine)
    idem_key = str(uuid.uuid4())

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        loan = await _setup_disbursed_loan(session)
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        from app.modules.credit.services.restructuring import LoanRestructuringService

        svc = LoanRestructuringService(session)
        r1 = await svc._execute_restructuring(
            loan_id=loan.id,
            restructuring_type="term_extension",
            periods_added=2,
            reason="test",
            actor_id=uuid.uuid4(),
            idempotency_key=idem_key,
            approval_request_id=None,
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform"))
        from app.modules.credit.services.restructuring import LoanRestructuringService

        svc = LoanRestructuringService(session)
        r2 = await svc._execute_restructuring(
            loan_id=loan.id,
            restructuring_type="term_extension",
            periods_added=2,
            reason="test",
            actor_id=uuid.uuid4(),
            idempotency_key=idem_key,
            approval_request_id=None,
        )
        await session.commit()

    assert r1.id == r2.id

    await _cleanup(test_engine)
