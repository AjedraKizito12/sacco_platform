# tests/modules/credit/test_guarantor_service.py
"""Tests for GuarantorService — nominate, accept, decline, lien lifecycle."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.credit.models import Loan, LoanApplication, LoanGuarantor, LoanProduct

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
    """Session that re-applies search_path after every transaction begin."""
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
    """Delete guarantor rows after tests."""
    async with _factory(engine)() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        from app.modules.credit.models import (
            LoanGuarantorLien,
            LoanInstallment,
            LoanRepayment,
        )
        await session.execute(delete(LoanGuarantorLien))
        await session.execute(delete(LoanGuarantor))
        await session.execute(delete(LoanRepayment))
        await session.execute(delete(LoanInstallment))
        await session.execute(delete(Loan))
        await session.execute(delete(LoanApplication))
        await session.execute(delete(LoanProduct))
        await session.commit()


async def _create_product(session: AsyncSession, required_guarantors: int = 1) -> LoanProduct:
    """Create a LoanProduct directly (bypasses LoanProductService GL lookup)."""
    product = LoanProduct(
        name=f"Guarantor Test Product {uuid.uuid4()}",
        interest_method="flat",
        annual_interest_rate=Decimal("12.0000"),
        repayment_frequency="monthly",
        max_term_periods=12,
        min_amount=Decimal("1000.0000"),
        max_amount=Decimal("100000.0000"),
        required_approvals=1,
        required_guarantors=required_guarantors,
        disbursement_destinations=["member_savings"],
        gl_principal_receivable_code="1100",
        gl_interest_receivable_code="1110",
        gl_interest_income_code="4100",
    )
    session.add(product)
    await session.commit()
    return product


async def _create_application(session: AsyncSession, product: LoanProduct) -> LoanApplication:
    app = LoanApplication(
        loan_product_id=product.id,
        member_id=uuid.uuid4(),
        requested_amount=Decimal("10000.0000"),
        requested_term_periods=12,
        disbursement_destination="member_savings",
        status="submitted",
        idempotency_key=str(uuid.uuid4()),
    )
    session.add(app)
    await session.commit()
    return app


async def _create_loan(
    session: AsyncSession, application: LoanApplication, product: LoanProduct
) -> Loan:
    """Create a minimal Loan row to satisfy the FK on loan_guarantors.loan_id."""
    loan = Loan(
        loan_reference=f"TEST-{uuid.uuid4().hex[:8].upper()}",
        loan_application_id=application.id,
        loan_product_id=product.id,
        member_id=application.member_id,
        status="disbursed",
        principal_amount=application.requested_amount,
        interest_method=product.interest_method,
        annual_interest_rate=product.annual_interest_rate,
        repayment_frequency=product.repayment_frequency,
        term_periods=application.requested_term_periods,
        repayment_allocation="INTEREST_PRINCIPAL",
        disbursement_destination=application.disbursement_destination,
        gl_principal_receivable_id=uuid.uuid4(),
        gl_interest_receivable_id=uuid.uuid4(),
        gl_interest_income_id=uuid.uuid4(),
        gl_disbursement_account_id=uuid.uuid4(),
        disbursed_by=uuid.uuid4(),
        idempotency_key=str(uuid.uuid4()),
    )
    session.add(loan)
    await session.commit()
    return loan


@pytest.mark.anyio
async def test_nominate_creates_guarantor_rows(test_engine: AsyncEngine) -> None:
    session = await _new_session(test_engine)
    try:
        product = await _create_product(session, required_guarantors=2)
        application = await _create_application(session, product)
        guarantor_ids = [uuid.uuid4(), uuid.uuid4()]

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=guarantor_ids,
            actor_id=uuid.uuid4(),
        )
        await session.commit()

        assert len(guarantors) == 2
        assert all(g.status == "nominated" for g in guarantors)
        assert {g.guarantor_member_id for g in guarantors} == set(guarantor_ids)
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.anyio
async def test_nominate_wrong_count_raises(test_engine: AsyncEngine) -> None:
    session = await _new_session(test_engine)
    try:
        product = await _create_product(session, required_guarantors=2)
        application = await _create_application(session, product)

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        with pytest.raises(ValueError, match="requires 2 guarantor"):
            await svc.nominate(
                application_id=application.id,
                guarantor_member_ids=[uuid.uuid4()],  # only 1, need 2
                actor_id=uuid.uuid4(),
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.anyio
async def test_nominate_on_zero_guarantor_product_raises(test_engine: AsyncEngine) -> None:
    session = await _new_session(test_engine)
    try:
        product = await _create_product(session, required_guarantors=0)
        application = await _create_application(session, product)

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        with pytest.raises(ValueError, match="does not require guarantors"):
            await svc.nominate(
                application_id=application.id,
                guarantor_member_ids=[uuid.uuid4()],
                actor_id=uuid.uuid4(),
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.anyio
async def test_accept_sets_accepted_status(test_engine: AsyncEngine) -> None:
    guarantor_member_id = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        product = await _create_product(session, required_guarantors=1)
        application = await _create_application(session, product)

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=[guarantor_member_id],
            actor_id=uuid.uuid4(),
        )
        lg = guarantors[0]
        await svc.accept(loan_guarantor_id=lg.id, guarantor_member_id=guarantor_member_id)
        await session.commit()

        # Reload and verify
        await session.refresh(lg)
        assert lg.status == "accepted"
        assert lg.consented_at is not None
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.anyio
async def test_decline_sets_declined_status(test_engine: AsyncEngine) -> None:
    guarantor_member_id = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        product = await _create_product(session, required_guarantors=1)
        application = await _create_application(session, product)

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=[guarantor_member_id],
            actor_id=uuid.uuid4(),
        )
        lg = guarantors[0]
        await svc.decline(loan_guarantor_id=lg.id, guarantor_member_id=guarantor_member_id)
        await session.commit()

        await session.refresh(lg)
        assert lg.status == "declined"
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.anyio
async def test_accept_wrong_member_raises(test_engine: AsyncEngine) -> None:
    guarantor_member_id = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        product = await _create_product(session, required_guarantors=1)
        application = await _create_application(session, product)

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=[guarantor_member_id],
            actor_id=uuid.uuid4(),
        )
        lg = guarantors[0]
        with pytest.raises(ValueError, match="not authorised"):
            await svc.accept(
                loan_guarantor_id=lg.id,
                guarantor_member_id=uuid.uuid4(),  # wrong member
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.anyio
async def test_adjust_liens_reduces_proportionally(test_engine: AsyncEngine) -> None:
    """adjust_liens reduces current_lien by fraction = principal_applied / original_principal."""
    from app.modules.credit.models import LoanGuarantorLien

    session = await _new_session(test_engine)
    try:
        # Setup: product, application, guarantor, lien
        product = await _create_product(session, required_guarantors=1)
        application = await _create_application(session, product)
        guarantor_member_id = uuid.uuid4()

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=[guarantor_member_id],
            actor_id=uuid.uuid4(),
        )
        lg = guarantors[0]
        await svc.accept(loan_guarantor_id=lg.id, guarantor_member_id=guarantor_member_id)

        # Simulate place_liens: create real Loan, set loan_id, create lien directly
        loan = await _create_loan(session, application, product)
        lg.loan_id = loan.id
        lien = LoanGuarantorLien(
            loan_guarantor_id=lg.id,
            savings_account_id=uuid.uuid4(),
            original_lien=Decimal("10000.0000"),
            current_lien=Decimal("10000.0000"),
            is_active=True,
        )
        session.add(lien)
        await session.commit()

        # apply 25% of 40000 principal → fraction=0.25, reduction=original*0.25=2500
        await svc.adjust_liens(
            loan_id=loan.id,
            principal_applied=Decimal("10000.0000"),  # 10000/40000 = 0.25
            original_principal=Decimal("40000.0000"),
        )
        await session.commit()

        await session.refresh(lien)
        expected = Decimal("10000.0000") - Decimal("10000.0000") * (
            Decimal("10000.0000") / Decimal("40000.0000")
        )
        assert lien.current_lien == expected
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.anyio
async def test_release_liens_zeros_and_deactivates(test_engine: AsyncEngine) -> None:
    """release_liens sets is_active=False, current_lien=0, guarantor status=released."""
    from app.modules.credit.models import LoanGuarantorLien

    session = await _new_session(test_engine)
    try:
        product = await _create_product(session, required_guarantors=1)
        application = await _create_application(session, product)
        guarantor_member_id = uuid.uuid4()

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=[guarantor_member_id],
            actor_id=uuid.uuid4(),
        )
        lg = guarantors[0]
        await svc.accept(loan_guarantor_id=lg.id, guarantor_member_id=guarantor_member_id)

        loan = await _create_loan(session, application, product)
        lg.loan_id = loan.id
        lien = LoanGuarantorLien(
            loan_guarantor_id=lg.id,
            savings_account_id=uuid.uuid4(),
            original_lien=Decimal("10000.0000"),
            current_lien=Decimal("7500.0000"),
            is_active=True,
        )
        session.add(lien)
        await session.commit()

        await svc.release_liens(loan_id=loan.id)
        await session.commit()

        await session.refresh(lien)
        await session.refresh(lg)
        assert lien.is_active is False
        assert lien.current_lien == Decimal("0")
        assert lg.status == "released"
        assert lg.released_at is not None
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.anyio
async def test_reactivate_liens_restores_lien(test_engine: AsyncEngine) -> None:
    """reactivate_liens reactivates the most recent inactive lien for each guarantor."""
    from datetime import UTC, datetime

    from app.modules.credit.models import LoanGuarantorLien

    session = await _new_session(test_engine)
    try:
        product = await _create_product(session, required_guarantors=1)
        application = await _create_application(session, product)
        guarantor_member_id = uuid.uuid4()

        from app.modules.credit.services.guarantor import GuarantorService
        svc = GuarantorService(session)
        guarantors = await svc.nominate(
            application_id=application.id,
            guarantor_member_ids=[guarantor_member_id],
            actor_id=uuid.uuid4(),
        )
        lg = guarantors[0]
        await svc.accept(loan_guarantor_id=lg.id, guarantor_member_id=guarantor_member_id)

        loan = await _create_loan(session, application, product)
        lg.loan_id = loan.id
        # Simulate post-release state
        lg.status = "released"
        lg.released_at = datetime.now(UTC)
        lien = LoanGuarantorLien(
            loan_guarantor_id=lg.id,
            savings_account_id=uuid.uuid4(),
            original_lien=Decimal("10000.0000"),
            current_lien=Decimal("0"),
            is_active=False,
        )
        session.add(lien)
        await session.commit()

        await svc.reactivate_liens(loan_id=loan.id, restored_amount=Decimal("6000.0000"))
        await session.commit()

        await session.refresh(lien)
        await session.refresh(lg)
        assert lien.is_active is True
        assert lien.current_lien == Decimal("6000.0000")
        assert lg.status == "accepted"
        assert lg.released_at is None
    finally:
        await session.close()
        await _cleanup(test_engine)
