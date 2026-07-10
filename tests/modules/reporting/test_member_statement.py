# tests/modules/reporting/test_member_statement.py
"""Consolidated member statement: service context + HTTP endpoint."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    pass

from app.modules.credit.models import (
    Loan,
    LoanApplication,
    LoanInstallment,
    LoanProduct,
)
from app.modules.fees.models import FeeAssessment, FeeType
from app.modules.ledger.models import JournalEntry
from app.modules.members.models import Member
from app.modules.savings.models import (
    SavingsAccount,
    SavingsProduct,
    SavingsTransaction,
)
from app.modules.shares.models import (
    MemberShareAccount,
    ShareProduct,
    ShareTransaction,
)

TEST_SCHEMA = "tenant_test"
_SYSTEM = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _new_session(engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()

    @event.listens_for(session.sync_session, "after_begin")
    def _set_path(sess, tx, conn):  # noqa: ANN001, ANN202
        conn.exec_driver_sql(f"SET LOCAL search_path TO {TEST_SCHEMA}, platform")

    return session


async def _je(session: AsyncSession, ref: str, when: datetime) -> JournalEntry:
    je = JournalEntry(
        reference=ref,
        description=ref,
        posted_by=str(_SYSTEM),
        posted_at=when,
        idempotency_key=f"mstmt-je-{uuid.uuid4()}",
    )
    session.add(je)
    await session.flush()
    return je


async def _seed_member_with_everything(session: AsyncSession) -> uuid.UUID:
    """One member with: 1 savings account (3 txns), 1 share account (1 txn),
    1 active loan (2 installments), 1 fee assessment. Txn dates span
    2026-01-10 .. 2026-02-15 so range tests can slice."""
    member = Member(
        member_number=f"M-{uuid.uuid4().hex[:8]}",
        full_name="Statement Member",
        date_of_birth=date(1990, 1, 1),
        gender="female",
        status="active",
        portal_enabled=True,
    )
    session.add(member)
    await session.flush()

    # Savings: deposits 1000 (Jan 10), 500 (Jan 20); withdrawal 200 (Feb 15).
    sav_product = SavingsProduct(
        name="Regular Savings",
        interest_rate=Decimal("5.00"),
        minimum_balance=Decimal("0"),
        liability_account_id=uuid.uuid4(),
        is_active=True,
    )
    session.add(sav_product)
    await session.flush()
    account = SavingsAccount(
        member_id=member.id,
        savings_product_id=sav_product.id,
        product_name="Regular Savings",
        interest_rate=Decimal("5.00"),
        minimum_balance=Decimal("0"),
        liability_account_id=sav_product.liability_account_id,
    )
    session.add(account)
    await session.flush()
    for when, txn_type, amount in (
        (datetime(2026, 1, 10, tzinfo=UTC), "deposit", Decimal("1000")),
        (datetime(2026, 1, 20, tzinfo=UTC), "deposit", Decimal("500")),
        (datetime(2026, 2, 15, tzinfo=UTC), "withdrawal", Decimal("200")),
    ):
        je = await _je(session, f"MSTMT-SAV-{uuid.uuid4().hex[:6]}", when)
        session.add(
            SavingsTransaction(
                savings_account_id=account.id,
                transaction_type=txn_type,
                amount=amount,
                narration=f"{txn_type} {amount}",
                journal_entry_id=je.id,
                posted_by=_SYSTEM,
                posted_at=when,
                idempotency_key=f"mstmt-sav-{uuid.uuid4()}",
            )
        )

    # Shares: one purchase of 10 shares, 5000 total (Jan 15).
    share_product = ShareProduct(
        name="Ordinary Shares",
        par_value=Decimal("500"),
        share_capital_account_id=uuid.uuid4(),
        is_active=True,
    )
    session.add(share_product)
    await session.flush()
    share_account = MemberShareAccount(
        member_id=member.id, share_product_id=share_product.id
    )
    session.add(share_account)
    await session.flush()
    share_je = await _je(session, "MSTMT-SHR-1", datetime(2026, 1, 15, tzinfo=UTC))
    session.add(
        ShareTransaction(
            share_account_id=share_account.id,
            transaction_type="purchase",
            quantity=10,
            amount=Decimal("5000"),
            journal_entry_id=share_je.id,
            posted_by=_SYSTEM,
            posted_at=datetime(2026, 1, 15, tzinfo=UTC),
            idempotency_key=f"mstmt-shr-{uuid.uuid4()}",
        )
    )

    # Loan: active, 2 installments.
    loan_product = LoanProduct(
        name="Statement Loan",
        interest_method="flat",
        annual_interest_rate=Decimal("12.00"),
        repayment_frequency="monthly",
        max_term_periods=24,
        min_amount=Decimal("100"),
        max_amount=Decimal("100000"),
        disbursement_destinations=["cash"],
        gl_principal_receivable_code="1300",
        gl_interest_receivable_code="1310",
        gl_interest_income_code="4100",
    )
    session.add(loan_product)
    await session.flush()
    application = LoanApplication(
        loan_product_id=loan_product.id,
        member_id=member.id,
        requested_amount=Decimal("10000"),
        requested_term_periods=2,
        disbursement_destination="cash",
        status="approved",
        idempotency_key=f"mstmt-app-{uuid.uuid4()}",
    )
    session.add(application)
    await session.flush()
    loan = Loan(
        loan_reference=f"LN-{uuid.uuid4().hex[:8]}",
        loan_application_id=application.id,
        loan_product_id=loan_product.id,
        member_id=member.id,
        status="disbursed",
        principal_amount=Decimal("10000"),
        interest_method="flat",
        annual_interest_rate=Decimal("12.00"),
        repayment_frequency="monthly",
        term_periods=2,
        repayment_allocation="INTEREST_PRINCIPAL",
        disbursement_destination="cash",
        gl_principal_receivable_id=uuid.uuid4(),
        gl_interest_receivable_id=uuid.uuid4(),
        gl_interest_income_id=uuid.uuid4(),
        gl_disbursement_account_id=uuid.uuid4(),
        outstanding_principal=Decimal("10000"),
        disbursed_at=datetime(2026, 1, 5, tzinfo=UTC),
        disbursed_by=_SYSTEM,
        idempotency_key=f"mstmt-loan-{uuid.uuid4()}",
    )
    session.add(loan)
    await session.flush()
    for n in (1, 2):
        session.add(
            LoanInstallment(
                loan_id=loan.id,
                period_number=n,
                due_date=date(2026, 1 + n, 5),
                principal_due=Decimal("5000"),
                interest_due=Decimal("100"),
                total_due=Decimal("5100"),
            )
        )

    # Fee: one member fee assessed Jan 12.
    fee_type = FeeType(
        code=f"MSTMT-{uuid.uuid4().hex[:6]}",
        name="Annual Membership Fee",
        applicable_to="member",
        amount=Decimal("250"),
        currency="UGX",
        trigger_kind="schedule",
        gl_income_account_code="4200",
        gl_receivable_account_code="1200",
    )
    session.add(fee_type)
    await session.flush()
    fee_je = await _je(session, "MSTMT-FEE-1", datetime(2026, 1, 12, tzinfo=UTC))
    session.add(
        FeeAssessment(
            fee_type_id=fee_type.id,
            target_type="member",
            target_id=member.id,
            period_start=date(2026, 1, 1),
            amount=Decimal("250"),
            currency="UGX",
            journal_entry_id=fee_je.id,
            assessed_at=datetime(2026, 1, 12, tzinfo=UTC),
        )
    )
    await session.commit()
    return member.id


async def _cleanup(engine: AsyncEngine) -> None:
    session = _new_session(engine)
    async with session:
        for tbl in (
            "loan_installments",
            "loans",
            "loan_applications",
            "loan_products",
            "fee_assessments",
            "fee_types",
            "share_transactions",
            "member_share_accounts",
            "share_products",
            "savings_transactions",
            "savings_accounts",
            "savings_products",
        ):
            await session.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        await session.execute(
            text("DELETE FROM journal_entries WHERE reference LIKE 'MSTMT-%'")
        )
        await session.execute(
            text(
                "DELETE FROM audit_log WHERE table_name IN ("
                "'members', 'loan_products', 'loan_applications', 'loans', "
                "'share_products', 'member_share_accounts', 'fee_types', "
                "'savings_products', 'savings_accounts')"
            )
        )
        await session.execute(text("DELETE FROM members"))
        await session.commit()


@pytest.fixture(autouse=True)
async def _clean(test_engine: AsyncEngine):  # noqa: ANN201
    yield
    await _cleanup(test_engine)


# ── Service ───────────────────────────────────────────────────────────────────


async def test_build_context_gathers_all_sections(test_engine: AsyncEngine) -> None:
    from app.modules.reporting.services.member_statement import MemberStatementService

    seed_session = _new_session(test_engine)
    async with seed_session:
        member_id = await _seed_member_with_everything(seed_session)
    session = _new_session(test_engine)
    async with session:
        member = await session.get(Member, member_id)
        assert member is not None
        ctx = await MemberStatementService(session).build_context(
            member, from_date=None, to_date=None
        )
    assert ctx["member"].id == member_id
    sav = ctx["savings"][0]
    assert sav["opening_balance"] == Decimal("0")
    assert sav["closing_balance"] == Decimal("1300")  # 1000 + 500 - 200
    assert [ln["running"] for ln in sav["lines"]] == [
        Decimal("1000"),
        Decimal("1500"),
        Decimal("1300"),
    ]
    shares = ctx["shares"][0]
    assert shares["total_quantity"] == 10
    assert shares["total_value"] == Decimal("5000")
    assert shares["product_name"] == "Ordinary Shares"
    loan = ctx["loans"][0]
    assert loan["loan"].outstanding_principal == Decimal("10000")
    assert [i.period_number for i in loan["installments"]] == [1, 2]
    assert ctx["fees"][0]["fee_name"] == "Annual Membership Fee"


async def test_build_context_range_filters_and_opening_balance(
    test_engine: AsyncEngine,
) -> None:
    from app.modules.reporting.services.member_statement import MemberStatementService

    seed_session = _new_session(test_engine)
    async with seed_session:
        member_id = await _seed_member_with_everything(seed_session)
    session = _new_session(test_engine)
    async with session:
        member = await session.get(Member, member_id)
        assert member is not None
        ctx = await MemberStatementService(session).build_context(
            member, from_date=date(2026, 2, 1), to_date=date(2026, 2, 28)
        )
    sav = ctx["savings"][0]
    # Jan deposits fall before the range -> opening balance, not lines.
    assert sav["opening_balance"] == Decimal("1500")
    assert len(sav["lines"]) == 1
    assert sav["lines"][0]["running"] == Decimal("1300")
    # Share purchase (Jan 15) is outside the range.
    assert ctx["shares"][0]["txns"] == []
    # Fee assessed Jan 12 is outside the range.
    assert ctx["fees"] == []
    # Loans always show (current snapshot + schedule).
    assert len(ctx["loans"]) == 1


async def test_member_statement_template_renders_pdf(test_engine: AsyncEngine) -> None:
    from app.modules.reporting._base import render_pdf
    from app.modules.reporting.services.member_statement import MemberStatementService

    seed_session = _new_session(test_engine)
    async with seed_session:
        member_id = await _seed_member_with_everything(seed_session)
    session = _new_session(test_engine)
    async with session:
        member = await session.get(Member, member_id)
        assert member is not None
        ctx = await MemberStatementService(session).build_context(
            member, from_date=None, to_date=None
        )
    pdf = render_pdf("member_statement.html", ctx)
    assert pdf[:4] == b"%PDF"
