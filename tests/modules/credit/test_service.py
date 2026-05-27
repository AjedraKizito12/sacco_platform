# tests/modules/credit/test_service.py
"""Integration tests for credit module services.

Uses async_sessionmaker + commit + cleanup pattern (not rollback fixture)
to avoid asyncpg protocol-state errors with flush().
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.credit.models import (
    Loan,
    LoanApplication,
    LoanInstallment,
    LoanProduct,
    LoanRepayment,
)
from app.modules.credit.services.product import LoanProductService

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
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


async def _cleanup(engine: AsyncEngine) -> None:
    """Delete all credit + related rows in dependency order."""
    async with _factory(engine)() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(delete(LoanRepayment))
        await session.execute(delete(LoanInstallment))
        await session.execute(delete(Loan))
        await session.execute(delete(LoanApplication))
        await session.execute(delete(LoanProduct))
        await session.commit()


def _product_kwargs(**overrides) -> dict:
    """Minimal valid kwargs for LoanProductService.create."""
    defaults = dict(
        name="Standard Loan",
        description=None,
        interest_method="flat",
        annual_interest_rate=Decimal("18.0000"),
        repayment_frequency="monthly",
        max_term_periods=24,
        min_amount=Decimal("50000"),
        max_amount=Decimal("5000000"),
        required_approvals=1,
        disbursement_destinations=["member_savings", "cash"],
        repayment_allocation="INTEREST_PRINCIPAL",
        gl_principal_receivable_code="1300",
        gl_interest_receivable_code="1310",
        gl_interest_income_code="4100",
        gl_loan_loss_expense_code=None,
        penalty_fee_type_code=None,
        write_off_threshold=Decimal("0"),
        created_by=uuid.uuid4(),
    )
    defaults.update(overrides)
    return defaults


@pytest.mark.asyncio
async def test_create_loan_product_success(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        product = await svc.create(**_product_kwargs(name="Test Loan Product"))
        await session.commit()

        assert product.id is not None
        assert product.name == "Test Loan Product"
        assert product.interest_method == "flat"
        assert product.annual_interest_rate == Decimal("18.0000")
        assert product.is_active is True
        assert "member_savings" in product.disbursement_destinations
        assert product.repayment_allocation == "INTEREST_PRINCIPAL"
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_create_loan_product_min_gt_max_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        with pytest.raises(ValueError, match="min_amount"):
            await svc.create(
                **_product_kwargs(
                    min_amount=Decimal("1000000"),
                    max_amount=Decimal("500000"),
                )
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_create_loan_product_negative_rate_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        with pytest.raises(ValueError, match="annual_interest_rate"):
            await svc.create(**_product_kwargs(annual_interest_rate=Decimal("-1")))
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_create_loan_product_required_approvals_lt_1_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        with pytest.raises(ValueError, match="required_approvals"):
            await svc.create(**_product_kwargs(required_approvals=0))
    finally:
        await session.close()
        await _cleanup(test_engine)
