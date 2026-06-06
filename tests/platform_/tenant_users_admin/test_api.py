"""Integration tests for /platform/tenants/{tenant_id}/users.

Uses stub auth + dependency overrides to bind the test schema as the
tenant schema. The shadow-user filter is exercised by seeding a shadow
and verifying it does not appear in list / detail.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session, get_session_for_tenant_schema
from app.main import app, lifespan
from app.modules.iam.reset_tokens import verify_reset_token
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


def _make_tenant_schema_override(engine: AsyncEngine, schema: str):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override(
        tenant_id: uuid.UUID,
    ) -> AsyncGenerator[AsyncSession, None]:
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


async def _create_superuser(
    factory: async_sessionmaker[AsyncSession],
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"super-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Super",
            is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _create_tenant_record(
    factory: async_sessionmaker[AsyncSession], schema: str,
) -> Tenant:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=schema,
            name="T",
            is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(t)
    return t


async def _seed_existing_user(
    factory: async_sessionmaker[AsyncSession],
    schema: str,
    *,
    email_suffix: str = "",
    impersonation_id: uuid.UUID | None = None,
) -> TenantUser:
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {schema}, platform"))
        u = TenantUser(
            email=f"u{email_suffix}-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Existing",
            is_active=True, is_admin=False,
            impersonation_id=impersonation_id,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO tenant_test, platform"))
        await s.execute(text("DELETE FROM tenant_users"))
        await s.execute(text("DELETE FROM audit_log"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_platform_session] = (
        _make_platform_session_override(test_engine)
    )
    app.dependency_overrides[get_session_for_tenant_schema] = (
        _make_tenant_schema_override(test_engine, "tenant_test")
    )
    try:
        async with lifespan(app), AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c
    except Exception:  # noqa: BLE001, S110
        # Redis-pool teardown can raise when the asyncio transport was created
        # in a sibling loop. Tests that hit Redis (create / password-reset)
        # have already passed by this point. Swallow so pytest doesn't report
        # a teardown error.
        pass
    finally:
        app.dependency_overrides.pop(get_platform_session, None)
        app.dependency_overrides.pop(get_session_for_tenant_schema, None)


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


# ── list ─────────────────────────────────────────────────────────────────────


async def test_list_returns_real_users_only(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    await _seed_existing_user(factory, "tenant_test")
    await _seed_existing_user(
        factory, "tenant_test", email_suffix="-imp",
        impersonation_id=uuid.uuid4(),
    )
    try:
        r = await client.get(
            f"/platform/tenants/{tenant.id}/users",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        users = r.json()
        # Only the non-shadow user appears
        assert len(users) == 1
        assert users[0]["impersonation_id"] is None
    finally:
        await _cleanup(factory)


# ── create ───────────────────────────────────────────────────────────────────


async def test_create_returns_user_and_reset_token(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/users",
            json={
                "email": f"new-{uuid.uuid4().hex[:6]}@test.example",
                "full_name": "New User",
                "is_admin": False,
            },
            headers=_hdr(actor.id),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["user"]["is_active"] is True
        assert body["user"]["is_admin"] is False
        token = body["password_reset_token"]
        assert token
        # Verify the token is a valid HMAC reset token
        from app.core.config import get_settings

        payload = verify_reset_token(token, get_settings().app_secret_key)
        assert payload["sub"] == body["user"]["id"]
        # TTL is 24h
        assert body["password_reset_expires_in"] == 86400
    finally:
        await _cleanup(factory)


async def test_create_rejects_duplicate_email(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    existing = await _seed_existing_user(factory, "tenant_test")
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/users",
            json={
                "email": existing.email,
                "full_name": "Dup",
                "is_admin": False,
            },
            headers=_hdr(actor.id),
        )
        assert r.status_code == 409, r.text
    finally:
        await _cleanup(factory)


# ── get ──────────────────────────────────────────────────────────────────────


async def test_get_returns_real_user(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    user = await _seed_existing_user(factory, "tenant_test")
    try:
        r = await client.get(
            f"/platform/tenants/{tenant.id}/users/{user.id}",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        assert r.json()["id"] == str(user.id)
    finally:
        await _cleanup(factory)


async def test_get_404_for_shadow_user(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    shadow = await _seed_existing_user(
        factory, "tenant_test", impersonation_id=uuid.uuid4(),
    )
    try:
        r = await client.get(
            f"/platform/tenants/{tenant.id}/users/{shadow.id}",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 404, r.text
    finally:
        await _cleanup(factory)


# ── patch ────────────────────────────────────────────────────────────────────


async def test_patch_updates_fields(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    user = await _seed_existing_user(factory, "tenant_test")
    try:
        r = await client.patch(
            f"/platform/tenants/{tenant.id}/users/{user.id}",
            json={"is_active": False, "is_admin": True, "full_name": "Updated"},
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_active"] is False
        assert body["is_admin"] is True
        assert body["full_name"] == "Updated"
    finally:
        await _cleanup(factory)


async def test_patch_404_for_shadow(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    shadow = await _seed_existing_user(
        factory, "tenant_test", impersonation_id=uuid.uuid4(),
    )
    try:
        r = await client.patch(
            f"/platform/tenants/{tenant.id}/users/{shadow.id}",
            json={"is_active": False},
            headers=_hdr(actor.id),
        )
        assert r.status_code == 404, r.text
    finally:
        await _cleanup(factory)


# ── password-reset ───────────────────────────────────────────────────────────


async def test_password_reset_returns_token(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    user = await _seed_existing_user(factory, "tenant_test")
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/users/{user.id}/password-reset",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user_id"] == str(user.id)
        token = body["password_reset_token"]
        from app.core.config import get_settings

        payload = verify_reset_token(token, get_settings().app_secret_key)
        assert payload["sub"] == str(user.id)
    finally:
        await _cleanup(factory)


async def test_password_reset_404_for_shadow(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant_record(factory, "tenant_test")
    shadow = await _seed_existing_user(
        factory, "tenant_test", impersonation_id=uuid.uuid4(),
    )
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/users/{shadow.id}/password-reset",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 404, r.text
    finally:
        await _cleanup(factory)
