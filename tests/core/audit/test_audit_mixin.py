"""
Tests for AuditableMixin:
- Platform model writes to platform.audit_log
- Tenant model writes to tenant audit_log (current schema)
- actor_type=platform_user recorded when context var is set
- update records before and after state

Each test manages its own session with explicit commit + cleanup, matching the
pattern used by maker_checker tests. This avoids the asyncpg protocol-state
error that occurs when flush() is called inside a session-scoped async fixture
in pytest-asyncio ≥0.21 with a session-scoped event loop.
"""
from __future__ import annotations

import uuid

import pytest
import structlog
from sqlalchemy import UUID, Text, delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.db import Base

TEST_TENANT_SCHEMA = "tenant_test"

# ── Minimal test models ────────────────────────────────────────────────────────

class PlatformWidget(AuditableMixin, Base):
    __tablename__ = "platform_widgets"
    __table_args__ = {"schema": "platform"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)


class TenantWidget(AuditableMixin, Base):
    __tablename__ = "tenant_widgets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)


@pytest.fixture(scope="session", autouse=True)
async def create_widget_tables(test_engine: AsyncEngine) -> None:
    """Create the test-model tables used only in this test module."""
    async with test_engine.begin() as conn:
        await conn.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await conn.run_sync(Base.metadata.create_all)


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def test_platform_model_writes_to_platform_audit_log(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)

    # Write (auto-audit fires on flush inside commit)
    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        session.sync_session.info["is_platform"] = True
        widget = PlatformWidget(name="alpha")
        session.add(widget)
        await session.commit()

    # Assert
    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        rows = (
            await session.execute(
                select(PlatformAuditLog).where(PlatformAuditLog.table_name == "platform_widgets")
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].table_name == "platform_widgets"
        assert rows[0].operation == "insert"
        assert rows[0].after_state["name"] == "alpha"
        assert rows[0].before_state is None

    # Cleanup
    async with factory() as session:
        await session.execute(text("SET search_path TO platform"))
        await session.execute(delete(PlatformAuditLog))
        await session.execute(delete(PlatformWidget))
        await session.commit()


async def test_tenant_model_writes_to_tenant_audit_log(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)

    # Write
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        widget = TenantWidget(name="beta")
        session.add(widget)
        await session.commit()

    # Assert
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        rows = (await session.execute(select(TenantAuditLog))).scalars().all()
        assert len(rows) == 1
        assert rows[0].table_name == "tenant_widgets"
        assert rows[0].operation == "insert"

    # Cleanup
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantAuditLog))
        await session.execute(delete(TenantWidget))
        await session.commit()


async def test_update_records_before_and_after(test_engine: AsyncEngine) -> None:
    factory = _factory(test_engine)

    # Write: insert then update
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        widget = TenantWidget(name="original")
        session.add(widget)
        await session.flush()

        widget.name = "updated"
        await session.commit()

    # Assert
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        rows = (await session.execute(select(TenantAuditLog))).scalars().all()
        update_rows = [r for r in rows if r.operation == "update"]
        assert len(update_rows) == 1
        assert update_rows[0].before_state["name"] == "original"
        assert update_rows[0].after_state["name"] == "updated"

    # Cleanup
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantAuditLog))
        await session.execute(delete(TenantWidget))
        await session.commit()


async def test_cross_context_actor_type_recorded(test_engine: AsyncEngine) -> None:
    """A platform_user acting via a tenant session writes to tenant log with correct actor_type."""
    factory = _factory(test_engine)
    actor_id = uuid.uuid4()

    # Write with actor context
    structlog.contextvars.bind_contextvars(
        actor_type="platform_user",
        actor_id=str(actor_id),
        actor_label="admin@platform.com",
    )
    try:
        async with factory() as session:
            await session.execute(
                text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
            )
            widget = TenantWidget(name="cross-context")
            session.add(widget)
            await session.commit()
    finally:
        structlog.contextvars.clear_contextvars()

    # Assert
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        rows = (await session.execute(select(TenantAuditLog))).scalars().all()
        insert_rows = [r for r in rows if r.operation == "insert"]
        last = insert_rows[-1]
        assert last.actor_type == "platform_user"
        assert last.actor_label == "admin@platform.com"
        assert last.actor_id == actor_id

    # Cleanup
    async with factory() as session:
        await session.execute(
            text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        await session.execute(delete(TenantAuditLog))
        await session.execute(delete(TenantWidget))
        await session.commit()
