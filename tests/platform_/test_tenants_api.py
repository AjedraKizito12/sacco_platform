"""Integration tests for /platform/tenants endpoints."""
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.models import PlatformUser, Tenant
from app.platform_.tenants.api import router as tenants_router

# Register router (idempotent check).
if not any(getattr(r, "path", "").startswith("/platform/tenants") for r in app.routes):
    app.include_router(tenants_router)


# ── Session override ──────────────────────────────────────────────────────────


def _make_platform_session_override(engine: AsyncEngine) -> Any:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            yield session

    return _override


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _create_superuser(factory: async_sessionmaker[AsyncSession]) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"super-{uuid.uuid4()}@test.example",
            full_name="Super",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _create_regular_user(factory: async_sessionmaker[AsyncSession]) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"regular-{uuid.uuid4()}@test.example",
            full_name="Regular",
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _cleanup(factory: async_sessionmaker[AsyncSession], *objects: object) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        for obj in objects:
            fresh = await s.get(type(obj), obj.id)  # type: ignore[attr-defined]
            if fresh:
                await s.delete(fresh)


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_post_tenants_returns_202(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)

    with patch("app.platform_.tenants.api.provision_tenant") as mock_task:
        mock_task.delay = MagicMock()
        resp = await client.post(
            "/platform/tenants",
            json={"slug": "acme-test", "name": "Acme SACCO"},
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )

    assert resp.status_code == 202
    data = resp.json()
    assert data["tenant"]["slug"] == "acme-test"
    assert data["tenant"]["status"] == "pending"
    assert "status_url" in data
    mock_task.delay.assert_called_once()

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        from sqlalchemy import select
        result = await s.execute(select(Tenant).where(Tenant.slug == "acme-test"))
        t = result.scalar_one_or_none()
        if t:
            await s.delete(t)
    await _cleanup(factory, actor)


async def test_duplicate_slug_returns_409(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)

    with patch("app.platform_.tenants.api.provision_tenant") as mock_task:
        mock_task.delay = MagicMock()
        await client.post(
            "/platform/tenants",
            json={"slug": "dup-slug", "name": "First"},
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        resp = await client.post(
            "/platform/tenants",
            json={"slug": "dup-slug", "name": "Second"},
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )

    assert resp.status_code == 409

    from sqlalchemy import select
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        result = await s.execute(select(Tenant).where(Tenant.slug == "dup-slug"))
        t = result.scalar_one_or_none()
        if t:
            await s.delete(t)
    await _cleanup(factory, actor)


async def test_invalid_slug_returns_422(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)

    resp = await client.post(
        "/platform/tenants",
        json={"slug": "INVALID SLUG!", "name": "Bad"},
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 422

    await _cleanup(factory, actor)


async def test_get_tenant_returns_full_state(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"get-test-{uuid.uuid4().hex[:6]}",
            schema_name=f"tenant_get_test_{uuid.uuid4().hex[:6]}",
            name="Get Test",
            status="active",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(t)

    resp = await client.get(
        f"/platform/tenants/{t.id}",
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(t.id)

    await _cleanup(factory, t, actor)


async def test_get_tenant_not_found(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)

    resp = await client.get(
        f"/platform/tenants/{uuid.uuid4()}",
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 404

    await _cleanup(factory, actor)


async def test_list_tenants(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"list-test-{uuid.uuid4().hex[:6]}",
            schema_name=f"tenant_list_{uuid.uuid4().hex[:6]}",
            name="List Test",
            status="active",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(t)

    resp = await client.get(
        "/platform/tenants",
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    await _cleanup(factory, t, actor)


async def test_retry_provisioning_requires_failed_status(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"retry-test-{uuid.uuid4().hex[:6]}",
            schema_name=f"tenant_retry_{uuid.uuid4().hex[:6]}",
            name="Retry Test",
            status="pending",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(t)

    resp = await client.post(
        f"/platform/tenants/{t.id}/retry-provisioning",
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 400

    await _cleanup(factory, t, actor)


async def test_non_superuser_cannot_create_tenant(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user = await _create_regular_user(factory)

    resp = await client.post(
        "/platform/tenants",
        json={"slug": "should-fail", "name": "Should Fail"},
        headers={"X-Platform-Actor-ID": str(user.id)},
    )
    assert resp.status_code == 403

    await _cleanup(factory, user)
