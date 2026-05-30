"""Integration tests for ShareService.

Uses async_sessionmaker + commit + cleanup pattern (not the rollback fixture)
to avoid asyncpg protocol-state errors with flush() in session-scoped event loops.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.modules.shares.executors  # noqa: F401 — registers shares executor in approval_registry
from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.ledger.service import LedgerService
from app.modules.maker_checker.models.tenant import TenantApprovalAction, TenantApprovalRequest
from app.modules.maker_checker.service import ApprovalService
from app.modules.members.models import Member
from app.modules.members.service import MemberService
from app.modules.shares.models import MemberShareAccount, ShareProduct, ShareTransaction
from app.modules.shares.service import ShareService

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
    async with _factory(engine)() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(ShareTransaction))
        await session.execute(delete(MemberShareAccount))
        await session.execute(delete(ShareProduct))
        await session.execute(delete(JournalLine))
        await session.execute(delete(JournalEntry))
        await session.execute(delete(ChartOfAccount))
        await session.execute(delete(Member))
        await session.commit()


async def _cleanup_approvals(engine: AsyncEngine) -> None:
    async with _factory(engine)() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantApprovalAction))
        await session.execute(delete(TenantApprovalRequest))
        await session.commit()


async def _setup_gl_accounts(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a cash account (asset) and a share capital account (equity).
    Returns (cash_account_id, share_capital_account_id).
    """
    session = await _new_session(engine)
    try:
        svc = LedgerService(session)
        actor = uuid.uuid4()
        cash = await svc.create_account(
            code="1010", name="Cash in Hand", account_type="asset", created_by=actor
        )
        equity = await svc.create_account(
            code="3010", name="Share Capital", account_type="equity", created_by=actor
        )
        await session.commit()
        return cash.id, equity.id
    finally:
        await session.close()


async def _setup_product(
    engine: AsyncEngine, share_capital_account_id: uuid.UUID
) -> uuid.UUID:
    """Create a share product and return its ID."""
    session = await _new_session(engine)
    try:
        svc = ShareService(session)
        product = await svc.create_product(
            name="Ordinary Shares",
            par_value=Decimal("1000.00"),
            share_capital_account_id=share_capital_account_id,
        )
        await session.commit()
        return product.id
    finally:
        await session.close()


async def _setup_member(engine: AsyncEngine) -> uuid.UUID:
    """Create a member and return its ID."""
    session = await _new_session(engine)
    try:
        svc = MemberService(session)
        actor = uuid.uuid4()
        member = await svc.register_member(
            full_name="Alice Nakato",
            date_of_birth=date(1990, 5, 15),
            gender="female",
            created_by=actor,
        )
        await session.commit()
        return member.id
    finally:
        await session.close()


async def _setup_account(
    engine: AsyncEngine, product_id: uuid.UUID
) -> uuid.UUID:
    """Create a member and open a share account, returning the account ID."""
    # First create a member
    session = await _new_session(engine)
    try:
        member_svc = MemberService(session)
        actor = uuid.uuid4()
        member = await member_svc.register_member(
            full_name="Test Member",
            date_of_birth=date(1990, 5, 15),
            gender="female",
            created_by=actor,
        )
        await session.commit()
        member_id = member.id
    finally:
        await session.close()

    # Then open account
    session = await _new_session(engine)
    try:
        svc = ShareService(session)
        account = await svc.open_account(
            member_id=member_id,
            share_product_id=product_id,
        )
        await session.commit()
        return account.id
    finally:
        await session.close()


# ── Share Products ────────────────────────────────────────────────────────────


