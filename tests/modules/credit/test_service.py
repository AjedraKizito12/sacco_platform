# tests/modules/credit/test_service.py
"""Integration tests for credit module services.

Uses async_sessionmaker + commit + cleanup pattern (not rollback fixture)
to avoid asyncpg protocol-state errors with flush().
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import logging

import pytest
from sqlalchemy import delete, func, text
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.modules.credit.executors  # noqa: F401 — registers credit.approve_application
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
from app.modules.credit.services.application import LoanApplicationService
from app.modules.credit.services.disbursement import LoanDisbursementService
from app.modules.credit.services.product import LoanProductService
from app.modules.credit.services.query import CreditQueryService
from app.modules.credit.services.repayment import LoanRepaymentService
from app.modules.credit.services.write_off import LoanWriteOffService
from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.ledger.service import LedgerService
from app.modules.maker_checker.service import ApprovalService
from app.modules.members.models import Member
from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction

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
    """Delete all credit + savings + GL rows in dependency order."""
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
        await session.execute(delete(SavingsTransaction))
        await session.execute(delete(SavingsAccount))
        await session.execute(delete(SavingsProduct))
        await session.execute(delete(JournalLine))
        await session.execute(delete(JournalEntry))
        await session.execute(delete(ChartOfAccount))
        await session.execute(delete(Member))
        await session.commit()


async def _setup_disbursed_loan(session: AsyncSession) -> Loan:
    """Insert a minimal disbursed Loan + 12 monthly installments.

    Uses direct row insertion (no GL, no service orchestration) so it can run
    inside an already-open session.  Suitable for restructuring tests that
    don't need a balanced GL.
    """
    from datetime import date, timedelta
    from decimal import Decimal

    from app.modules.credit.services._schedule import compute_schedule

    principal = Decimal("120000.0000")
    annual_rate = Decimal("18.0000")
    term = 12
    today = date.today()

    product = LoanProduct(
        name=f"Restructure Test {uuid.uuid4()}",
        interest_method="flat",
        annual_interest_rate=annual_rate,
        repayment_frequency="monthly",
        max_term_periods=term,
        min_amount=Decimal("10000"),
        max_amount=Decimal("500000"),
        required_approvals=1,
        disbursement_destinations=["cash"],
        gl_principal_receivable_code="1300",
        gl_interest_receivable_code="1310",
        gl_interest_income_code="4100",
    )
    session.add(product)
    await session.flush()

    application = LoanApplication(
        loan_product_id=product.id,
        member_id=uuid.uuid4(),
        requested_amount=principal,
        requested_term_periods=term,
        disbursement_destination="cash",
        status="disbursed",
        idempotency_key=str(uuid.uuid4()),
    )
    session.add(application)
    await session.flush()

    schedule = compute_schedule(
        principal=principal,
        annual_interest_rate=annual_rate,
        interest_method="flat",
        repayment_frequency="monthly",
        term_periods=term,
        disbursement_date=today,
    )
    maturity_date = schedule[-1].due_date

    loan = Loan(
        loan_reference=f"RST-{uuid.uuid4().hex[:8].upper()}",
        loan_application_id=application.id,
        loan_product_id=product.id,
        member_id=application.member_id,
        status="disbursed",
        principal_amount=principal,
        outstanding_principal=principal,
        interest_method="flat",
        annual_interest_rate=annual_rate,
        repayment_frequency="monthly",
        term_periods=term,
        repayment_allocation="INTEREST_PRINCIPAL",
        disbursement_destination="cash",
        gl_principal_receivable_id=uuid.uuid4(),
        gl_interest_receivable_id=uuid.uuid4(),
        gl_interest_income_id=uuid.uuid4(),
        gl_disbursement_account_id=uuid.uuid4(),
        first_repayment_due=schedule[0].due_date,
        maturity_date=maturity_date,
        disbursed_by=uuid.uuid4(),
        idempotency_key=str(uuid.uuid4()),
    )
    session.add(loan)
    await session.flush()

    for row in schedule:
        inst = LoanInstallment(
            loan_id=loan.id,
            period_number=row.period_number,
            due_date=row.due_date,
            principal_due=row.principal_due,
            interest_due=row.interest_due,
            total_due=row.total_due,
        )
        session.add(inst)
    await session.flush()

    return loan


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


# ── Disbursement helpers ──────────────────────────────────────────────────────


async def _setup_disbursement_accounts(engine: AsyncEngine) -> dict:
    """Create GL accounts and savings product needed for disbursement tests."""
    session = await _new_session(engine)
    try:
        actor = uuid.uuid4()
        ledger = LedgerService(session)
        principal_recv = await ledger.create_account(
            code="1300", name="Loans Receivable", account_type="asset", created_by=actor
        )
        interest_recv = await ledger.create_account(
            code="1310", name="Interest Receivable", account_type="asset", created_by=actor
        )
        interest_income = await ledger.create_account(
            code="4100", name="Interest Income", account_type="income", created_by=actor
        )
        cash_account = await ledger.create_account(
            code="1020", name="Cash", account_type="asset", created_by=actor
        )
        savings_liability = await ledger.create_account(
            code="2010", name="Member Savings Liability", account_type="liability", created_by=actor
        )
        loan_loss = await ledger.create_account(
            code="5100", name="Loan Loss Expense", account_type="expense", created_by=actor
        )
        savings_product = SavingsProduct(
            name="Standard Savings",
            interest_rate=Decimal("5"),
            minimum_balance=Decimal("0"),
            liability_account_id=savings_liability.id,
        )
        session.add(savings_product)
        await session.flush()
        await session.commit()
        return {
            "actor": actor,
            "principal_recv_id": principal_recv.id,
            "principal_recv_code": "1300",
            "interest_recv_id": interest_recv.id,
            "interest_recv_code": "1310",
            "interest_income_id": interest_income.id,
            "interest_income_code": "4100",
            "cash_account_id": cash_account.id,
            "cash_account_code": "1020",
            "disbursement_account": cash_account.id,
            "savings_liability_id": savings_liability.id,
            "savings_liability_code": "2010",
            "loan_loss_id": loan_loss.id,
            "loan_loss_code": "5100",
            "savings_product_id": savings_product.id,
        }
    finally:
        await session.close()


async def _make_approved_application(
    engine: AsyncEngine,
    accounts: dict,
    interest_method: str = "flat",
) -> tuple[LoanApplication, LoanProduct]:
    """Create product + submit + approve. Returns (application, product)."""
    product = await _make_product(
        engine,
        name=f"Disburse Test {interest_method}",
        interest_method=interest_method,
        gl_principal_receivable_code=accounts["principal_recv_code"],
        gl_interest_receivable_code=accounts["interest_recv_code"],
        gl_interest_income_code=accounts["interest_income_code"],
        gl_loan_loss_expense_code=accounts["loan_loss_code"],
        disbursement_destinations=["cash", "member_savings"],
        required_approvals=1,
    )

    submitter = uuid.uuid4()
    approver = uuid.uuid4()

    session = await _new_session(engine)
    try:
        app_svc = LoanApplicationService(session)
        approval_svc = ApprovalService(session)
        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("120000"),
            requested_term_periods=12,
            disbursement_destination="cash",
            disbursement_account_id=accounts["cash_account_id"],
            submitted_by=submitter,
            idempotency_key=f"app-{uuid.uuid4()}",
        )
        await approval_svc.approve(
            request_id=application.approval_request_id,
            actor_user_id=approver,
        )
        await session.commit()
        return application, product
    finally:
        await session.close()


# ── Disbursement tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disburse_cash_destination_creates_loan(test_engine):
    accounts = await _setup_disbursement_accounts(test_engine)
    application, product = await _make_approved_application(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=f"disb-{uuid.uuid4()}",
        )
        await session.commit()

        assert loan.id is not None
        assert loan.status == "disbursed"
        assert loan.outstanding_principal == Decimal("120000")
        assert loan.loan_reference.startswith("LN-")
        assert len(loan.loan_reference) == len("LN-202601-000001")
        assert loan.disbursed_at is not None
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_disburse_creates_installments(test_engine):
    accounts = await _setup_disbursement_accounts(test_engine)
    application, product = await _make_approved_application(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=f"disb-inst-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        installments = list(
            (await session2.execute(
                sa_select(LoanInstallment).where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
            )).scalars().all()
        )
        assert len(installments) == 12
        assert installments[0].period_number == 1
        total_principal = sum(i.principal_due for i in installments)
        assert abs(total_principal - Decimal("120000")) <= Decimal("1")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_disburse_gl_entry_balanced(test_engine):
    accounts = await _setup_disbursement_accounts(test_engine)
    application, product = await _make_approved_application(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=f"disb-gl-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        lines = list(
            (await session2.execute(
                sa_select(JournalLine).where(JournalLine.sub_ledger_id == loan.id)
            )).scalars().all()
        )
        assert len(lines) >= 2
        total_dr = sum(ln.debit_amount for ln in lines)
        total_cr = sum(ln.credit_amount for ln in lines)
        assert total_dr == total_cr
        for ln in lines:
            assert ln.sub_ledger_type == "loan"
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_disburse_flat_posts_interest_gl(test_engine):
    """Flat method: second GL entry Dr interest_receivable / Cr interest_income."""
    accounts = await _setup_disbursement_accounts(test_engine)
    application, product = await _make_approved_application(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=f"disb-flat-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        lines = list(
            (await session2.execute(
                sa_select(JournalLine).where(
                    JournalLine.sub_ledger_id == loan.id,
                    JournalLine.account_id == accounts["interest_recv_id"],
                )
            )).scalars().all()
        )
        assert any(ln.debit_amount > 0 for ln in lines)
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_disburse_idempotency(test_engine):
    """Same idempotency_key → returns same loan."""
    accounts = await _setup_disbursement_accounts(test_engine)
    application, product = await _make_approved_application(test_engine, accounts, "flat")

    idem_key = f"disb-idem-{uuid.uuid4()}"
    session = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session)
        loan1 = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=idem_key,
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanDisbursementService(session2)
        loan2 = await svc2.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=idem_key,
        )
        assert loan2.id == loan1.id
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_disburse_non_approved_raises(test_engine):
    accounts = await _setup_disbursement_accounts(test_engine)
    product = await _make_product(
        test_engine,
        gl_principal_receivable_code=accounts["principal_recv_code"],
        gl_interest_receivable_code=accounts["interest_recv_code"],
        gl_interest_income_code=accounts["interest_income_code"],
    )
    session = await _new_session(test_engine)
    try:
        app_svc = LoanApplicationService(session)
        application = await app_svc.submit(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("100000"),
            requested_term_periods=6,
            disbursement_destination="cash",
            disbursement_account_id=accounts["cash_account_id"],
            submitted_by=uuid.uuid4(),
            idempotency_key=f"not-approved-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = LoanDisbursementService(session2)
        with pytest.raises(ValueError, match="[Aa]pproved|status"):
            await svc.disburse(
                loan_application_id=application.id,
                actor_id=accounts["actor"],
                idempotency_key=f"nonapproved-disb-{uuid.uuid4()}",
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


# ── Interest accrual tests ────────────────────────────────────────────────────


async def _make_disbursed_loan(
    engine: AsyncEngine,
    accounts: dict,
    interest_method: str = "reducing_balance",
) -> Loan:
    """Create and disburse a loan. Returns the Loan object."""
    application, product = await _make_approved_application(
        engine, accounts, interest_method
    )
    session = await _new_session(engine)
    try:
        svc = LoanDisbursementService(session)
        loan = await svc.disburse(
            loan_application_id=application.id,
            actor_id=accounts["actor"],
            idempotency_key=f"accrual-disb-{uuid.uuid4()}",
        )
        await session.commit()
        return loan
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_accrue_interest_posts_gl_entry(test_engine):
    """Reducing balance: accrual for a loan with an installment due today posts a GL entry."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    today = date.today()
    session = await _new_session(test_engine)
    try:
        installments = list(
            (await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )).scalars().all()
        )
        installments[0].due_date = today
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _accrue_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        updated_loan = await session2.get(Loan, loan.id)
        assert updated_loan.accrued_interest > Decimal("0")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_accrue_interest_idempotent(test_engine):
    """Running accrual twice on the same day does not double-post."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    today = date.today()
    session = await _new_session(test_engine)
    try:
        installments = list(
            (await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )).scalars().all()
        )
        installments[0].due_date = today
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _accrue_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine)  # second run
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        updated_loan = await session2.get(Loan, loan.id)
        first_run_interest = updated_loan.accrued_interest
        assert first_run_interest > Decimal("0")
    finally:
        await session2.close()

    _engine2 = _create_engine(get_settings().database_url)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine2)
    await _engine2.dispose()

    session3 = await _new_session(test_engine)
    try:
        final_loan = await session3.get(Loan, loan.id)
        assert final_loan.accrued_interest == first_run_interest
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_accrue_skips_flat_loans(test_engine):
    """Flat method loans: accrual task does nothing (interest booked at disbursement)."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    today = date.today()
    session = await _new_session(test_engine)
    try:
        installments = list(
            (await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )).scalars().all()
        )
        installments[0].due_date = today
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _accrue_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        updated_loan = await session2.get(Loan, loan.id)
        assert updated_loan.accrued_interest == Decimal("0")
    finally:
        await session2.close()
        await _cleanup(test_engine)


