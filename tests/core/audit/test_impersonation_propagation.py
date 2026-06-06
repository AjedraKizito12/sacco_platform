"""When impersonation_id is bound to structlog contextvars, AuditableMixin
writes it onto tenant.audit_log rows. PlatformAuditLog rows do NOT carry
the column and must be unaffected.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.audit.models import PlatformAuditLog, TenantAuditLog
from app.modules.iam.tenant_users.models import TenantUser
from app.platform_.models import PlatformUser


async def test_tenant_audit_row_carries_impersonation_id(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    imp_id = uuid.uuid4()
    structlog.contextvars.bind_contextvars(
        actor_type="tenant_user",
        actor_id=str(uuid.uuid4()),
        actor_label="imp.abc@platform.local",
        impersonation_id=str(imp_id),
    )
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            u = TenantUser(
                email=f"u-{uuid.uuid4().hex[:6]}@test.example",
                full_name="U", is_active=True, is_admin=False,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(u)

        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            rows = (
                await s.execute(
                    select(TenantAuditLog)
                    .where(TenantAuditLog.table_name == "tenant_users")
                    .order_by(TenantAuditLog.occurred_at.desc())
                    .limit(1)
                )
            ).scalars().all()
            assert rows, "no tenant_users audit row found"
            assert rows[0].impersonation_id == imp_id
    finally:
        structlog.contextvars.clear_contextvars()
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            await s.execute(text("DELETE FROM tenant_users"))
            await s.execute(text("DELETE FROM audit_log"))


async def test_platform_audit_row_unaffected_by_impersonation_id(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    structlog.contextvars.bind_contextvars(
        actor_type="platform_user",
        actor_id=str(uuid.uuid4()),
        impersonation_id=str(uuid.uuid4()),
    )
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            u = PlatformUser(
                email=f"p-{uuid.uuid4().hex[:6]}@test.example",
                full_name="P", is_active=True, is_superuser=False,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            )
            s.add(u)
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            rows = (
                await s.execute(
                    select(PlatformAuditLog)
                    .where(PlatformAuditLog.table_name == "platform_users")
                    .order_by(PlatformAuditLog.occurred_at.desc())
                    .limit(1)
                )
            ).scalars().all()
            assert rows, "no platform_users audit row found"
            # PlatformAuditLog has no impersonation_id column; the mixin must
            # have silently dropped the key from the insert payload.
            assert not hasattr(rows[0], "impersonation_id")
    finally:
        structlog.contextvars.clear_contextvars()
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(text("DELETE FROM platform.platform_users"))
            await s.execute(text("DELETE FROM platform.audit_log"))