async def test_create_product_returns_active_product(test_engine):
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        product = await svc.create_product(
            name="Ordinary Shares",
            par_value=Decimal("1000.00"),
            share_capital_account_id=equity_id,
            minimum_shares=1,
        )
        await session.commit()

        assert product.id is not None
        assert product.name == "Ordinary Shares"
        assert product.par_value == Decimal("1000.00")
        assert product.is_active is True
        assert product.maximum_shares is None
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_create_product_invalid_par_value_raises(test_engine):
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        with pytest.raises(ValueError, match="par_value must be positive"):
            await svc.create_product(
                name="Bad",
                par_value=Decimal("0"),
                share_capital_account_id=equity_id,
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


# ── Member Share Accounts ─────────────────────────────────────────────────────


async def test_open_account_returns_account(test_engine):
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, equity_id)

    session = await _new_session(test_engine)
    try:
        member_svc = MemberService(session)
        actor = uuid.uuid4()
        member = await member_svc.register_member(
            full_name="Alice Nakato",
            date_of_birth=date(1990, 5, 15),
            gender="female",
            created_by=actor,
        )
        await session.commit()
        member_id = member.id
    finally:
        await session.close()

    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        account = await svc.open_account(
            member_id=member_id,
            share_product_id=product_id,
        )
        await session.commit()

        assert account.id is not None
        assert account.member_id == member_id
        assert account.share_product_id == product_id
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_open_account_duplicate_raises(test_engine):
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, equity_id)

    # Create a member
    session = await _new_session(test_engine)
    try:
        member_svc = MemberService(session)
        actor = uuid.uuid4()
        member = await member_svc.register_member(
            full_name="Alice Nakato",
            date_of_birth=date(1990, 5, 15),
            gender="female",
            created_by=actor,
        )
        await session.commit()
        member_id = member.id
    finally:
        await session.close()

    # Open first account with a specific member_id
    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        _ = await svc.open_account(
            member_id=member_id, share_product_id=product_id
        )
        await session.commit()
    finally:
        await session.close()

    # Try to open second account with the same member_id — should raise
    session2 = await _new_session(test_engine)
    try:
        svc2 = ShareService(session2)
        with pytest.raises(ValueError, match="already exists"):
            await svc2.open_account(
                member_id=member_id, share_product_id=product_id
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


# ── Balance ───────────────────────────────────────────────────────────────────


async def test_get_balance_zero_for_new_account(test_engine):
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, equity_id)
    account_id = await _setup_account(test_engine, product_id)

    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        shares_held, total_value = await svc.get_balance(account_id)
        assert shares_held == 0
        assert total_value == Decimal("0")
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_get_account_not_found_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_account(uuid.uuid4())
    finally:
        await session.close()


# ── Share Purchase ────────────────────────────────────────────────────────────


async def test_purchase_shares_returns_transaction(test_engine):
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, equity_id)
    account_id = await _setup_account(test_engine, product_id)

    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        txn = await svc.purchase_shares(
            share_account_id=account_id,
            quantity=5,
            payment_account_id=cash_id,
            posted_by=uuid.uuid4(),
            idempotency_key="buy-shares-001",
        )
        await session.commit()

        assert txn.id is not None
        assert txn.transaction_type == "purchase"
        assert txn.quantity == 5
        assert txn.amount == Decimal("5000.00")  # 5 × 1000.00
        assert txn.journal_entry_id is not None
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_purchase_shares_updates_balance(test_engine):
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, equity_id)
    account_id = await _setup_account(test_engine, product_id)

    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        await svc.purchase_shares(
            share_account_id=account_id,
            quantity=10,
            payment_account_id=cash_id,
            posted_by=uuid.uuid4(),
            idempotency_key="buy-shares-002",
        )
        await session.commit()

        shares_held, total_value = await svc.get_balance(account_id)
        assert shares_held == 10
        assert total_value == Decimal("10000.00")  # 10 × 1000.00
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_purchase_shares_idempotency(test_engine):
    """Calling purchase_shares twice with the same key returns the same transaction."""
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, equity_id)
    account_id = await _setup_account(test_engine, product_id)

    async def _buy(idem_key: str) -> uuid.UUID:
        session = await _new_session(test_engine)
        try:
            svc = ShareService(session)
            txn = await svc.purchase_shares(
                share_account_id=account_id,
                quantity=3,
                payment_account_id=cash_id,
                posted_by=uuid.uuid4(),
                idempotency_key=idem_key,
            )
            await session.commit()
            return txn.id
        finally:
            await session.close()

    try:
        id1 = await _buy("idem-buy-003")
        id2 = await _buy("idem-buy-003")
        assert id1 == id2  # same transaction returned on retry

        # Balance should reflect only one purchase, not two
        session = await _new_session(test_engine)
        try:
            svc = ShareService(session)
            shares_held, _ = await svc.get_balance(account_id)
            assert shares_held == 3
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine)


