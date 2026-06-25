"""Integration: member endpoints require a member credential, not a tenant one.

In stub mode the isolation is structural — CurrentMember reads X-Member-Actor-ID,
CurrentTenantUser reads X-Tenant-Actor-ID. In JWT mode the aud claim
("member:<slug>" vs "tenant:<slug>") enforces the same boundary (covered by the
service-level token-audience test).
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from app.core.db import get_tenant_session
from app.main import app, lifespan
from app.modules.members.models import Member

TEST_TENANT_SCHEMA = "tenant_test"
HEADERS = {"X-Tenant-Slug": "test-tenant"}


async def _make_tenant_session_override(engine: AsyncEngine):  # noqa: ANN202
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


@pytest.fixture
async def client(test_engine: AsyncEngine, tenant_actor_id: uuid.UUID):  # noqa: ANN201
    override = await _make_tenant_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = "test-tenant"
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


@pytest.fixture(autouse=True)
async def _clean_members(test_engine: AsyncEngine):  # noqa: ANN201
    yield
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(text("DELETE FROM members"))
        await session.commit()


async def _seed_active_member(engine: AsyncEngine) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        m = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}",
            full_name="Iso Test",
            date_of_birth=date(1990, 1, 1),
            gender="male",
            status="active",
            email=f"m-{uuid.uuid4().hex[:6]}@example.com",
            portal_enabled=True,
        )
        session.add(m)
        await session.commit()
        return m.id


async def test_member_route_rejects_tenant_only_actor(
    client, test_engine: AsyncEngine
) -> None:  # noqa: ANN001
    # The default client carries a tenant actor but NO X-Member-Actor-ID.
    # A member route must not accept the tenant credential.
    await _seed_active_member(test_engine)
    resp = await client.get("/member/savings", headers=HEADERS)
    assert resp.status_code in (401, 403, 422), resp.text
    assert resp.status_code != 200


async def test_member_route_accepts_member_actor(
    client, test_engine: AsyncEngine
) -> None:  # noqa: ANN001
    member_id = await _seed_active_member(test_engine)
    resp = await client.get(
        "/member/savings", headers={**HEADERS, "X-Member-Actor-ID": str(member_id)}
    )
    assert resp.status_code == 200, resp.text