# ── Repayment tests ───────────────────────────────────────────────────────────


async def _make_disbursed_loan_with_interest(
    engine: AsyncEngine,
    accounts: dict,
) -> tuple[Loan, Decimal]:
    """Disburse a reducing_balance loan, run one accrual cycle, return (loan, accrued_interest)."""
    loan = await _make_disbursed_loan(engine, accounts, "reducing_balance")

    today = date.today()
    session = await _new_session(engine)
    try:
        installment = (
            await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalars().first()
        installment.due_date = today
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _accrue_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _accrue_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session2 = await _new_session(engine)
    try:
        refreshed = await session2.get(Loan, loan.id)
        return refreshed, refreshed.accrued_interest
    finally:
        await session2.close()


@pytest.mark.asyncio
async def test_repayment_interest_first_allocation(test_engine):
    """Interest cleared before principal; snapshot and installment updated."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)
    assert accrued_interest > Decimal("0"), "Precondition: loan must have accrued interest"

    principal_before = loan.outstanding_principal
    repayment_amount = accrued_interest + Decimal("100.00")

    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        repayment = await svc.apply_repayment(
            loan_id=loan.id,
            amount=repayment_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    assert repayment.interest_applied == accrued_interest
    assert repayment.principal_applied == Decimal("100.00")
    assert repayment.overpayment == Decimal("0")

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.accrued_interest == Decimal("0")
        assert updated.outstanding_principal == principal_before - Decimal("100.00")
        assert updated.total_paid_interest == accrued_interest
        assert updated.total_paid_principal == Decimal("100.00")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_exact_payoff_closes_loan(test_engine):
    """Repayment = outstanding_principal + accrued_interest → loan.status = 'closed'."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    payoff_amount = loan.outstanding_principal + accrued_interest

    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        repayment = await svc.apply_repayment(
            loan_id=loan.id,
            amount=payoff_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.status == "closed"
        assert updated.closed_at is not None
        assert updated.outstanding_principal == Decimal("0")
        assert updated.accrued_interest == Decimal("0")
        assert repayment.overpayment == Decimal("0")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_overpayment(test_engine):
    """Repayment > total owed → overpayment > 0, loan closed."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    total_owed = loan.outstanding_principal + accrued_interest
    overpay_amount = total_owed + Decimal("50.00")

    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        repayment = await svc.apply_repayment(
            loan_id=loan.id,
            amount=overpay_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    assert repayment.overpayment == Decimal("50.00")

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.status == "closed"
        assert updated.outstanding_principal == Decimal("0")
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_gl_balanced(test_engine):
    """GL entry for repayment is balanced (sum debits == sum credits)."""
    from app.modules.ledger.models import JournalEntry, JournalLine
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    repayment_amount = accrued_interest + Decimal("50.00")

    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        repayment = await svc.apply_repayment(
            loan_id=loan.id,
            amount=repayment_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
        repayment_id = repayment.id
        journal_entry_id = repayment.journal_entry_id
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        lines = list(
            (await session2.execute(
                sa_select(JournalLine).where(JournalLine.journal_entry_id == journal_entry_id)
            )).scalars().all()
        )
        total_debit = sum(l.debit_amount for l in lines)
        total_credit = sum(l.credit_amount for l in lines)
        assert total_debit == total_credit

        for line in lines:
            assert line.sub_ledger_type == "loan"
            assert line.sub_ledger_id == loan.id
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_idempotency(test_engine):
    """Repayment with same idempotency_key twice → second call returns existing, one GL entry."""
    from app.modules.ledger.models import JournalEntry
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    idem_key = f"rpy-idem-{uuid.uuid4()}"

    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        r1 = await svc.apply_repayment(
            loan_id=loan.id,
            amount=Decimal("100.00"),
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=idem_key,
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanRepaymentService(session2)
        r2 = await svc2.apply_repayment(
            loan_id=loan.id,
            amount=Decimal("100.00"),
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=idem_key,
        )
        await session2.commit()
    finally:
        await session2.close()

    assert r1.id == r2.id

    session3 = await _new_session(test_engine)
    try:
        count = await session3.scalar(
            sa_select(func.count()).select_from(JournalEntry).where(
                JournalEntry.idempotency_key == f"loan-rpy-{idem_key}"
            )
        )
        assert count == 1
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_on_closed_loan_raises(test_engine):
    """Repayment on a closed loan raises ValueError."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    payoff_amount = loan.outstanding_principal + accrued_interest
    session = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session)
        await svc.apply_repayment(
            loan_id=loan.id,
            amount=payoff_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LoanRepaymentService(session2)
        with pytest.raises(ValueError, match="closed"):
            await svc2.apply_repayment(
                loan_id=loan.id,
                amount=Decimal("10.00"),
                payment_account_id=accounts["disbursement_account"],
                posted_by=accounts["actor"],
                idempotency_key=f"rpy-{uuid.uuid4()}",
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_repayment_updates_installments(test_engine):
    """Repayment payment marks oldest pending installments as paid/partial."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    session = await _new_session(test_engine)
    try:
        installment = (
            await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalars().first()
        installment_total = installment.total_due
    finally:
        await session.close()

    payment_amount = accrued_interest + installment_total

    session2 = await _new_session(test_engine)
    try:
        svc = LoanRepaymentService(session2)
        await svc.apply_repayment(
            loan_id=loan.id,
            amount=payment_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session2.commit()
    finally:
        await session2.close()

    session3 = await _new_session(test_engine)
    try:
        first_installment = (
            await session3.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalars().first()
        assert first_installment.status == "paid"
        assert first_installment.paid_at is not None
    finally:
        await session3.close()
        await _cleanup(test_engine)


# ── CreditQueryService tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_loans_eligible_for_fee_overdue(test_engine):
    """Loans with overdue installments appear in the eligibility query."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    yesterday = date.today() - timedelta(days=1)
    session = await _new_session(test_engine)
    try:
        installments = list(
            (await session.execute(
                sa_select(LoanInstallment).where(LoanInstallment.loan_id == loan.id)
            )).scalars().all()
        )
        for inst in installments:
            inst.due_date = yesterday
            inst.status = "overdue"
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = CreditQueryService(session2)
        eligible = await svc.find_loans_eligible_for_fee(
            as_of_date=date.today(),
            min_days_past_due=0,
        )
        loan_ids = [e["loan_id"] for e in eligible]
        assert loan.id in loan_ids
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_find_loans_eligible_for_fee_not_overdue(test_engine):
    """Loans with no overdue installments do not appear in eligibility query."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    session = await _new_session(test_engine)
    try:
        svc = CreditQueryService(session)
        eligible = await svc.find_loans_eligible_for_fee(
            as_of_date=date.today(),
            min_days_past_due=0,
        )
        loan_ids = [e["loan_id"] for e in eligible]
        assert loan.id not in loan_ids
    finally:
        await session.close()
        await _cleanup(test_engine)


# ── Penalty consumer tests ────────────────────────────────────────────────────


async def _insert_outbox_event(
    engine: AsyncEngine,
    event_type: str,
    payload: dict,
) -> uuid.UUID:
    """Insert a TenantOutboxEvent directly for testing."""
    import json
    from app.core.outbox.models import TenantOutboxEvent
    from datetime import datetime, UTC
    event_id = uuid.uuid4()
    session = await _new_session(engine)
    try:
        evt = TenantOutboxEvent(
            id=event_id,
            aggregate_type="loan",
            aggregate_id=uuid.uuid4(),
            event_type=event_type,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
        session.add(evt)
        await session.commit()
    finally:
        await session.close()
    return event_id


@pytest.mark.asyncio
async def test_consumer_fee_assessment_increments_accrued_penalties(test_engine):
    """FeeAssessmentCreated with target_type='loan' increments loans.accrued_penalties."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    assessment_id = uuid.uuid4()
    penalty_amount = Decimal("500.00")
    event_id = await _insert_outbox_event(
        test_engine,
        "FeeAssessmentCreated",
        {
            "assessment_id": str(assessment_id),
            "target_type": "loan",
            "target_id": str(loan.id),
            "amount": str(penalty_amount),
        },
    )

    from app.modules.credit.consumer import _process_tenant_events
    await _process_tenant_events(TEST_TENANT_SCHEMA, test_engine)

    session = await _new_session(test_engine)
    try:
        updated = await session.get(Loan, loan.id)
        assert updated.accrued_penalties == penalty_amount
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_consumer_fee_assessment_idempotent(test_engine):
    """Replaying FeeAssessmentCreated does not double-increment accrued_penalties."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    penalty_amount = Decimal("300.00")
    event_id = await _insert_outbox_event(
        test_engine,
        "FeeAssessmentCreated",
        {
            "assessment_id": str(uuid.uuid4()),
            "target_type": "loan",
            "target_id": str(loan.id),
            "amount": str(penalty_amount),
        },
    )

    from app.modules.credit.consumer import _process_tenant_events
    await _process_tenant_events(TEST_TENANT_SCHEMA, test_engine)
    await _process_tenant_events(TEST_TENANT_SCHEMA, test_engine)  # replay

    session = await _new_session(test_engine)
    try:
        updated = await session.get(Loan, loan.id)
        assert updated.accrued_penalties == penalty_amount  # not doubled
    finally:
        await session.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_consumer_fee_collection_decrements_accrued_penalties(test_engine):
    """FeeCollectionCreated with target_type='loan' decrements accrued_penalties, increments total_paid_penalties."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    penalty_amount = Decimal("200.00")
    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.accrued_penalties = penalty_amount
        await session.commit()
    finally:
        await session.close()

    collected_amount = Decimal("150.00")
    await _insert_outbox_event(
        test_engine,
        "FeeCollectionCreated",
        {
            "collection_id": str(uuid.uuid4()),
            "target_type": "loan",
            "target_id": str(loan.id),
            "amount_collected": str(collected_amount),
        },
    )

    from app.modules.credit.consumer import _process_tenant_events
    await _process_tenant_events(TEST_TENANT_SCHEMA, test_engine)

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.accrued_penalties == penalty_amount - collected_amount
        assert updated.total_paid_penalties == collected_amount
    finally:
        await session2.close()
        await _cleanup(test_engine)


# ── Arrears beat task tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_in_arrears_when_installment_overdue(test_engine):
    """Loan with an overdue installment → status transitions to in_arrears."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")
    assert loan.status == "disbursed"

    yesterday = date.today() - timedelta(days=1)
    session = await _new_session(test_engine)
    try:
        installment = (
            await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalars().first()
        installment.due_date = yesterday
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _mark_arrears_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _mark_arrears_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.status == "in_arrears"
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_clear_arrears_when_caught_up(test_engine):
    """Loan in in_arrears with all installments now paid → status reverts to disbursed."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.status = "in_arrears"
        await session.commit()
    finally:
        await session.close()

    from datetime import timezone
    session2 = await _new_session(test_engine)
    try:
        installments = list(
            (await session2.execute(
                sa_select(LoanInstallment).where(LoanInstallment.loan_id == loan.id)
            )).scalars().all()
        )
        for inst in installments:
            inst.status = "paid"
            inst.principal_paid = inst.principal_due
            inst.interest_paid = inst.interest_due
        await session2.commit()
    finally:
        await session2.close()

    from app.modules.credit.beat import _mark_arrears_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _mark_arrears_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session3 = await _new_session(test_engine)
    try:
        updated = await session3.get(Loan, loan.id)
        assert updated.status == "disbursed"
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_arrears_task_idempotent(test_engine):
    """Running arrears task twice → no double status flips."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    yesterday = date.today() - timedelta(days=1)
    session = await _new_session(test_engine)
    try:
        installment = (
            await session.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.period_number)
                .limit(1)
            )
        ).scalars().first()
        installment.due_date = yesterday
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _mark_arrears_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _mark_arrears_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _mark_arrears_for_tenant(TEST_TENANT_SCHEMA, _engine)  # second run
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.status == "in_arrears"
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_arrears_task_skips_closed_written_off(test_engine):
    """Closed and written_off loans are excluded from arrears processing."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "reducing_balance")

    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.status = "closed"
        await session.commit()
    finally:
        await session.close()

    yesterday = date.today() - timedelta(days=1)
    session2 = await _new_session(test_engine)
    try:
        inst = (
            await session2.execute(
                sa_select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .limit(1)
            )
        ).scalars().first()
        inst.due_date = yesterday
        await session2.commit()
    finally:
        await session2.close()

    from app.modules.credit.beat import _mark_arrears_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _mark_arrears_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session3 = await _new_session(test_engine)
    try:
        updated = await session3.get(Loan, loan.id)
        assert updated.status == "closed"
    finally:
        await session3.close()
        await _cleanup(test_engine)
        await _cleanup(test_engine)


# ── Write-off tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_off_below_threshold_direct(test_engine):
    """Write-off amount <= threshold → direct execution, no approval_request, status=written_off."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    # Update product to set write_off_threshold = 999999 so any write-off is direct.
    session = await _new_session(test_engine)
    try:
        from app.modules.credit.models import LoanProduct
        product = await session.get(LoanProduct, loan.loan_product_id)
        product.write_off_threshold = Decimal("999999.00")
        await session.commit()
    finally:
        await session.close()

    write_off_amount = loan.outstanding_principal

    session2 = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session2)
        result = await svc.write_off(
            loan_id=loan.id,
            amount=write_off_amount,
            reason="Non-recoverable debt",
            actor_id=accounts["actor"],
            idempotency_key=f"wo-{uuid.uuid4()}",
        )
        await session2.commit()
    finally:
        await session2.close()

    assert result["direct"] is True
    assert result["approval_request_id"] is None

    session3 = await _new_session(test_engine)
    try:
        updated = await session3.get(Loan, loan.id)
        assert updated.status == "written_off"
        assert updated.outstanding_principal == Decimal("0")
        assert updated.total_written_off == write_off_amount
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_write_off_gl_balanced(test_engine):
    """Write-off GL entry: Dr loan_loss_expense / Cr gl_principal_receivable_id — balanced."""
    from app.modules.ledger.models import JournalLine
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        from app.modules.credit.models import LoanProduct
        product = await session.get(LoanProduct, loan.loan_product_id)
        product.write_off_threshold = Decimal("999999.00")
        await session.commit()
    finally:
        await session.close()

    write_off_amount = Decimal("100.00")

    session2 = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session2)
        result = await svc.write_off(
            loan_id=loan.id,
            amount=write_off_amount,
            reason="Partial write-off",
            actor_id=accounts["actor"],
            idempotency_key=f"wo-{uuid.uuid4()}",
        )
        await session2.commit()
        journal_entry_id = result["journal_entry_id"]
    finally:
        await session2.close()

    session3 = await _new_session(test_engine)
    try:
        lines = list(
            (await session3.execute(
                sa_select(JournalLine).where(JournalLine.journal_entry_id == journal_entry_id)
            )).scalars().all()
        )
        total_debit = sum(l.debit_amount for l in lines)
        total_credit = sum(l.credit_amount for l in lines)
        assert total_debit == total_credit == write_off_amount

        for line in lines:
            assert line.sub_ledger_type == "loan"
            assert line.sub_ledger_id == loan.id
    finally:
        await session3.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_write_off_above_threshold_creates_approval_request(test_engine):
    """Write-off amount > threshold → approval_request created, GL not yet posted."""
    from app.modules.ledger.models import JournalEntry
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    # Product has write_off_threshold=0 by default → any amount > 0 needs approval.
    write_off_amount = Decimal("500.00")

    session = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session)
        result = await svc.write_off(
            loan_id=loan.id,
            amount=write_off_amount,
            reason="Needs approval",
            actor_id=accounts["actor"],
            idempotency_key=f"wo-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    assert result["direct"] is False
    assert result["approval_request_id"] is not None

    session2 = await _new_session(test_engine)
    try:
        updated = await session2.get(Loan, loan.id)
        assert updated.status != "written_off"
        assert updated.total_written_off == Decimal("0")

        count = await session2.scalar(
            sa_select(func.count()).select_from(JournalEntry).where(
                JournalEntry.reference.like("LOAN-WO-%")
            )
        )
        assert count == 0
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_write_off_already_written_off_raises(test_engine):
    """Write-off on a written_off loan raises ValueError."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.status = "written_off"
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session2)
        with pytest.raises(ValueError, match="written_off"):
            await svc.write_off(
                loan_id=loan.id,
                amount=Decimal("100.00"),
                reason="Double write-off",
                actor_id=accounts["actor"],
                idempotency_key=f"wo-{uuid.uuid4()}",
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_write_off_amount_exceeds_principal_raises(test_engine):
    """Write-off amount > outstanding_principal raises ValueError."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        from app.modules.credit.models import LoanProduct
        product = await session.get(LoanProduct, loan.loan_product_id)
        product.write_off_threshold = Decimal("999999.00")
        await session.commit()
    finally:
        await session.close()

    too_much = loan.outstanding_principal + Decimal("1.00")
    session2 = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session2)
        with pytest.raises(ValueError, match="outstanding_principal"):
            await svc.write_off(
                loan_id=loan.id,
                amount=too_much,
                reason="Too much",
                actor_id=accounts["actor"],
                idempotency_key=f"wo-{uuid.uuid4()}",
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_write_off_idempotency(test_engine):
    """Same idempotency_key twice → second call is no-op, returns same result."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        from app.modules.credit.models import LoanProduct
        product = await session.get(LoanProduct, loan.loan_product_id)
        product.write_off_threshold = Decimal("999999.00")
        await session.commit()
    finally:
        await session.close()

    idem_key = f"wo-idem-{uuid.uuid4()}"
    write_off_amount = Decimal("100.00")

    session2 = await _new_session(test_engine)
    try:
        svc = LoanWriteOffService(session2)
        r1 = await svc.write_off(
            loan_id=loan.id, amount=write_off_amount, reason="First",
            actor_id=accounts["actor"], idempotency_key=idem_key,
        )
        await session2.commit()
    finally:
        await session2.close()

    session3 = await _new_session(test_engine)
    try:
        svc2 = LoanWriteOffService(session3)
        r2 = await svc2.write_off(
            loan_id=loan.id, amount=write_off_amount, reason="Second",
            actor_id=accounts["actor"], idempotency_key=idem_key,
        )
        await session3.commit()
    finally:
        await session3.close()

    assert r1["journal_entry_id"] == r2["journal_entry_id"]

    session4 = await _new_session(test_engine)
    try:
        updated = await session4.get(Loan, loan.id)
        assert updated.total_written_off == write_off_amount  # not doubled
    finally:
        await session4.close()
        await _cleanup(test_engine)


# ── Reconciliation tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconciliation_no_drift_after_clean_lifecycle(test_engine, caplog):
    """After disburse → repay lifecycle, reconciliation finds no drift."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan, accrued_interest = await _make_disbursed_loan_with_interest(test_engine, accounts)

    repayment_amount = accrued_interest + Decimal("50.00")
    session = await _new_session(test_engine)
    try:
        from app.modules.credit.services.repayment import LoanRepaymentService
        svc = LoanRepaymentService(session)
        await svc.apply_repayment(
            loan_id=loan.id,
            amount=repayment_amount,
            payment_account_id=accounts["disbursement_account"],
            posted_by=accounts["actor"],
            idempotency_key=f"rpy-{uuid.uuid4()}",
        )
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _reconcile_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)

    with caplog.at_level(logging.ERROR):
        drifted = await _reconcile_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    assert drifted == 0, f"Expected no drift, got {drifted} drifted loans"
    assert "loan_snapshot_drift" not in caplog.text

    await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_reconciliation_detects_injected_drift(test_engine):
    """Direct UPDATE to outstanding_principal bypassing service → reconciliation detects drift."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.outstanding_principal = l.outstanding_principal - Decimal("999.00")
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _reconcile_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    drifted = await _reconcile_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    assert drifted == 1, f"Expected 1 drifted loan, got {drifted}"

    await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_reconciliation_does_not_modify_loan(test_engine):
    """Reconciliation task is read-only — does not update outstanding_principal."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")
    original_principal = loan.outstanding_principal

    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.outstanding_principal = l.outstanding_principal - Decimal("100.00")
        drifted_principal = l.outstanding_principal
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _reconcile_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    await _reconcile_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    session2 = await _new_session(test_engine)
    try:
        after = await session2.get(Loan, loan.id)
        assert after.outstanding_principal == drifted_principal
    finally:
        await session2.close()
        await _cleanup(test_engine)


@pytest.mark.asyncio
async def test_reconciliation_skips_closed_loans(test_engine):
    """Closed loans are excluded from reconciliation checks."""
    accounts = await _setup_disbursement_accounts(test_engine)
    loan = await _make_disbursed_loan(test_engine, accounts, "flat")

    session = await _new_session(test_engine)
    try:
        l = await session.get(Loan, loan.id)
        l.status = "closed"
        l.outstanding_principal = Decimal("0")
        await session.commit()
    finally:
        await session.close()

    from app.modules.credit.beat import _reconcile_for_tenant
    from sqlalchemy.ext.asyncio import create_async_engine as _create_engine
    from app.core.config import get_settings
    _engine = _create_engine(get_settings().database_url)
    drifted = await _reconcile_for_tenant(TEST_TENANT_SCHEMA, _engine)
    await _engine.dispose()

    assert drifted == 0, "Closed loan should not be checked"

    await _cleanup(test_engine)
