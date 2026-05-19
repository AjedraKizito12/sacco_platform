"""Tests for the platform auth stub dependency."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated
from unittest.mock import patch

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.platform_.auth import get_current_platform_user, get_current_superuser
from app.platform_.models import PlatformUser

# ── Minimal test app ─────────────────────────────────────────────────────────

_test_app = FastAPI()


@_test_app.get("/protected")
async def _protected(
    user: Annotated[PlatformUser, Depends(get_current_platform_user)],
) -> dict[str, str]:
    return {"id": str(user.id)}


@_test_app.get("/superuser")
async def _superuser_route(
    user: Annotated[PlatformUser, Depends(get_current_superuser)],
) -> dict[str, str]:
    return {"id": str(user.id)}


# ── Helper ────────────────────────────────────────────────────────────────────


async def _insert_user(
    factory: async_sessionmaker[AsyncSession],
    *,
    is_active: bool = True,
    is_superuser: bool = False,
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        u = PlatformUser(
            email=f"auth-test-{uuid.uuid4()}@test.example",
            full_name="Auth Test User",
            is_active=is_active,
            is_superuser=is_superuser,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _delete_user(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = await s.get(PlatformUser, user_id)
        if u:
            await s.delete(u)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def app_client(test_engine: AsyncEngine) -> Generator[None, None, None]:
    """Return an AsyncClient whose app uses the test_engine for platform sessions."""

    async def _override_platform_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_engine.connect() as conn:
            await conn.begin()
            await conn.execute(text("SET LOCAL search_path TO platform"))
            session = AsyncSession(bind=conn, expire_on_commit=False)
            session.sync_session.info["is_platform"] = True
            try:
                yield session
            finally:
                await session.close()
                await conn.rollback()

    _test_app.dependency_overrides[get_platform_session] = _override_platform_session
    yield
    _test_app.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_missing_header_returns_422(test_engine: AsyncEngine, app_client: None) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_test_app), base_url="http://test"
    ) as client:
        resp = await client.get("/protected")
    assert resp.status_code == 422


async def test_invalid_uuid_returns_400(test_engine: AsyncEngine, app_client: None) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_test_app), base_url="http://test"
    ) as client:
        resp = await client.get("/protected", headers={"X-Platform-Actor-ID": "not-a-uuid"})
    assert resp.status_code == 400


async def test_unknown_actor_returns_401(test_engine: AsyncEngine, app_client: None) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_test_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/protected",
            headers={"X-Platform-Actor-ID": str(uuid.uuid4())},
        )
    assert resp.status_code == 401


async def test_inactive_actor_returns_403(test_engine: AsyncEngine, app_client: None) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user = await _insert_user(factory, is_active=False)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/protected",
                headers={"X-Platform-Actor-ID": str(user.id)},
            )
        assert resp.status_code == 403
    finally:
        await _delete_user(factory, user.id)


async def test_active_actor_returns_200(test_engine: AsyncEngine, app_client: None) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user = await _insert_user(factory, is_active=True)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/protected",
                headers={"X-Platform-Actor-ID": str(user.id)},
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(user.id)
    finally:
        await _delete_user(factory, user.id)


async def test_non_superuser_returns_403_on_superuser_route(
    test_engine: AsyncEngine, app_client: None
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user = await _insert_user(factory, is_active=True, is_superuser=False)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/superuser",
                headers={"X-Platform-Actor-ID": str(user.id)},
            )
        assert resp.status_code == 403
    finally:
        await _delete_user(factory, user.id)


async def test_superuser_returns_200_on_superuser_route(
    test_engine: AsyncEngine, app_client: None
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    user = await _insert_user(factory, is_active=True, is_superuser=True)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=_test_app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/superuser",
                headers={"X-Platform-Actor-ID": str(user.id)},
            )
        assert resp.status_code == 200
    finally:
        await _delete_user(factory, user.id)


def test_prod_boot_guard_raises_on_stub_auth_in_production() -> None:
    """APP_ENV=production + PLATFORM_AUTH_MODE=stub must refuse to start."""
    import asyncio

    from app.core.config import Settings, get_settings
    from app.main import app as fastapi_app

    prod_settings = Settings(
        database_url="postgresql+asyncpg://sacco:sacco@localhost:5432/sacco_test",
        app_secret_key="test-secret-key-not-used-in-production",
        app_env="production",
        platform_auth_mode="stub",
    )
    get_settings.cache_clear()
    with (
        patch("app.main.settings", prod_settings),
        pytest.raises(
            RuntimeError,
            match="PLATFORM_AUTH_MODE=stub is forbidden in production",
        ),
    ):
        asyncio.run(_run_lifespan(fastapi_app))
    get_settings.cache_clear()


async def _run_lifespan(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        pass
