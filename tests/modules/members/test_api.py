from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan

TEST_TENANT_SCHEMA = "tenant_test"
ACTOR_ID = str(uuid.uuid4())
HEADERS = {"X-Tenant-Slug": "test-tenant", "X-Actor-ID": ACTOR_ID}


async def _make_tenant_session_override(engine: AsyncEngine):
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
async def client(test_engine: AsyncEngine):
    override = await _make_tenant_session_override(test_engine)
    app.dependency_overrides[get_tenant_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


def _member_body(**overrides) -> dict:
    base = {
        "full_name": "Grace Auma",
        "date_of_birth": "1988-03-22",
        "gender": "female",
    }
    base.update(overrides)
    return base


async def test_register_member_returns_201(client):
    resp = await client.post("/members", json=_member_body(), headers=HEADERS)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "pending"
    assert data["member_number"].startswith("M-")
    assert data["joined_at"] is None


async def test_register_member_duplicate_email_returns_409(client):
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    await client.post("/members", json=_member_body(email=email), headers=HEADERS)
    resp = await client.post("/members", json=_member_body(email=email), headers=HEADERS)
    assert resp.status_code == 409, resp.text


async def test_list_members_returns_200(client):
    await client.post("/members", json=_member_body(), headers=HEADERS)
    resp = await client.get("/members", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


async def test_list_members_filter_by_status(client):
    resp = await client.get("/members?status=pending", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    for m in resp.json():
        assert m["status"] == "pending"


async def test_get_member_returns_200(client):
    created = (
        await client.post("/members", json=_member_body(), headers=HEADERS)
    ).json()
    member_id = created["id"]

    resp = await client.get(f"/members/{member_id}", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == member_id


async def test_get_member_not_found_returns_404(client):
    resp = await client.get(f"/members/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404, resp.text


async def test_submit_status_change_returns_202(client):
    created = (
        await client.post("/members", json=_member_body(), headers=HEADERS)
    ).json()
    member_id = created["id"]

    resp = await client.post(
        f"/members/{member_id}/status-change",
        json={
            "new_status": "active",
            "reason": "KYC verified",
            "idempotency_key": f"activate-{uuid.uuid4().hex}",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert "approval_request_id" in data
    assert data["status"] == "pending"
