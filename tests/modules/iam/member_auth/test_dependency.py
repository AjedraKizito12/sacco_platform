"""Tests for the member stub dependency (no crypto path)."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.iam.dependencies import get_current_member_stub
from app.modules.members.models import Member

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
    from sqlalchemy import event as sa_event

    session = _factory(engine)()

    @sa_event.listens_for(session.sync_session, "after_begin")
    def _reapply(sess, transaction, connection):  # type: ignore[misc]  # noqa: ANN001, ANN202
        connection.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))

    await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
    return session


async def _seed(engine: AsyncEngine, *, status: str, portal_enabled: bool) -> uuid.UUID:
    session = await _new_session(engine)
    try:
        m = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}",
            full_name="Dep Test",
            date_of_birth=date(1990, 1, 1),
            gender="male",
            status=status,
            email=f"dep-{uuid.uuid4().hex[:6]}@example.com",
            portal_enabled=portal_enabled,
            hashed_password="x",
        )
        session.add(m)
        await session.commit()
        return m.id
    finally:
        await session.close()


async def _cleanup(engine: AsyncEngine, member_id: uuid.UUID) -> None:
    session = await _new_session(engine)
    try:
        await session.execute(text("DELETE FROM members WHERE id = :mid"), {"mid": str(member_id)})
        await session.commit()
    finally:
        await session.close()


async def test_stub_resolves_active_enabled_member(test_engine: AsyncEngine) -> None:
    member_id = await _seed(test_engine, status="active", portal_enabled=True)
    try:
        session = await _new_session(test_engine)
        try:
            out = await get_current_member_stub(
                x_member_actor_id=str(member_id), session=session
            )
            assert out.id == member_id
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine, member_id)


async def test_stub_rejects_suspended_member(test_engine: AsyncEngine) -> None:
    member_id = await _seed(test_engine, status="suspended", portal_enabled=True)
    try:
        session = await _new_session(test_engine)
        try:
            with pytest.raises(HTTPException) as exc:
                await get_current_member_stub(x_member_actor_id=str(member_id), session=session)
            assert exc.value.status_code == 403
        finally:
            await session.close()
    finally:
        await _cleanup(test_engine, member_id)
