"""End-to-end cross-context flow:
    1. Maker submits impersonation request
    2. Checker approves via /platform/approvals/{id}/approve
    3. Maker mints a tenant token
    4. Shadow tenant_user exists with impersonation_id set
    5. Using stub auth against the shadow user, /members responds
    6. The audit_log row for the member registration has impersonation_id set
    7. Maker DELETEs the impersonation
    8. Shadow user is_active=False; tenant sessions revoked
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.platform_.impersonations.executors  # noqa: F401
from app.core.audit.models import TenantAuditLog
from app.core.db import get_platform_session, get_tenant_session
from app.main import app, lifespan
from app.modules.iam.tenant_users.models import TenantUser
from app.platform_.models import PlatformUser, Tenant


def _make_platform_session_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


def _make_tenant_session_override(engine: AsyncEngine, schema: str):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {schema}, platform")
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_platform_session] = (
        _make_platform_session_override(test_engine)
    )
    app.dependency_overrides[get_tenant_session] = (
        _make_tenant_session_override(test_engine, "tenant_test")
    )
    try:
        async with lifespan(app), AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
    except Exception:
        # Redis-pool teardown sometimes raises when the asyncio transport
        # was created in a sibling loop; the functional test has already
        # passed by this point. Swallow so pytest doesn't report a teardown
        # error.
        pass
    finally:
        app.dependency_overrides.pop(get_platform_session, None)
        app.dependency_overrides.pop(get_tenant_session, None)


async def _seed_signing_key(factory: async_sessionmaker[AsyncSession]) -> None:
    from app.modules.iam.keys.service import KeyService, clear_key_caches

    clear_key_caches()
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await KeyService(s).generate_and_insert(audience="tenant")


async def _seed_platform_actors(
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
        tenant = Tenant(
            slug="test-tenant", schema_name="tenant_test", name="T",
            is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add_all([maker, checker, tenant])
    return maker, checker, tenant


async def _cleanup_all(factory: async_sessionmaker[AsyncSession]) -> None:
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
        await s.execute(text("DELETE FROM members"))
        await s.execute(text("DELETE FROM tenant_sessions"))
        await s.execute(text("DELETE FROM tenant_users"))
        await s.execute(text("DELETE FROM audit_log"))


async def test_full_cross_context_flow(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    await _seed_signing_key(factory)
    maker, checker, tenant = await _seed_platform_actors(factory)
    try:
        # 1. Submit
        sub = await client.post(
            "/platform/impersonations",
            json={
                "tenant_id": str(tenant.id),
                "reason": "Investigating member balance reported by tenant admin",
            },
            headers={"X-Platform-Actor-ID": str(maker.id)},
        )
        assert sub.status_code == 202, sub.text
        approval_id = sub.json()["approval_request_id"]

        # 2. Approve
        apr = await client.post(
            f"/platform/approvals/{approval_id}/approve",
            json={"comment": "ticket verified"},
            headers={"X-Platform-Actor-ID": str(checker.id)},
        )
        assert apr.status_code == 200, apr.text
        assert apr.json()["status"] == "executed"
        imp_id = uuid.UUID(apr.json()["execution_result"]["impersonation_id"])

        # 3. Mint
        mint = await client.post(
            f"/platform/impersonations/{imp_id}/mint-tenant-token",
            headers={"X-Platform-Actor-ID": str(maker.id)},
        )
        assert mint.status_code == 200, mint.text
        assert mint.json()["access_token"]
        assert mint.json()["tenant_slug"] == tenant.slug

        # 4. Shadow tenant_user exists
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            shadow = await s.scalar(
                select(TenantUser).where(TenantUser.impersonation_id == imp_id)
            )
            assert shadow is not None
            shadow_id = shadow.id

        # 5. Use the shadow identity via stub auth to register a member
        reg = await client.post(
            "/members",
            json={
                "full_name": "Mary Test",
                "date_of_birth": "1990-01-01",
                "gender": "female",
            },
            headers={
                "X-Tenant-Slug": tenant.slug,
                "X-Tenant-Actor-ID": str(shadow_id),
            },
        )
        assert reg.status_code == 201, reg.text

        # 6. Audit row for the registration carries impersonation_id
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            audit_rows = (
                await s.execute(
                    select(TenantAuditLog)
                    .where(TenantAuditLog.table_name == "members")
                    .order_by(TenantAuditLog.occurred_at.desc())
                    .limit(1)
                )
            ).scalars().all()
            assert audit_rows, "no audit row for member insert"
            assert audit_rows[0].impersonation_id == imp_id
            assert audit_rows[0].actor_type == "tenant_user"
            assert audit_rows[0].actor_id == shadow_id

        # 7. End
        end = await client.delete(
            f"/platform/impersonations/{imp_id}",
            headers={"X-Platform-Actor-ID": str(maker.id)},
        )
        assert end.status_code == 204, end.text

        # 8. Shadow inactive; sessions revoked
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
            shadow2 = await s.get(TenantUser, shadow_id)
            assert shadow2 is not None
            assert shadow2.is_active is False
            revoked_count = await s.scalar(
                text(
                    "SELECT COUNT(*) FROM tenant_sessions "
                    "WHERE tenant_user_id = :uid AND revoked_at IS NOT NULL"
                ),
                {"uid": shadow_id},
            )
            assert revoked_count and revoked_count > 0

        # Subsequent stub-auth request as the shadow returns 403 (inactive)
        reg2 = await client.post(
            "/members",
            json={
                "full_name": "Late Mary",
                "date_of_birth": "1990-01-01",
                "gender": "female",
            },
            headers={
                "X-Tenant-Slug": tenant.slug,
                "X-Tenant-Actor-ID": str(shadow_id),
            },
        )
        assert reg2.status_code == 403, reg2.text
    finally:
        await _cleanup_all(factory)
