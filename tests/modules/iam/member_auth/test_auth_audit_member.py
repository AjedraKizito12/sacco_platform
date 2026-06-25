"""Integration test: write_member_auth_event records actor_type='member'."""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.iam.auth_audit import write_member_auth_event

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


async def test_write_member_auth_event_records_member_actor(test_engine: AsyncEngine) -> None:
    member_id = uuid.uuid4()
    session = await _new_session(test_engine)
    try:
        await write_member_auth_event(
            db=session,
            operation="login_success",
            actor_id=member_id,
            actor_label="jane@example.com",
            after_state={"session_id": "s1"},
        )
        await session.commit()

        row = (
            await session.execute(
                text(
                    "SELECT actor_type, table_name FROM audit_log "
                    "WHERE actor_id = :aid ORDER BY occurred_at DESC LIMIT 1"
                ),
                {"aid": str(member_id)},
            )
        ).first()
        assert row is not None
        assert row.actor_type == "member"
        assert row.table_name == "member_sessions"
    finally:
        await session.execute(
            text("DELETE FROM audit_log WHERE actor_id = :aid"), {"aid": str(member_id)}
        )
        await session.commit()
        await session.close()
