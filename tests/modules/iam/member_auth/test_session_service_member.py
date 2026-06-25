"""Integration tests: SessionService against MemberSession.

Uses async_sessionmaker + commit + cleanup (not the rolled-back fixture) so
flush() works under the session-scoped event loop, per the IAM test convention.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.iam.sessions.models import MemberSession
from app.modules.iam.sessions.service import SessionService

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _new_session(engine: AsyncEngine) -> AsyncSession:
    from sqlalchemy import event as sa_event

    session = _factory(engine)()

    @sa_event.listens_for(session.sync_session, "after_begin")
    def _reapply_search_path(sess, transaction, connection):  # type: ignore[misc]  # noqa: ANN001, ANN202
        connection.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))

    await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
    return session


async def _cleanup(engine: AsyncEngine, member_id: uuid.UUID) -> None:
    async with _factory(engine)() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(
            text("DELETE FROM member_sessions WHERE member_id = :mid"),
            {"mid": str(member_id)},
        )
        await session.commit()


async def test_create_member_session_sets_member_id(test_engine: AsyncEngine) -> None:
    member_id = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        svc = SessionService(db=session, model_cls=MemberSession, redis=None)
        row = await svc.create(
            user_id=member_id,
            jti=str(uuid.uuid4()),
            user_agent="pytest",
            ip_address="127.0.0.1",
            refresh_ttl_seconds=3600,
        )
        await session.commit()
        assert isinstance(row, MemberSession)
        assert row.member_id == member_id
    finally:
        await session.close()
        await _cleanup(test_engine, member_id)


async def test_revoke_all_for_member(test_engine: AsyncEngine) -> None:
    member_id = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        svc = SessionService(db=session, model_cls=MemberSession, redis=None)
        for _ in range(2):
            await svc.create(
                user_id=member_id,
                jti=str(uuid.uuid4()),
                user_agent=None,
                ip_address=None,
                refresh_ttl_seconds=3600,
            )
        await session.commit()
        revoked = await svc.revoke_all_for_user(member_id)
        await session.commit()
        assert revoked == 2
    finally:
        await session.close()
        await _cleanup(test_engine, member_id)
