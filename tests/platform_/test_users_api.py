"""Integration tests for /platform/users endpoints."""
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.models import PlatformUser
from app.platform_.users.api import router as users_router

# Register router (idempotent check).
if not any(getattr(r, "path", "").startswith("/platform/users") for r in app.routes):
    app.include_router(users_router)


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


async def _make_user(
    factory: async_sessionmaker[AsyncSession],
    *,
    is_superuser: bool = False,
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"u-{uuid.uuid4()}@test.example",
            full_name="Test User",
            is_active=True,
            is_superuser=is_superuser,
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


async def test_list_users_returns_200(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _make_user(factory)

    resp = await client.get(
        "/platform/users", headers={"X-Platform-Actor-ID": str(actor.id)}
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    await _cleanup(factory, actor)


async def test_get_user_returns_detail(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _make_user(factory)
    target = await _make_user(factory)

    resp = await client.get(
        f"/platform/users/{target.id}",
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(target.id)

    await _cleanup(factory, actor, target)


async def test_get_nonexistent_user_returns_404(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _make_user(factory)

    resp = await client.get(
        f"/platform/users/{uuid.uuid4()}",
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 404

    await _cleanup(factory, actor)


async def test_create_user_requires_superuser(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _make_user(factory, is_superuser=False)

    resp = await client.post(
        "/platform/users",
        json={"email": "new@test.example", "full_name": "New User"},
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 403

    await _cleanup(factory, actor)


async def test_create_user_returns_201(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _make_user(factory, is_superuser=True)
    email = f"new-{uuid.uuid4().hex[:8]}@test.example"

    resp = await client.post(
        "/platform/users",
        json={"email": email, "full_name": "New User"},
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == email
    new_id = uuid.UUID(data["id"])

    # Cleanup created user
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        result = await s.execute(select(PlatformUser).where(PlatformUser.id == new_id))
        u = result.scalar_one_or_none()
        if u:
            await s.delete(u)
    await _cleanup(factory, actor)


async def test_duplicate_email_returns_409(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _make_user(factory, is_superuser=True)
    email = f"dup-{uuid.uuid4().hex[:8]}@test.example"

    await client.post(
        "/platform/users",
        json={"email": email, "full_name": "First"},
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    resp = await client.post(
        "/platform/users",
        json={"email": email, "full_name": "Second"},
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 409

    # Cleanup
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        result = await s.execute(
            select(PlatformUser).where(PlatformUser.email == email)
        )
        u = result.scalar_one_or_none()
        if u:
            await s.delete(u)
    await _cleanup(factory, actor)


async def test_update_full_name_no_maker_checker(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _make_user(factory, is_superuser=True)
    target = await _make_user(factory)

    resp = await client.patch(
        f"/platform/users/{target.id}",
        json={"full_name": "Updated Name"},
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"

    await _cleanup(factory, actor, target)


async def test_update_requires_superuser(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _make_user(factory, is_superuser=False)
    target = await _make_user(factory)

    resp = await client.patch(
        f"/platform/users/{target.id}",
        json={"full_name": "Blocked"},
        headers={"X-Platform-Actor-ID": str(actor.id)},
    )
    assert resp.status_code == 403

    await _cleanup(factory, actor, target)
