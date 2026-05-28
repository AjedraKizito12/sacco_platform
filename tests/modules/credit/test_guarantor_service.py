# tests/modules/credit/test_guarantor_service.py
"""Tests for GuarantorService — nominate, accept, decline, lien lifecycle."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.credit.models import LoanGuarantor, LoanProduct, LoanApplication


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
        from app.modules.credit.models import LoanGuarantorLien
        await session.execute(delete(LoanGuarantorLien))
        await session.execute(delete(LoanGuarantor))
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
