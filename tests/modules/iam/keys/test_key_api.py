import pytest
from collections.abc import AsyncGenerator
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app
from app.modules.iam.keys.service import clear_key_caches


def _make_platform_session_override(engine: AsyncEngine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            yield session

    return _override


@pytest.fixture(autouse=True)
def reset_caches():
    clear_key_caches()
    yield
    clear_key_caches()


@pytest.fixture(autouse=True)
def override_db(test_engine: AsyncEngine):
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    yield
    app.dependency_overrides.pop(get_platform_session, None)


@pytest.mark.anyio
async def test_jwks_endpoint_is_reachable_and_returns_keys_list():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/.well-known/jwks.json")
    assert response.status_code == 200
    body = response.json()
    assert "keys" in body
    assert isinstance(body["keys"], list)


@pytest.mark.anyio
async def test_jwks_endpoint_requires_no_auth_header():
    # No Authorization or X-Platform-Actor-ID — must not return 401 or 403.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/.well-known/jwks.json")
    assert response.status_code not in (401, 403)


@pytest.mark.anyio
async def test_platform_jwt_keys_list_rejects_non_uuid_actor_id():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/platform/jwt-keys/",
            headers={"X-Platform-Actor-ID": "not-a-uuid"},
        )
    assert response.status_code in (400, 422)


@pytest.mark.anyio
async def test_platform_jwt_keys_list_rejects_missing_actor_id():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/platform/jwt-keys/")
    assert response.status_code == 422  # missing required header
