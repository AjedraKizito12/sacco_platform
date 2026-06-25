"""HTTP test: GET /member/me (member self-service profile, stub auth)."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from app.core.db import get_tenant_session
from app.main import app, lifespan

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
    """Delete members created here so other modules' tests stay isolated."""
    yield
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(text("DELETE FROM member_sessions"))
        await session.execute(text("DELETE FROM audit_log WHERE table_name = 'members'"))
        await session.execute(text("DELETE FROM members"))
        await session.commit()


async def _create_active_member(client, engine: AsyncEngine) -> str:  # noqa: ANN001
    """Create a member via HTTP, then activate + enable it via direct DB write."""
    resp = await client.post(
        "/members",
        json={
            "full_name": f"Member {uuid.uuid4().hex[:6]}",
            "date_of_birth": "1990-05-15",
            "gender": "female",
            "email": f"m-{uuid.uuid4().hex[:6]}@example.com",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    member_id = resp.json()["id"]

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET search_path TO {TEST_TENANT_SCHEMA}, platform"))
        await session.execute(
            text(
                "UPDATE members SET status='active', portal_enabled=true WHERE id = :mid"
            ),
            {"mid": member_id},
        )
        await session.commit()
    return member_id


def _member_headers(member_id: str) -> dict[str, str]:
    return {**HEADERS, "X-Member-Actor-ID": member_id}


async def test_member_me_returns_own_profile(client, test_engine: AsyncEngine) -> None:  # noqa: ANN001
    member_id = await _create_active_member(client, test_engine)
    resp = await client.get("/member/me", headers=_member_headers(member_id))
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == member_id
