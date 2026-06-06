"""Both tenant deps (stub + JWT) bind impersonation_id to structlog
contextvars when the resolved TenantUser has a non-null impersonation_id.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.iam.dependencies import get_current_tenant_user_stub
from app.modules.iam.tenant_users.models import TenantUser


async def _seed_shadow(
    factory: async_sessionmaker[AsyncSession],
    impersonation_id: uuid.UUID,
) -> uuid.UUID:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        u = TenantUser(
            email=f"imp.{impersonation_id.hex[:12]}@platform.local",
            full_name="Shadow",
            is_active=True,
            is_admin=True,
            impersonation_id=impersonation_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u.id


async def test_stub_dep_binds_impersonation_id(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    imp_id = uuid.uuid4()
    user_id = await _seed_shadow(factory, imp_id)
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            await get_current_tenant_user_stub(
                x_tenant_actor_id=str(user_id), session=s
            )
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("impersonation_id") == str(imp_id)
    finally:
        structlog.contextvars.clear_contextvars()
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            await s.execute(text("DELETE FROM tenant_users"))
            await s.execute(text("DELETE FROM audit_log"))


async def test_stub_dep_does_not_bind_for_real_user(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        u = TenantUser(
            email=f"u-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Real", is_active=True, is_admin=False,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    user_id = u.id
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            await get_current_tenant_user_stub(
                x_tenant_actor_id=str(user_id), session=s
            )
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("impersonation_id") is None
    finally:
        structlog.contextvars.clear_contextvars()
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            await s.execute(text("DELETE FROM tenant_users"))
            await s.execute(text("DELETE FROM audit_log"))
