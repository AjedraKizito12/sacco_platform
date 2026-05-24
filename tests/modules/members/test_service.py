"""Integration tests for MemberService.

Uses async_sessionmaker + commit + cleanup (not the rollback fixture)
to avoid asyncpg protocol-state errors with flush() in session-scoped event loops.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.members.models import Member
from app.modules.members.service import MemberService
from app.modules.maker_checker.models.tenant import TenantApprovalRequest, TenantApprovalAction
from app.modules.maker_checker.service import ApprovalService
# import app.modules.members.executors  # noqa: F401 — registers members executor (added in Task 5)

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
    """Return a new AsyncSession with search_path set.

    The after_begin listener re-applies search_path on every new connection
    (NullPool closes the connection after each commit).
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


def _member_kwargs(**overrides) -> dict:
    """Return minimal valid kwargs for register_member."""
    base = {
        "full_name": "Alice Nakato",
        "date_of_birth": date(1990, 5, 15),
        "gender": "female",
        "created_by": uuid.uuid4(),
    }
    base.update(overrides)
    return base


# ── Registration ──────────────────────────────────────────────────────────────


async def test_register_member_returns_pending_status(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = MemberService(session)
        member = await svc.register_member(**_member_kwargs())
        await session.commit()

        assert member.id is not None
        assert member.member_number.startswith("M-")
        assert member.status == "pending"
        assert member.joined_at is None
        assert member.full_name == "Alice Nakato"
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_register_member_generates_sequential_member_numbers(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = MemberService(session)
        m1 = await svc.register_member(**_member_kwargs(full_name="Alice", email="alice@example.com"))
        m2 = await svc.register_member(**_member_kwargs(full_name="Bob", email="bob@example.com"))
        await session.commit()

        # Both are M-NNNNN formatted; second number is higher than first.
        n1 = int(m1.member_number.split("-")[1])
        n2 = int(m2.member_number.split("-")[1])
        assert n2 > n1
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_register_member_duplicate_email_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = MemberService(session)
        await svc.register_member(**_member_kwargs(email="dup@example.com"))
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = MemberService(session2)
        with pytest.raises(ValueError, match="already exists"):
            await svc2.register_member(**_member_kwargs(full_name="Other", email="dup@example.com"))
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_register_member_duplicate_national_id_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = MemberService(session)
        await svc.register_member(**_member_kwargs(national_id_number="CM123456"))
        await session.commit()
    finally:
        await session.close()

    session2 = await _new_session(test_engine)
    try:
        svc2 = MemberService(session2)
        with pytest.raises(ValueError, match="already exists"):
            await svc2.register_member(**_member_kwargs(full_name="Other", national_id_number="CM123456"))
    finally:
        await session2.close()
        await _cleanup(test_engine)


async def test_list_members_filter_by_status(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = MemberService(session)
        actor = uuid.uuid4()
        m1 = await svc.register_member(**_member_kwargs(full_name="Pending One", created_by=actor))
        m2 = await svc.register_member(**_member_kwargs(full_name="Active One", created_by=actor))
        m2.status = "active"  # Force directly for this test (bypassing maker-checker)
        await session.commit()

        pending = await svc.list_members(status="pending")
        active = await svc.list_members(status="active")

        pending_ids = [m.id for m in pending]
        active_ids = [m.id for m in active]
        assert m1.id in pending_ids
        assert m1.id not in active_ids
        assert m2.id in active_ids
        assert m2.id not in pending_ids
    finally:
        await session.close()
        await _cleanup(test_engine)


async def test_get_member_not_found_raises(test_engine):
    session = await _new_session(test_engine)
    try:
        svc = MemberService(session)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_member(uuid.uuid4())
    finally:
        await session.close()
