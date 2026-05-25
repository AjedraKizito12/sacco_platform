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

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.ledger.service import LedgerService
from app.modules.maker_checker.models.tenant import TenantApprovalAction, TenantApprovalRequest
from app.modules.members.models import Member
from app.modules.members.service import MemberService
from app.modules.shares.models import MemberShareAccount, ShareProduct, ShareTransaction
from app.modules.shares.service import ShareService

# import app.modules.shares.executors  # noqa: F401 — registers shares executor (added in Task 6)

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
    engine: AsyncEngine, product_id: uuid.UUID, member_id: uuid.UUID
) -> uuid.UUID:
    """Open a member share account and return its ID."""
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
    member_id = await _setup_member(test_engine)

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
    member_id = await _setup_member(test_engine)

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
    member_id = await _setup_member(test_engine)
    account_id = await _setup_account(test_engine, product_id, member_id)

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
