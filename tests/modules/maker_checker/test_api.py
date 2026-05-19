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

MAKER_ID = str(uuid.uuid4())
CHECKER_ID = str(uuid.uuid4())

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


@pytest.fixture
async def client(test_engine: AsyncEngine):
    override = await _make_tenant_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


async def test_submit_returns_201(client):
    resp = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}, "required_approvals": 1},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "pending"
    assert data["operation_type"] == "api.test.op"


async def test_get_approval(client):
    post = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    assert post.status_code == 201, post.text
    rid = post.json()["id"]
    resp = await client.get(
        f"/approvals/{rid}",
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


async def test_approve_executes_on_quorum(client):
    post = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}, "required_approvals": 1},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    assert post.status_code == 201, post.text
    rid = post.json()["id"]
    resp = await client.post(
        f"/approvals/{rid}/approve",
        json={},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": CHECKER_ID},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "executed"


async def test_cancel_by_maker(client):
    post = await client.post(
        "/approvals",
        json={"operation_type": "api.test.op", "payload": {}, "required_approvals": 2},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    assert post.status_code == 201, post.text
    rid = post.json()["id"]
    resp = await client.post(
        f"/approvals/{rid}/cancel",
        json={},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


async def test_unknown_operation_returns_400(client):
    resp = await client.post(
        "/approvals",
        json={"operation_type": "no.such.op", "payload": {}},
        headers={"X-Tenant-Slug": "test-tenant", "X-Actor-ID": MAKER_ID},
    )
    assert resp.status_code == 400
