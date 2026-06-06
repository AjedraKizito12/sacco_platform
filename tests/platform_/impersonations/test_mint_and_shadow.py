"""mint_tenant_token: lazily provisions the shadow tenant_user on first call,
reuses it on subsequent calls, idempotent, gone-on-revoke/end/expire.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.platform_.impersonations.executors  # noqa: F401 — register executor
from app.modules.iam.tenant_users.models import TenantUser
from app.modules.maker_checker.service import ApprovalService
from app.platform_.impersonations.exceptions import ImpersonationGone
from app.platform_.impersonations.models import SupportImpersonation
from app.platform_.impersonations.service import ImpersonationService
from app.platform_.models import PlatformUser, Tenant


async def _seed_signing_key(factory: async_sessionmaker[AsyncSession]) -> None:
    from app.modules.iam.keys.service import KeyService, clear_key_caches

    clear_key_caches()
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await KeyService(s).generate_and_insert(audience="tenant")


async def _seed(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[PlatformUser, PlatformUser, Tenant]:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        maker = PlatformUser(
            email=f"maker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Jane Maker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        checker = PlatformUser(
            email=f"checker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Pat Checker", is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        # The test schema is tenant_test (set up by conftest)
        tenant = Tenant(
            slug="test-tenant",  # matches TEST_TENANT_SLUG in conftest
            schema_name="tenant_test",
            name="Test Tenant",
            is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add_all([maker, checker, tenant])
    return maker, checker, tenant


async def _approve_request(
    factory: async_sessionmaker[AsyncSession],
    maker_id: uuid.UUID,
    checker_id: uuid.UUID,
    tenant_id: uuid.UUID,
    reason: str = "Investigating member balance issue reported by ops",
) -> uuid.UUID:
    """Create impersonation request and approve it. Returns impersonation_id."""
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        approval = await ImpersonationService(s).request(
            platform_user_id=maker_id, tenant_id=tenant_id, reason=reason,
        )
        approval_id = approval.id

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        executed = await ApprovalService(s).approve(
            request_id=approval_id, actor_user_id=checker_id,
        )
        return uuid.UUID(executed.execution_result["impersonation_id"])  # type: ignore[index]


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.support_impersonations"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.execute(text("DELETE FROM platform.jwt_signing_keys"))
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        await s.execute(text("DELETE FROM tenant_sessions"))
        await s.execute(text("DELETE FROM tenant_users"))
        await s.execute(text("DELETE FROM audit_log"))


async def test_mint_creates_shadow_user_first_call(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_signing_key(factory)
    maker, checker, tenant = await _seed(factory)
    imp_id = await _approve_request(factory, maker.id, checker.id, tenant.id)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            result = await ImpersonationService(s).mint_tenant_token(
                impersonation_id=imp_id, user_agent="pytest", ip_address="127.0.0.1",
            )
            assert result.access_token
            assert result.refresh_token
            assert result.tenant_slug == tenant.slug
            assert result.impersonation_id == imp_id
            assert result.expires_in > 0

        # Verify shadow tenant_user exists with impersonation_id set
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            shadow = await s.scalar(
                select(TenantUser).where(TenantUser.impersonation_id == imp_id)
            )
            assert shadow is not None
            assert shadow.is_admin is True
            assert shadow.hashed_password is None
            assert shadow.is_active is True
            assert shadow.email.startswith(f"imp.{imp_id.hex[:12]}")

        # Verify the impersonation row was updated with tenant_user_id
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            row = await s.get(SupportImpersonation, imp_id)
            assert row is not None
            assert row.tenant_user_id == shadow.id
    finally:
        await _cleanup(factory)


async def test_mint_reuses_shadow_user_on_subsequent_calls(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_signing_key(factory)
    maker, checker, tenant = await _seed(factory)
    imp_id = await _approve_request(factory, maker.id, checker.id, tenant.id)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            r1 = await ImpersonationService(s).mint_tenant_token(
                impersonation_id=imp_id, user_agent="ua1", ip_address="1.1.1.1",
            )
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            r2 = await ImpersonationService(s).mint_tenant_token(
                impersonation_id=imp_id, user_agent="ua2", ip_address="2.2.2.2",
            )
        # Tokens differ (different JTIs) but slug + imp_id are stable
        assert r1.access_token != r2.access_token
        assert r1.tenant_slug == r2.tenant_slug
        assert r1.impersonation_id == r2.impersonation_id

        # Only one shadow user exists
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            rows = (
                await s.execute(
                    select(TenantUser).where(TenantUser.impersonation_id == imp_id)
                )
            ).scalars().all()
            assert len(rows) == 1
    finally:
        await _cleanup(factory)


async def test_mint_rejects_when_ended(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_signing_key(factory)
    maker, checker, tenant = await _seed(factory)
    imp_id = await _approve_request(factory, maker.id, checker.id, tenant.id)
    # Force-end the impersonation
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        await ImpersonationService(s).end(impersonation_id=imp_id, ended_by=maker.id)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            with pytest.raises(ImpersonationGone):
                await ImpersonationService(s).mint_tenant_token(
                    impersonation_id=imp_id, user_agent="x", ip_address="x",
                )
    finally:
        await _cleanup(factory)


async def test_mint_rejects_when_expired(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_signing_key(factory)
    maker, checker, tenant = await _seed(factory)
    imp_id = await _approve_request(factory, maker.id, checker.id, tenant.id)
    # Force-expire by setting expires_at in the past
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(
            text(
                "UPDATE platform.support_impersonations "
                "SET expires_at = now() - interval '1 minute' "
                "WHERE id = :id"
            ),
            {"id": imp_id},
        )
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            with pytest.raises(ImpersonationGone):
                await ImpersonationService(s).mint_tenant_token(
                    impersonation_id=imp_id, user_agent="x", ip_address="x",
                )
    finally:
        await _cleanup(factory)
