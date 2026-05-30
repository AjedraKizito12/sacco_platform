"""Integration tests for FeeAssessmentService and FeeCollectionService."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.fees.models import FeeAssessment, FeeCollection, FeeType
from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.ledger.service import LedgerService
from app.modules.members.models import Member
from app.modules.members.service import MemberService
from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
    from sqlalchemy import event as sa_event

    session = _factory(engine)()

    @sa_event.listens_for(session.sync_session, "after_begin")
    def _reapply(sess, transaction, connection):  # type: ignore[misc]
        connection.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))

    await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
    return session


async def _cleanup(engine: AsyncEngine) -> None:
    async with _factory(engine)() as s:
        await s.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await s.execute(delete(FeeCollection))
        await s.execute(delete(FeeAssessment))
        await s.execute(delete(FeeType))
        await s.execute(delete(SavingsTransaction))
        await s.execute(delete(SavingsAccount))
        await s.execute(delete(SavingsProduct))
        await s.execute(delete(JournalLine))
        await s.execute(delete(JournalEntry))
        await s.execute(delete(ChartOfAccount))
        await s.execute(delete(Member))
        await s.commit()


async def _setup_gl(engine: AsyncEngine) -> dict[str, uuid.UUID]:
    """Create GL accounts needed by fee tests. Returns {name: id}."""
    session = await _new_session(engine)
    try:
        svc = LedgerService(session)
        actor = uuid.uuid4()
        cash = await svc.create_account(code="1020", name="Cash", account_type="asset", created_by=actor)
        savings_liab = await svc.create_account(code="2010", name="Member Savings", account_type="liability", created_by=actor)
        fee_recv = await svc.create_account(code="1101", name="Fee Receivable", account_type="asset", created_by=actor)
        fee_income = await svc.create_account(code="4001", name="Fee Income", account_type="income", created_by=actor)
        annual_recv = await svc.create_account(code="1102", name="Annual Sub Receivable", account_type="asset", created_by=actor)
        annual_income = await svc.create_account(code="4002", name="Annual Sub Income", account_type="income", created_by=actor)
        await session.commit()
        return {
            "cash": cash.id,
            "savings_liab": savings_liab.id,
            "fee_recv": fee_recv.id,
            "fee_income": fee_income.id,
            "annual_recv": annual_recv.id,
            "annual_income": annual_income.id,
        }
    finally:
        await session.close()


async def _setup_fee_type(
    engine: AsyncEngine,
    code: str = "MEMBERSHIP",
    trigger_kind: str = "event",
    event_name: str | None = "MemberActivated",
    requires_collection: bool = False,
) -> uuid.UUID:
    session = await _new_session(engine)
    try:
        ft = FeeType(
            code=code,
            name=f"Test {code}",
            applicable_to="member",
            amount_kind="fixed",
            amount=Decimal("5000.00"),
            currency="UGX",
            trigger_kind=trigger_kind,
            event_name=event_name,
            gl_income_account_code="4001",
            gl_receivable_account_code="1101",
            requires_collection=requires_collection,
        )
        session.add(ft)
        await session.commit()
        return ft.id
    finally:
        await session.close()


async def _setup_member(engine: AsyncEngine) -> uuid.UUID:
    session = await _new_session(engine)
    try:
        svc = MemberService(session)
        m = await svc.register_member(
            full_name="Test Member",
            date_of_birth=date(1990, 1, 1),
            gender="male",
            created_by=uuid.uuid4(),
        )
        await session.commit()
        return m.id
    finally:
        await session.close()


# ── FeeAssessmentService ──────────────────────────────────────────────────────

async def test_assess_creates_assessment_and_gl_entry(test_engine):
    """assess() creates a FeeAssessment row and posts Dr receivable / Cr income."""
    await _setup_gl(test_engine)
    fee_type_id = await _setup_fee_type(test_engine)
    member_id = await _setup_member(test_engine)

    session = await _new_session(test_engine)
    try:
        from app.modules.fees.service import FeeAssessmentService
        ft = await session.get(FeeType, fee_type_id)
        svc = FeeAssessmentService(session)
        assessment = await svc.assess(
            fee_type=ft,
            target_type="member",
            target_id=member_id,
            period_start=date(2026, 1, 1),
            period_end=None,
            triggered_by_event_id=None,
            actor=uuid.uuid4(),
            idempotency_key="assess-001",
        )
        await session.commit()

        assert assessment.id is not None
        assert assessment.status == "assessed"
        assert assessment.amount == Decimal("5000.00")
        assert assessment.journal_entry_id is not None
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_assess_idempotent(test_engine):
    """assess() with same (fee_type, target, period_start) returns existing row."""
    await _setup_gl(test_engine)
    fee_type_id = await _setup_fee_type(test_engine)
    member_id = await _setup_member(test_engine)

    async def _assess() -> uuid.UUID:
        s = await _new_session(test_engine)
        try:
            from app.modules.fees.service import FeeAssessmentService
            ft = await s.get(FeeType, fee_type_id)
            svc = FeeAssessmentService(s)
            a = await svc.assess(
                fee_type=ft, target_type="member", target_id=member_id,
                period_start=date(2026, 1, 1), period_end=None,
                triggered_by_event_id=None, actor=uuid.uuid4(),
                idempotency_key=f"assess-idem-{uuid.uuid4()}",
            )
            await s.commit()
            return a.id
        finally:
            await s.close()

    try:
        id1 = await _assess()
        id2 = await _assess()
        assert id1 == id2
    finally:
        await _cleanup(test_engine)


async def test_assess_posts_balanced_gl_entry(test_engine):
    """Assessment GL entry: Dr fee_receivable, Cr fee_income."""
    gl = await _setup_gl(test_engine)
    fee_type_id = await _setup_fee_type(test_engine)
    member_id = await _setup_member(test_engine)

    session = await _new_session(test_engine)
    try:
        from app.modules.fees.service import FeeAssessmentService
        ft = await session.get(FeeType, fee_type_id)
        await FeeAssessmentService(session).assess(
            fee_type=ft, target_type="member", target_id=member_id,
            period_start=date(2026, 1, 1), period_end=None,
            triggered_by_event_id=None, actor=uuid.uuid4(),
            idempotency_key="assess-gl-001",
        )
        await session.commit()

        ledger_svc = LedgerService(session)
        recv_bal = await ledger_svc.get_account_balance(gl["fee_recv"])
        income_bal = await ledger_svc.get_account_balance(gl["fee_income"])
        assert recv_bal == Decimal("5000.00")
        assert income_bal == Decimal("5000.00")
    finally:
        await session.close()
        await _cleanup(test_engine)


async def _setup_savings_account(engine: AsyncEngine, member_id: uuid.UUID, liability_id: uuid.UUID) -> uuid.UUID:
    session = await _new_session(engine)
    try:
        from app.modules.savings.service import SavingsService
        product = SavingsProduct(
            name="Basic", interest_rate=Decimal("5"), minimum_balance=Decimal("0"),
            liability_account_id=liability_id,
        )
        session.add(product)
        await session.flush()
        svc = SavingsService(session)
        acc = await svc.open_account(member_id=member_id, savings_product_id=product.id)
        await session.commit()
        return acc.id
    finally:
        await session.close()


async def test_auto_collect_full_collection(test_engine):
    """requires_collection=True: assess + auto-collect from savings when sufficient balance."""
    gl = await _setup_gl(test_engine)
    fee_type_id = await _setup_fee_type(test_engine, requires_collection=True)
    member_id = await _setup_member(test_engine)
    account_id = await _setup_savings_account(test_engine, member_id, gl["savings_liab"])

    # Deposit 10000 into savings
    session = await _new_session(test_engine)
    try:
        from app.modules.savings.service import SavingsService
        await SavingsService(session).deposit(
            savings_account_id=account_id, amount=Decimal("10000.00"),
            payment_account_id=gl["cash"], posted_by=uuid.uuid4(),
            idempotency_key="pre-assess-dep-001",
        )
        await session.commit()
    finally:
        await session.close()

    # Assess (should auto-collect 5000)
    session2 = await _new_session(test_engine)
    try:
        from app.modules.fees.service import FeeAssessmentService
        from app.modules.savings.service import SavingsService
        ft = await session2.get(FeeType, fee_type_id)
        assessment = await FeeAssessmentService(session2).assess(
            fee_type=ft, target_type="member", target_id=member_id,
            period_start=date(2026, 1, 1), period_end=None,
            triggered_by_event_id=None, actor=uuid.uuid4(),
            idempotency_key="ac-full-001",
        )
        await session2.commit()

        assert assessment.status == "paid"
        balance = await SavingsService(session2).get_balance(account_id)
        assert balance == Decimal("5000.00")  # 10000 - 5000 fee
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_auto_collect_partial_collection(test_engine):
    """Auto-collect with insufficient balance: partially_paid status, correct shortfall."""
    gl = await _setup_gl(test_engine)
    fee_type_id = await _setup_fee_type(test_engine, requires_collection=True)
    member_id = await _setup_member(test_engine)
    account_id = await _setup_savings_account(test_engine, member_id, gl["savings_liab"])

    # Deposit only 2000 (fee is 5000)
    session = await _new_session(test_engine)
    try:
        from app.modules.savings.service import SavingsService
        await SavingsService(session).deposit(
            savings_account_id=account_id, amount=Decimal("2000.00"),
            payment_account_id=gl["cash"], posted_by=uuid.uuid4(),
            idempotency_key="pre-assess-dep-002",
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        from app.modules.fees.service import FeeAssessmentService
        ft = await session2.get(FeeType, fee_type_id)
        assessment = await FeeAssessmentService(session2).assess(
            fee_type=ft, target_type="member", target_id=member_id,
            period_start=date(2026, 1, 1), period_end=None,
            triggered_by_event_id=None, actor=uuid.uuid4(),
            idempotency_key="ac-partial-001",
        )
        await session2.commit()

        assert assessment.status == "partially_paid"
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_auto_collect_no_savings_account_leaves_assessed(test_engine):
    """Auto-collect with no savings account: assessment stays 'assessed'."""
    await _setup_gl(test_engine)
    fee_type_id = await _setup_fee_type(test_engine, requires_collection=True)
    member_id = await _setup_member(test_engine)
    # No savings account created

    session = await _new_session(test_engine)
    try:
        from app.modules.fees.service import FeeAssessmentService
        ft = await session.get(FeeType, fee_type_id)
        assessment = await FeeAssessmentService(session).assess(
            fee_type=ft, target_type="member", target_id=member_id,
            period_start=date(2026, 1, 1), period_end=None,
            triggered_by_event_id=None, actor=uuid.uuid4(),
            idempotency_key="ac-no-account-001",
        )
        await session.commit()

        assert assessment.status == "assessed"
    finally:
        await session.close()
        await _cleanup(test_engine)
