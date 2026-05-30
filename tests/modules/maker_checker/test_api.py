import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan
from app.modules.maker_checker.api import router as maker_checker_router
from app.modules.maker_checker.registry import approval_registry

# Register router (not yet done in main.py — will be wired in T18)
app.include_router(maker_checker_router)

approval_registry["api.test.op"] = AsyncMock(return_value={"done": True})

TEST_TENANT_SCHEMA = "tenant_test"


async def _make_tenant_session_override(engine: AsyncEngine):
    """Return a dependency override that yields a session on the test schema."""
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
            )
            yield session

    return _override


async def _seed_actor(engine: AsyncEngine, email: str, full_name: str) -> uuid.UUID:
    """Insert (or return id of) a tenant_users row for the given email."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {TEST_TENANT_SCHEMA}, platform")
        )
        existing = (
            await session.execute(
                text("SELECT id FROM tenant_users WHERE email = :email"),
                {"email": email},
            )
        ).scalar()
        if existing is not None:
            return existing
        new_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO tenant_users "
                "(id, email, full_name, is_active, is_admin, created_at, updated_at) "
                "VALUES (:id, :email, :name, true, true, now(), now())"
            ),
            {"id": new_id, "email": email, "name": full_name},
        )
        await session.commit()
        return new_id


@pytest.fixture
async def maker_id(test_engine: AsyncEngine) -> str:
    return str(await _seed_actor(test_engine, "maker@example.com", "Maker"))


@pytest.fixture
async def checker_id(test_engine: AsyncEngine) -> str:
    return str(await _seed_actor(test_engine, "checker@example.com", "Checker"))


@pytest.fixture
async def client(test_engine: AsyncEngine):
    override = await _make_tenant_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


def _hdr(slug: str, actor_id: str) -> dict[str, str]:
    return {"X-Tenant-Slug": slug, "X-Tenant-Actor-ID": actor_id}


async def test_submit_returns_201(client, maker_id):
    resp = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}, "required_approvals": 1},
        headers=_hdr("test-tenant", maker_id),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "pending"
    assert data["operation_type"] == "api.test.op"


async def test_get_approval(client, maker_id):
    post = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}},
        headers=_hdr("test-tenant", maker_id),
    )
    assert post.status_code == 201, post.text
    rid = post.json()["id"]
    resp = await client.get(
        f"/approvals/{rid}",
        headers=_hdr("test-tenant", maker_id),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


async def test_approve_executes_on_quorum(client, maker_id, checker_id):
    post = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}, "required_approvals": 1},
        headers=_hdr("test-tenant", maker_id),
    )
    assert post.status_code == 201, post.text
    rid = post.json()["id"]
    resp = await client.post(
        f"/approvals/{rid}/approve",
        json={},
        headers=_hdr("test-tenant", checker_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "executed"


async def test_cancel_by_maker(client, maker_id):
    post = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}, "required_approvals": 2},
        headers=_hdr("test-tenant", maker_id),
    )
    assert post.status_code == 201, post.text
    rid = post.json()["id"]
    resp = await client.post(
        f"/approvals/{rid}/cancel",
        json={},
        headers=_hdr("test-tenant", maker_id),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


async def test_unknown_operation_returns_400(client, maker_id):
    resp = await client.post(
        "/approvals",
        json={"operation_type": "no.such.op", "payload": {}},
        headers=_hdr("test-tenant", maker_id),
    )
    assert resp.status_code == 400
