"""Integration tests for write_platform_auth_event and write_tenant_auth_event.

Each test commits to the real DB then queries and cleans up. This follows the
pattern in tests/core/audit/test_audit_service.py.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.audit.models import PlatformAuditLog, TenantAuditLog

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine) -> async_sessionmaker:  # type: ignore[type-arg]
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_write_platform_auth_event_writes_row(test_engine: AsyncEngine) -> None:
    from app.modules.iam.auth_audit import write_platform_auth_event

    factory = _factory(test_engine)
    user_id = uuid.uuid4()

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await write_platform_auth_event(
            db=session,
            operation="login_success",
            actor_id=user_id,
            actor_label="user@example.com",
            after_state={"session_id": str(uuid.uuid4())},
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        rows = (await session.execute(select(PlatformAuditLog))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.operation == "login_success"
        assert row.actor_id == user_id
        assert row.actor_type == "platform_user"
        assert row.actor_label == "user@example.com"
        assert row.table_name == "platform_sessions"

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await session.execute(delete(PlatformAuditLog))
        await session.commit()


@pytest.mark.anyio
async def test_write_platform_auth_event_anonymous_uses_nil_uuid(test_engine: AsyncEngine) -> None:
    from app.modules.iam.auth_audit import write_platform_auth_event

    factory = _factory(test_engine)

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await write_platform_auth_event(
            db=session,
            operation="login_failed",
            actor_id=None,
            actor_label=None,
            after_state={"email": "unknown@example.com", "reason": "user_not_found"},
        )
        await session.commit()

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        rows = (await session.execute(select(PlatformAuditLog))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.actor_type == "anonymous"
        assert row.actor_id is None
        assert row.record_id == uuid.UUID(int=0)

    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await session.execute(delete(PlatformAuditLog))
        await session.commit()


@pytest.mark.anyio
async def test_write_tenant_auth_event_writes_row(test_engine: AsyncEngine) -> None:
    from app.modules.iam.auth_audit import write_tenant_auth_event

    factory = _factory(test_engine)
    user_id = uuid.uuid4()

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await write_tenant_auth_event(
            db=session,
            operation="login_success",
            actor_id=user_id,
            actor_label="member@sacco.org",
            tenant_slug="test-sacco",
            after_state={"session_id": str(uuid.uuid4())},
        )
        await session.commit()

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        rows = (await session.execute(select(TenantAuditLog))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.operation == "login_success"
        assert row.actor_id == user_id
        assert row.actor_type == "tenant_user"
        assert row.table_name == "tenant_sessions"
        assert row.after_state["tenant"] == "test-sacco"

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantAuditLog))
        await session.commit()


@pytest.mark.anyio
async def test_write_tenant_auth_event_user_table_for_reset(test_engine: AsyncEngine) -> None:
    from app.modules.iam.auth_audit import write_tenant_auth_event

    factory = _factory(test_engine)
    user_id = uuid.uuid4()

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await write_tenant_auth_event(
            db=session,
            operation="password_reset_confirmed",
            actor_id=user_id,
            actor_label="member@sacco.org",
            tenant_slug="test-sacco",
            table_name="tenant_users",
        )
        await session.commit()

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        rows = (await session.execute(select(TenantAuditLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].table_name == "tenant_users"
        assert rows[0].operation == "password_reset_confirmed"

    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantAuditLog))
        await session.commit()
