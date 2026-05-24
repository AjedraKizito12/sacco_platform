"""Integration tests for LedgerService.

Uses the async_sessionmaker + commit + cleanup pattern (not the rollback fixture)
to avoid asyncpg protocol-state errors with flush() in session-scoped event loops.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession

from app.modules.ledger.models import ChartOfAccount, JournalEntry, JournalLine
from app.modules.ledger.service import LedgerService

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
    """Return a new AsyncSession with search_path set (no transaction started).

    With NullPool each commit closes the underlying connection.  We attach an
    ``after_begin`` listener to the *sync* session so that search_path is
    re-applied at the start of every new transaction (i.e. on every new
    connection acquired after a commit).
    """
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
        await session.execute(delete(JournalLine))
        await session.execute(delete(JournalEntry))
        await session.execute(delete(ChartOfAccount))
        await session.commit()


# ── Account CRUD ──────────────────────────────────────────────────────────────


async def test_create_account_returns_active_account(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        account = await svc.create_account(
            code="1000",
            name="Cash",
            account_type="asset",
            created_by=uuid.uuid4(),
        )
        await session.commit()

        assert account.id is not None
        assert account.code == "1000"
        assert account.name == "Cash"
        assert account.account_type == "asset"
        assert account.is_active is True
        assert account.parent_id is None
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_create_account_duplicate_code_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        await svc.create_account(
            code="1001",
            name="Bank",
            account_type="asset",
            created_by=uuid.uuid4(),
        )
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = LedgerService(session2)
        with pytest.raises(ValueError, match="already exists"):
            await svc2.create_account(
                code="1001",
                name="Duplicate",
                account_type="asset",
                created_by=uuid.uuid4(),
            )
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_create_account_invalid_type_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        with pytest.raises(ValueError, match="account_type"):
            await svc.create_account(
                code="9999",
                name="Bad",
                account_type="invalid",
                created_by=uuid.uuid4(),
            )
    finally:
        await session.close()


async def test_list_accounts_returns_active_only_by_default(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        actor = uuid.uuid4()
        await svc.create_account(code="2000", name="Equity", account_type="equity", created_by=actor)
        acc = await svc.create_account(code="2001", name="Inactive", account_type="equity", created_by=actor)
        acc.is_active = False
        await session.commit()

        results = await svc.list_accounts()
        codes = [a.code for a in results]
        assert "2000" in codes
        assert "2001" not in codes
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_get_account_not_found_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_account(uuid.uuid4())
    finally:
        await session.close()
