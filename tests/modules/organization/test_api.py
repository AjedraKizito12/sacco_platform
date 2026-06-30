from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan

SCHEMA = "tenant_test"


async def _tenant_session_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


@pytest.fixture
async def client(
    test_engine: AsyncEngine, tenant_actor_id: uuid.UUID
) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_tenant_session] = await _tenant_session_override(test_engine)
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = "test-tenant"
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM organization_profile"))
        await s.commit()


async def test_get_creates_empty_profile(client: AsyncClient) -> None:
    resp = await client.get("/organization/kyc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is False
    assert body["completion"]["is_complete"] is False
    assert body["values"]["legal_name"] is None


async def test_put_updates_values_and_completion(client: AsyncClient) -> None:
    resp = await client.put("/organization/kyc", json={"legal_name": "Umoja SACCO"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["values"]["legal_name"] == "Umoja SACCO"
    assert any(
        i["key"] == "legal_name" and i["present"] for i in body["completion"]["items"]
    )
