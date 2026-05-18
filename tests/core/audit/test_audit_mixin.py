"""
Tests for AuditableMixin:
- Platform model writes to platform.audit_log
- Tenant model writes to tenant audit_log (current schema)
- actor_type=platform_user recorded when context var is set
- update records before and after state
"""
from __future__ import annotations

import uuid

import pytest
import structlog
from sqlalchemy import UUID, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.db import Base

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
async def create_widget_tables(test_engine):
    """Create the test-model tables used only in this test module."""
    from sqlalchemy import text
    async with test_engine.begin() as conn:
        await conn.execute(text("SET search_path TO tenant_test, platform"))
        await conn.run_sync(Base.metadata.create_all)


async def test_platform_model_writes_to_platform_audit_log(platform_session):
    widget = PlatformWidget(name="alpha")
    platform_session.add(widget)
    await platform_session.flush()

    rows = (await platform_session.execute(select(PlatformAuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].table_name == "platform_widgets"
    assert rows[0].operation == "insert"
    assert rows[0].after_state["name"] == "alpha"
    assert rows[0].before_state is None


async def test_tenant_model_writes_to_tenant_audit_log(tenant_session):
    widget = TenantWidget(name="beta")
    tenant_session.add(widget)
    await tenant_session.flush()

    rows = (await tenant_session.execute(select(TenantAuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].table_name == "tenant_widgets"
    assert rows[0].operation == "insert"


async def test_update_records_before_and_after(tenant_session):
    widget = TenantWidget(name="original")
    tenant_session.add(widget)
    await tenant_session.flush()

    widget.name = "updated"
    await tenant_session.flush()

    rows = (await tenant_session.execute(select(TenantAuditLog))).scalars().all()
    update_rows = [r for r in rows if r.operation == "update"]
    assert len(update_rows) == 1
    assert update_rows[0].before_state["name"] == "original"
    assert update_rows[0].after_state["name"] == "updated"


async def test_cross_context_actor_type_recorded(tenant_session):
    """A platform_user acting via a tenant session writes to tenant log with correct actor_type."""
    actor_id = uuid.uuid4()
    structlog.contextvars.bind_contextvars(
        actor_type="platform_user",
        actor_id=str(actor_id),
        actor_label="admin@platform.com",
    )
    try:
        widget = TenantWidget(name="cross-context")
        tenant_session.add(widget)
        await tenant_session.flush()
    finally:
        structlog.contextvars.clear_contextvars()

    rows = (await tenant_session.execute(select(TenantAuditLog))).scalars().all()
    insert_rows = [r for r in rows if r.operation == "insert"]
    last = insert_rows[-1]
    assert last.actor_type == "platform_user"
    assert last.actor_label == "admin@platform.com"
    assert last.actor_id == actor_id
