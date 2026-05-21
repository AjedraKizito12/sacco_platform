"""
Integration tests for PlatformAuditService and TenantAuditService.

Each test manages its own session with explicit commit + cleanup, matching the
pattern used by maker_checker tests. This avoids the asyncpg protocol-state
error that occurs when flush() is called inside a session-scoped async fixture
in pytest-asyncio ≥0.21 with a session-scoped event loop.
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.audit.service import PlatformAuditService, TenantAuditService

TEST_TENANT_SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_platform_audit_service_writes_row(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    record_id = uuid.uuid4()

    # Write
    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        session.sync_session.info["is_platform"] = True
        svc = PlatformAuditService(session)
        await svc.record(
            table_name="tenants",
            record_id=record_id,
            operation="update",
            actor_type="platform_user",
            before_state={"status": "active"},
            after_state={"status": "suspended"},
        )
        await session.commit()

    # Assert
    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        rows = (await session.execute(select(PlatformAuditLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].record_id == record_id
        assert rows[0].before_state == {"status": "active"}
        assert rows[0].after_state == {"status": "suspended"}
        assert rows[0].operation == "update"

    # Cleanup
    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await session.execute(delete(PlatformAuditLog))
        await session.commit()


async def test_tenant_audit_service_writes_row(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)
    record_id = uuid.uuid4()

    # Write
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        svc = TenantAuditService(session)
        await svc.record(
            table_name="loans",
            record_id=record_id,
            operation="insert",
            actor_type="tenant_user",
            after_state={"amount": "500000"},
        )
        await session.commit()

    # Assert
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        rows = (await session.execute(select(TenantAuditLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].operation == "insert"
        assert rows[0].before_state is None

    # Cleanup
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantAuditLog))
        await session.commit()


async def test_audit_service_is_append_only() -> None:
    """Service has no update or delete methods — append-only contract."""
    svc = TenantAuditService(None)  # type: ignore[arg-type]
    assert not hasattr(svc, "update")
    assert not hasattr(svc, "delete")
    assert not hasattr(svc, "remove")
