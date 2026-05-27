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

import app.modules.credit.executors  # noqa: F401 — registers credit.approve_application
from app.modules.credit.services.application import LoanApplicationService
from app.modules.maker_checker.service import ApprovalService

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


@pytest.mark.asyncio
async def test_get_loan_product_success(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        created = await svc.create(**_product_kwargs(name="Get Test Product"))
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanProductService(session2)
        fetched = await svc2.get(created.id)
        assert fetched.id == created.id
        assert fetched.name == "Get Test Product"
        assert fetched.interest_method == "flat"
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_get_unknown_product_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        with pytest.raises(ValueError, match="not found"):
            await svc.get(uuid.uuid4())
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_list_products_active_only_by_default(test_engine):
    actor = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        p_active = await svc.create(**_product_kwargs(name="Active Product", created_by=actor))
        p_inactive = await svc.create(**_product_kwargs(name="Inactive Product", created_by=actor))
        await svc.deactivate(p_inactive.id, deactivated_by=actor)
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanProductService(session2)
        active_list = await svc2.list(include_inactive=False)
        all_list = await svc2.list(include_inactive=True)
        active_ids = {p.id for p in active_list}
        all_ids = {p.id for p in all_list}
        assert p_active.id in active_ids
        assert p_inactive.id not in active_ids
        assert p_active.id in all_ids
        assert p_inactive.id in all_ids
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_deactivate_product(test_engine):
    actor = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        product = await svc.create(**_product_kwargs(name="To Deactivate", created_by=actor))
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanProductService(session2)
        deactivated = await svc2.deactivate(product.id, deactivated_by=actor)
        await session2.commit()
        assert deactivated.is_active is False
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_update_product_name(test_engine):
    actor = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        product = await svc.create(**_product_kwargs(name="Original Name", created_by=actor))
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanProductService(session2)
        updated = await svc2.update(product.id, name="Updated Name", updated_by=actor)
        await session2.commit()
        assert updated.name == "Updated Name"
        # Immutable financial fields unchanged
        assert updated.annual_interest_rate == Decimal("18.0000")
        assert updated.min_amount == Decimal("50000")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_update_write_off_threshold(test_engine):
    actor = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        svc = LoanProductService(session)
        product = await svc.create(**_product_kwargs(write_off_threshold=Decimal("0")))
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanProductService(session2)
        updated = await svc2.update(
            product.id,
            write_off_threshold=Decimal("100000"),
            updated_by=actor,
        )
        await session2.commit()
        assert updated.write_off_threshold == Decimal("100000")
    finally:
        await session2.close()
        await _cleanup(test_engine)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_product(engine: AsyncEngine, **overrides) -> LoanProduct:
    """Create a committed LoanProduct for use in application tests."""
    session = await _new_session(engine)
    try:
        svc = LoanProductService(session)
        product = await svc.create(**_product_kwargs(**overrides))
        await session.commit()
        return product
    finally:
        await session.close()


# ── Application tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_application_success(test_engine):
    product = await _make_product(test_engine, name="App Test Product", required_approvals=1)

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        actor = uuid.uuid4()
        application = await svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("200000"),
            requested_term_periods=12,
            purpose="Business expansion",
            disbursement_destination="member_savings",
            disbursement_account_id=None,
            submitted_by=actor,
            idempotency_key=f"submit-test-{uuid.uuid4()}",
        )
        await session.commit()

        assert application.id is not None
        assert application.status == "submitted"
        assert application.approval_request_id is not None
        assert application.loan_product_id == product.id
        assert application.requested_amount == Decimal("200000")
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_submit_inactive_product_raises(test_engine):
    product = await _make_product(test_engine, name="Inactive Product")
    # Deactivate the product
    session0 = await _new_session(test_engine)
    try:
        svc0 = LoanProductService(session0)
        await svc0.deactivate(product.id, deactivated_by=uuid.uuid4())
        await session0.commit()
    finally:
        await session0.close()

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        with pytest.raises(ValueError, match="not active"):
            await svc.submit(
                loan_product_id=product.id,
                member_id=uuid.uuid4(),
                requested_amount=Decimal("100000"),
                requested_term_periods=6,
                disbursement_destination="member_savings",
                submitted_by=uuid.uuid4(),
                idempotency_key=f"inactive-{uuid.uuid4()}",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_submit_amount_below_min_raises(test_engine):
    product = await _make_product(test_engine, min_amount=Decimal("50000"), max_amount=Decimal("500000"))

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        with pytest.raises(ValueError, match="min_amount|minimum"):
            await svc.submit(
                loan_product_id=product.id,
                member_id=uuid.uuid4(),
                requested_amount=Decimal("10000"),  # below min_amount=50000
                requested_term_periods=6,
                disbursement_destination="member_savings",
                submitted_by=uuid.uuid4(),
                idempotency_key=f"below-min-{uuid.uuid4()}",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_submit_amount_above_max_raises(test_engine):
    product = await _make_product(test_engine, min_amount=Decimal("50000"), max_amount=Decimal("500000"))

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        with pytest.raises(ValueError, match="max_amount|maximum"):
            await svc.submit(
                loan_product_id=product.id,
                member_id=uuid.uuid4(),
                requested_amount=Decimal("1000000"),  # above max_amount=500000
                requested_term_periods=6,
                disbursement_destination="member_savings",
                submitted_by=uuid.uuid4(),
                idempotency_key=f"above-max-{uuid.uuid4()}",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_submit_term_above_max_raises(test_engine):
    product = await _make_product(test_engine, max_term_periods=12)

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        with pytest.raises(ValueError, match="max_term_periods|term"):
            await svc.submit(
                loan_product_id=product.id,
                member_id=uuid.uuid4(),
                requested_amount=Decimal("100000"),
                requested_term_periods=24,  # above max_term_periods=12
                disbursement_destination="member_savings",
                submitted_by=uuid.uuid4(),
                idempotency_key=f"over-term-{uuid.uuid4()}",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_submit_idempotency(test_engine):
    """Same idempotency_key returns the same application on second call."""
    product = await _make_product(test_engine)

    idem_key = f"idem-{uuid.uuid4()}"
    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        actor = uuid.uuid4()
        first = await svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=actor,
            idempotency_key=idem_key,
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanApplicationService(session2)
        second = await svc2.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("200000"),  # different amount — ignored
            requested_term_periods=12,
            disbursement_destination="member_savings",
            submitted_by=uuid.uuid4(),
            idempotency_key=idem_key,  # same key
        )
        assert second.id == first.id
        assert second.requested_amount == Decimal("100000")  # original preserved
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_approve_quorum_1(test_engine):
    """With required_approvals=1: single non-self approve → application.status=approved."""
    product = await _make_product(test_engine, required_approvals=1)

    submitter = uuid.uuid4()
    approver = uuid.uuid4()  # different actor

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)
        approval_svc = ApprovalService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"q1-{uuid.uuid4()}",
        )
        # Approve as a different actor.
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=approver,
        )
        await session.commit()

        # After executor ran, application.status should be 'approved'.
        assert application.status == "approved"
        assert application.approved_amount == Decimal("100000")
        assert application.approved_term_periods == 6
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_approve_quorum_2_requires_two_approvers(test_engine):
    """With required_approvals=2: first approve keeps pending; second approve triggers executor."""
    product = await _make_product(test_engine, required_approvals=2)

    submitter = uuid.uuid4()
    approver1 = uuid.uuid4()
    approver2 = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)
        approval_svc = ApprovalService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"q2-{uuid.uuid4()}",
        )

        # First approval — quorum not yet met.
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=approver1,
        )
        # Application should still be 'submitted' (executor not called yet).
        assert application.status == "submitted"

        # Second approval — quorum met, executor fires.
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=approver2,
        )
        await session.commit()

        assert application.status == "approved"
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_self_approval_raises(test_engine):
    product = await _make_product(test_engine, required_approvals=1)
    submitter = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)
        approval_svc = ApprovalService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"self-approve-{uuid.uuid4()}",
        )

        with pytest.raises(ValueError, match="[Ss]elf"):
            await approval_svc.approve(
                request_id=application.approval_request_id,
                actor_user_id=submitter,  # same as submitted_by
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_reject_application(test_engine):
    product = await _make_product(test_engine, required_approvals=1)
    submitter = uuid.uuid4()
    rejecter = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"reject-{uuid.uuid4()}",
        )

        rejected = await app_svc.reject(
            application_id=application.id,
            rejected_by=rejecter,
            reason="Insufficient collateral",
        )
        await session.commit()

        assert rejected.status == "rejected"
        assert rejected.rejection_reason == "Insufficient collateral"
        assert rejected.decided_by == rejecter
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_withdraw_application_success(test_engine):
    product = await _make_product(test_engine, required_approvals=1)
    submitter = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"withdraw-{uuid.uuid4()}",
        )

        withdrawn = await app_svc.withdraw(
            application_id=application.id,
            withdrawn_by=submitter,  # same actor as submitter
        )
        await session.commit()

        assert withdrawn.status == "withdrawn"
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_withdraw_non_originator_raises(test_engine):
    """Only the original submitter can withdraw."""
    product = await _make_product(test_engine, required_approvals=1)
    submitter = uuid.uuid4()
    other_actor = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"nonoriginator-{uuid.uuid4()}",
        )

        with pytest.raises(ValueError, match="[Mm]aker|[Oo]riginator|[Cc]ancel"):
            await app_svc.withdraw(
                application_id=application.id,
                withdrawn_by=other_actor,
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_withdraw_after_approval_action_raises(test_engine):
    """Cannot withdraw once a checker has acted on the approval request."""
    product = await _make_product(test_engine, required_approvals=2)
    submitter = uuid.uuid4()
    approver = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)
        approval_svc = ApprovalService(session)

        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=submitter,
            idempotency_key=f"after-action-{uuid.uuid4()}",
        )

        # First approve (quorum=2, so not yet approved).
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=approver,
        )

        # Submitter tries to withdraw — should fail because action_count > 0.
        with pytest.raises(ValueError, match="[Cc]hecker|[Aa]cted|[Cc]ancel"):
            await app_svc.withdraw(
                application_id=application.id,
                withdrawn_by=submitter,
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_list_applications_filter_by_member(test_engine):
    product = await _make_product(test_engine)
    member_a = uuid.uuid4()
    member_b = uuid.uuid4()

    session = await _new_session(test_engine)
    try:
        svc = LoanApplicationService(session)
        app_a = await svc.submit(
            loan_product_id=product.id,
            member_id=member_a,
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="member_savings",
            submitted_by=member_a,
            idempotency_key=f"list-a-{uuid.uuid4()}",
        )
        app_b = await svc.submit(
            loan_product_id=product.id,
            member_id=member_b,
            requested_amount=Decimal("150000"),
            requested_term_periods=12,
            disbursement_destination="member_savings",
            submitted_by=member_b,
            idempotency_key=f"list-b-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanApplicationService(session2)
        member_a_apps = await svc2.list(member_id=member_a)
        assert len(member_a_apps) == 1
        assert member_a_apps[0].id == app_a.id
    finally:
        await session2.close()
        await _cleanup(test_engine)
