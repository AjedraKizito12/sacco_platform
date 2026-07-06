"""Integration tests for the tenant dashboard aggregates.

Uses the async_sessionmaker + commit + cleanup pattern (not the rollback
fixture) per the repo's tenant-service test convention. Rows are inserted
directly via the models — the aggregates are read-only, so how the rows got
there is irrelevant to what they compute.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.credit.models import Loan, LoanApplication, LoanProduct
from app.modules.credit.services.query import CreditQueryService
from app.modules.dashboard.service import TenantDashboardStatsService
from app.modules.ledger.models import JournalEntry
from app.modules.members.models import Member
from app.modules.members.service import MemberService
from app.modules.savings.models import (
    SavingsAccount,
    SavingsProduct,
    SavingsTransaction,
)
from app.modules.savings.service import SavingsService

pytestmark = pytest.mark.asyncio

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

    await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
    return session


async def _cleanup(engine: AsyncEngine) -> None:
    async with _factory(engine)() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        # Order matters for FKs: transactions → accounts → products; loans →
        # applications → products; entries; members last.
        await session.execute(delete(SavingsTransaction))
        await session.execute(delete(SavingsAccount))
        await session.execute(delete(SavingsProduct))
        await session.execute(delete(Loan))
        await session.execute(delete(LoanApplication))
        await session.execute(delete(LoanProduct))
        await session.execute(delete(JournalEntry))
        await session.execute(delete(Member))
        await session.commit()


def _member_kwargs(**overrides) -> dict:
    base = {
        "full_name": "Alice Nakato",
        "date_of_birth": date(1990, 5, 15),
        "gender": "female",
        "created_by": uuid.uuid4(),
    }
    base.update(overrides)
    return base


async def _insert_loan(
    session: AsyncSession, *, status: str, outstanding: Decimal, member_id: uuid.UUID
) -> Loan:
    """Insert a minimal Loan (+ product + application) for portfolio tests."""
    product = LoanProduct(
        name=f"P-{uuid.uuid4()}",
        interest_method="flat",
        annual_interest_rate=Decimal("18.0000"),
        repayment_frequency="monthly",
        max_term_periods=12,
        min_amount=Decimal("1000"),
        max_amount=Decimal("1000000"),
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
        member_id=member_id,
        requested_amount=outstanding,
        requested_term_periods=12,
        disbursement_destination="cash",
        status="disbursed",
        idempotency_key=str(uuid.uuid4()),
    )
    session.add(application)
    await session.flush()

    loan = Loan(
        loan_reference=f"L-{uuid.uuid4().hex[:8].upper()}",
        loan_application_id=application.id,
        loan_product_id=product.id,
        member_id=member_id,
        status=status,
        principal_amount=outstanding,
        outstanding_principal=outstanding,
        interest_method="flat",
        annual_interest_rate=Decimal("18.0000"),
        repayment_frequency="monthly",
        term_periods=12,
        repayment_allocation="INTEREST_PRINCIPAL",
        disbursement_destination="cash",
        gl_principal_receivable_id=uuid.uuid4(),
        gl_interest_receivable_id=uuid.uuid4(),
        gl_interest_income_id=uuid.uuid4(),
        gl_disbursement_account_id=uuid.uuid4(),
        disbursed_by=uuid.uuid4(),
        idempotency_key=str(uuid.uuid4()),
    )
    session.add(loan)
    await session.flush()
    return loan


async def _insert_savings_account(session: AsyncSession, member_id: uuid.UUID) -> SavingsAccount:
    product = SavingsProduct(
        name=f"S-{uuid.uuid4()}",
        interest_rate=Decimal("2.0000"),
        minimum_balance=Decimal("0"),
        liability_account_id=uuid.uuid4(),
    )
    session.add(product)
    await session.flush()

    account = SavingsAccount(
        member_id=member_id,
        savings_product_id=product.id,
        product_name=product.name,
        interest_rate=product.interest_rate,
        minimum_balance=product.minimum_balance,
        liability_account_id=product.liability_account_id,
    )
    session.add(account)
    await session.flush()
    return account


async def _insert_txn(
    session: AsyncSession, account_id: uuid.UUID, ttype: str, amount: Decimal
) -> None:
    entry = JournalEntry(
        reference=f"JE-{uuid.uuid4().hex[:8]}",
        description="test",
        posted_by=uuid.uuid4(),
        idempotency_key=str(uuid.uuid4()),
    )
    session.add(entry)
    await session.flush()
    session.add(
        SavingsTransaction(
            savings_account_id=account_id,
            transaction_type=ttype,
            amount=amount,
            journal_entry_id=entry.id,
            posted_by=uuid.uuid4(),
            idempotency_key=str(uuid.uuid4()),
        )
    )
    await session.flush()


# ── MemberService.count_by_status ───────────────────────────────────────────


async def test_count_by_status(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = MemberService(session)
        m_pending = await svc.register_member(**_member_kwargs(email="p@x.com"))
        m_active1 = await svc.register_member(**_member_kwargs(email="a1@x.com"))
        m_active2 = await svc.register_member(**_member_kwargs(email="a2@x.com"))
        m_susp = await svc.register_member(**_member_kwargs(email="s@x.com"))
        # register_member starts everyone 'pending'; nudge statuses directly.
        m_active1.status = "active"
        m_active2.status = "active"
        m_susp.status = "suspended"
        assert m_pending.status == "pending"
        await session.commit()

        counts = await svc.count_by_status()
        assert counts == {"pending": 1, "active": 2, "suspended": 1}
    finally:
        await session.close()
        await _cleanup(test_engine)


# ── CreditQueryService.portfolio_summary ────────────────────────────────────


async def test_portfolio_summary(test_engine):
    session = await _new_session(test_engine)
    try:
        member_a = uuid.uuid4()
        member_b = uuid.uuid4()
        await _insert_loan(
            session, status="disbursed", outstanding=Decimal("40000"), member_id=member_a
        )
        await _insert_loan(
            session, status="in_arrears", outstanding=Decimal("10000"), member_id=member_b
        )
        # closed loans don't count toward outstanding principal.
        await _insert_loan(
            session, status="closed", outstanding=Decimal("5000"), member_id=member_a
        )
        await session.commit()

        summary = await CreditQueryService(session).portfolio_summary()
        assert summary.outstanding_principal_total == Decimal("50000")
        assert summary.loans_by_status == {"disbursed": 1, "in_arrears": 1, "closed": 1}
        assert summary.members_in_arrears == 1
    finally:
        await session.close()
        await _cleanup(test_engine)


# ── CreditQueryService.count_applications_awaiting_decision ──────────────────


async def _insert_application(session: AsyncSession, *, status: str) -> None:
    """Insert a bare LoanApplication (+ product) in the given status."""
    product = LoanProduct(
        name=f"P-{uuid.uuid4()}",
        interest_method="flat",
        annual_interest_rate=Decimal("18.0000"),
        repayment_frequency="monthly",
        max_term_periods=12,
        min_amount=Decimal("1000"),
        max_amount=Decimal("1000000"),
        required_approvals=1,
        disbursement_destinations=["cash"],
        gl_principal_receivable_code="1300",
        gl_interest_receivable_code="1310",
        gl_interest_income_code="4100",
    )
    session.add(product)
    await session.flush()
    session.add(
        LoanApplication(
            loan_product_id=product.id,
            member_id=uuid.uuid4(),
            requested_amount=Decimal("10000"),
            requested_term_periods=12,
            disbursement_destination="cash",
            status=status,
            idempotency_key=str(uuid.uuid4()),
        )
    )
    await session.flush()


async def test_count_applications_awaiting_decision(test_engine):
    session = await _new_session(test_engine)
    try:
        # Only 'submitted' and 'under_review' await an operator decision.
        await _insert_application(session, status="submitted")
        await _insert_application(session, status="under_review")
        await _insert_application(session, status="under_review")
        await _insert_application(session, status="draft")  # not submitted yet
        await _insert_application(session, status="approved")  # already decided
        await _insert_application(session, status="rejected")  # already decided
        await session.commit()

        count = await CreditQueryService(session).count_applications_awaiting_decision()
        assert count == 3
    finally:
        await session.close()
        await _cleanup(test_engine)


# ── ApprovalService.count_pending (tenant scope) ─────────────────────────────


async def _insert_approval(session: AsyncSession, *, status: str) -> None:
    from datetime import datetime

    from app.modules.maker_checker.models.tenant import TenantApprovalRequest

    session.add(
        TenantApprovalRequest(
            operation_type="loans.approve_application",
            payload={},
            requested_by=uuid.uuid4(),
            requested_at=datetime.now(UTC),
            required_approvals=1,
            status=status,
        )
    )
    await session.flush()


async def test_count_pending_approvals(test_engine):
    session = await _new_session(test_engine)
    try:
        from app.modules.maker_checker.service import ApprovalService

        await _insert_approval(session, status="pending")
        await _insert_approval(session, status="pending")
        await _insert_approval(session, status="approved")  # already decided
        await _insert_approval(session, status="rejected")  # already decided
        await session.commit()

        count = await ApprovalService(session).count_pending()
        assert count == 2
    finally:
        await session.execute(
            text("DELETE FROM approval_requests")  # noqa: S608
        )
        await session.commit()
        await session.close()
        await _cleanup(test_engine)


# ── SavingsService.total_balance_all_accounts ───────────────────────────────


async def test_total_balance_all_accounts(test_engine):
    session = await _new_session(test_engine)
    try:
        member = await MemberService(session).register_member(**_member_kwargs())
        await session.flush()
        account = await _insert_savings_account(session, member.id)
        await _insert_txn(session, account.id, "deposit", Decimal("1000"))
        await _insert_txn(session, account.id, "SYSTEM_CREDIT", Decimal("500"))
        await _insert_txn(session, account.id, "withdrawal", Decimal("200"))
        # EXTERNAL_CREDIT is NOT counted by get_balance, so it must NOT be
        # counted here either (consistency with per-account balances).
        await _insert_txn(session, account.id, "EXTERNAL_CREDIT", Decimal("999"))
        await session.commit()

        total = await SavingsService(session).total_balance_all_accounts()
        assert total == Decimal("1300")  # 1000 + 500 - 200
    finally:
        await session.close()
        await _cleanup(test_engine)


# ── Composed service ────────────────────────────────────────────────────────


async def test_compute_empty_schema(test_engine):
    session = await _new_session(test_engine)
    try:
        stats = await TenantDashboardStatsService(session).compute()
        assert stats.members == {}
        assert stats.total_members == 0
        assert stats.total_savings == Decimal("0")
        assert stats.loans_outstanding_principal == Decimal("0")
        assert stats.loans_by_status == {}
        assert stats.members_in_arrears == 0
        assert stats.approvals_pending == 0
        assert stats.applications_pending == 0
        assert stats.last_updated is not None
    finally:
        await session.close()
        await _cleanup(test_engine)