async def test_purchase_shares_posts_balanced_gl_entry(test_engine):
    """Verify the GL entry debits cash and credits share capital."""
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, equity_id)
    account_id = await _setup_account(test_engine, product_id)

    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        await svc.purchase_shares(
            share_account_id=account_id,
            quantity=2,
            payment_account_id=cash_id,
            posted_by=uuid.uuid4(),
            idempotency_key="buy-shares-004",
        )
        await session.commit()

        # Verify GL balances: cash debited 2000, equity credited 2000
        ledger_svc = LedgerService(session)
        cash_balance = await ledger_svc.get_account_balance(cash_id)
        equity_balance = await ledger_svc.get_account_balance(equity_id)
        assert cash_balance == Decimal("2000.00")   # asset debit-normal
        assert equity_balance == Decimal("2000.00")  # equity credit-normal
    finally:
        await session.close()
        await _cleanup(test_engine)


# ── Share Redemption (Maker-Checker) ──────────────────────────────────────────


async def test_submit_redemption_insufficient_shares_raises(test_engine):
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, equity_id)
    account_id = await _setup_account(test_engine, product_id)

    # Account has 0 shares — try to redeem 5
    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        with pytest.raises(ValueError, match="Insufficient shares"):
            await svc.submit_redemption(
                share_account_id=account_id,
                quantity=5,
                payment_account_id=cash_id,
                submitted_by=uuid.uuid4(),
                idempotency_key="redeem-fail-001",
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_executor_redeems_shares_and_posts_gl(test_engine):
    """Full maker-checker flow: purchase → submit redemption → approve → verify balance + GL."""
    cash_id, equity_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, equity_id)
    account_id = await _setup_account(test_engine, product_id)
    maker_id = uuid.uuid4()
    checker_id = uuid.uuid4()

    # Purchase 10 shares first
    session = await _new_session(test_engine)
    try:
        svc = ShareService(session)
        await svc.purchase_shares(
            share_account_id=account_id,
            quantity=10,
            payment_account_id=cash_id,
            posted_by=maker_id,
            idempotency_key="buy-for-redeem-001",
        )
        await session.commit()
    finally:
        await session.close()

    # Submit redemption of 3 shares
    session2 = await _new_session(test_engine)
    try:
        svc2 = ShareService(session2)
        approval_id = await svc2.submit_redemption(
            share_account_id=account_id,
            quantity=3,
            payment_account_id=cash_id,
            submitted_by=maker_id,
            idempotency_key="redeem-001",
        )
        await session2.commit()
    finally:
        await session2.close()

    # Approve — triggers executor
    session3 = await _new_session(test_engine)
    try:
        approval_svc = ApprovalService(session3)
        await approval_svc.approve(request_id=approval_id, actor_user_id=checker_id)
        await session3.commit()
    finally:
        await session3.close()

    # Verify balance = 10 - 3 = 7 shares
    session4 = await _new_session(test_engine)
    try:
        svc4 = ShareService(session4)
        shares_held, total_value = await svc4.get_balance(account_id)
        assert shares_held == 7
        assert total_value == Decimal("7000.00")  # 7 × 1000.00

        # GL: cash net balance = 10000 purchased - 3000 redeemed = 7000 debited net
        ledger_svc = LedgerService(session4)
        cash_balance = await ledger_svc.get_account_balance(cash_id)
        equity_balance = await ledger_svc.get_account_balance(equity_id)
        assert cash_balance == Decimal("7000.00")   # 10000 debit - 3000 credit
        assert equity_balance == Decimal("7000.00")  # 10000 credit - 3000 debit
    finally:
        await session4.close()
        await _cleanup_approvals(test_engine)
        await _cleanup(test_engine)
