from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.core.audit.service import PlatformAuditService, TenantAuditService


async def test_platform_audit_service_writes_row(platform_session):
    svc = PlatformAuditService(platform_session)
    record_id = uuid.uuid4()
    await svc.record(
        table_name="tenants",
        record_id=record_id,
        operation="update",
        actor_type="platform_user",
        before_state={"status": "active"},
        after_state={"status": "suspended"},
    )
    await platform_session.flush()

    rows = (await platform_session.execute(select(PlatformAuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].record_id == record_id
    assert rows[0].before_state == {"status": "active"}
    assert rows[0].after_state == {"status": "suspended"}
    assert rows[0].operation == "update"


async def test_tenant_audit_service_writes_row(tenant_session):
    svc = TenantAuditService(tenant_session)
    record_id = uuid.uuid4()
    await svc.record(
        table_name="loans",
        record_id=record_id,
        operation="insert",
        actor_type="tenant_user",
        after_state={"amount": "500000"},
    )
    await tenant_session.flush()

    rows = (await tenant_session.execute(select(TenantAuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].operation == "insert"
    assert rows[0].before_state is None


async def test_audit_service_is_append_only(tenant_session):
    """Service has no update or delete methods — append-only contract."""
    svc = TenantAuditService(tenant_session)
    assert not hasattr(svc, "update")
    assert not hasattr(svc, "delete")
    assert not hasattr(svc, "remove")
