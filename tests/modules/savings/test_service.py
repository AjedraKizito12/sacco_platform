"""Integration tests for SavingsService.

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

import app.modules.savings.executors  # noqa: F401 — registers savings executor
from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.ledger.service import LedgerService
from app.modules.members.models import Member
from app.modules.members.service import MemberService
from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction
from app.modules.savings.service import SavingsService

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
        await session.execute(delete(SavingsTransaction))
        await session.execute(delete(SavingsAccount))
        await session.execute(delete(SavingsProduct))
        await session.execute(delete(JournalLine))
        await session.execute(delete(JournalEntry))
        await session.execute(delete(ChartOfAccount))
        await session.execute(delete(Member))
        await session.commit()


async def _setup_gl_accounts(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a cash account (asset) and a savings liability account.
    Returns (cash_account_id, liability_account_id).
    """
    session = await _new_session(engine)
    try:
        svc = LedgerService(session)
        actor = uuid.uuid4()
        cash = await svc.create_account(
            code="1020", name="Cash in Hand", account_type="asset", created_by=actor
        )
        liability = await svc.create_account(
            code="2010", name="Member Savings", account_type="liability", created_by=actor
        )
        await session.commit()
        return cash.id, liability.id
    finally:
        await session.close()


async def _setup_product(engine: AsyncEngine, liability_account_id: uuid.UUID) -> uuid.UUID:
    """Create a savings product and return its ID."""
    session = await _new_session(engine)
    try:
        svc = SavingsService(session)
        product = await svc.create_product(
            name="Regular Savings",
            interest_rate=Decimal("5.00"),
            liability_account_id=liability_account_id,
            minimum_balance=Decimal("500.00"),
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
        member = await svc.register_member(
            full_name="Alice Nakato",
            date_of_birth=date(1990, 5, 15),
            gender="female",
            created_by=uuid.uuid4(),
        )
        await session.commit()
        return member.id
    finally:
        await session.close()


async def _setup_account(
    engine: AsyncEngine, product_id: uuid.UUID
) -> uuid.UUID:
    """Create a member and open a savings account, returning the account ID."""
    member_id = await _setup_member(engine)
    session = await _new_session(engine)
    try:
        svc = SavingsService(session)
        account = await svc.open_account(
            member_id=member_id,
            savings_product_id=product_id,
        )
        await session.commit()
        return account.id
    finally:
        await session.close()


# ── Savings Products ──────────────────────────────────────────────────────────


async def test_create_product_returns_active_product(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        product = await svc.create_product(
            name="Regular Savings",
            interest_rate=Decimal("5.00"),
            liability_account_id=liability_id,
            minimum_balance=Decimal("500.00"),
        )
        await session.commit()

        assert product.id is not None
        assert product.name == "Regular Savings"
        assert product.interest_rate == Decimal("5.00")
        assert product.minimum_balance == Decimal("500.00")
        assert product.is_active is True
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_create_product_negative_interest_rate_raises(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        with pytest.raises(ValueError, match="interest_rate"):
            await svc.create_product(
                name="Bad",
                interest_rate=Decimal("-1"),
                liability_account_id=liability_id,
            )
    finally:
        await session.close()
        await _cleanup(test_engine)


# ── Savings Accounts ──────────────────────────────────────────────────────────


async def test_open_account_returns_account_with_snapshots(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    member_id = await _setup_member(test_engine)

    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        account = await svc.open_account(
            member_id=member_id,
            savings_product_id=product_id,
        )
        await session.commit()

        assert account.id is not None
        assert account.member_id == member_id
        assert account.savings_product_id == product_id
        # Product terms are snapshotted
        assert account.product_name == "Regular Savings"
        assert account.interest_rate == Decimal("5.00")
        assert account.minimum_balance == Decimal("500.00")
        assert account.liability_account_id == liability_id
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_open_account_duplicate_raises(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    member_id = await _setup_member(test_engine)

    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        _ = await svc.open_account(member_id=member_id, savings_product_id=product_id)
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = SavingsService(session2)
        with pytest.raises(ValueError, match="already exists"):
            await svc2.open_account(member_id=member_id, savings_product_id=product_id)
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_open_account_inactive_product_raises(test_engine):
    _, liability_id = await _setup_gl_accounts(test_engine)
    product_id = await _setup_product(test_engine, liability_id)
    member_id = await _setup_member(test_engine)

    # Deactivate the product
    session = await _new_session(test_engine)
    try:
        from app.modules.savings.models import SavingsProduct as SP
        product = await session.get(SP, product_id)
        product.is_active = False
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = SavingsService(session2)
        with pytest.raises(ValueError, match="not found or inactive"):
            await svc2.open_account(member_id=member_id, savings_product_id=product_id)
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_get_account_not_found_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = SavingsService(session)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_account(uuid.uuid4())
    finally:
        await session.close()
