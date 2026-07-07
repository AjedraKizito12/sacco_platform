"""HTTP tests: member KYC requirements config + completion endpoints."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan

SCHEMA = "tenant_test"
HEADERS = {"X-Tenant-Slug": "test-tenant"}


async def _make_tenant_session_override(engine: AsyncEngine):  # noqa: ANN202
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {SCHEMA}, platform")
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
    app.dependency_overrides[get_tenant_session] = await _make_tenant_session_override(
        test_engine
    )
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
        await s.execute(text("DELETE FROM member_kyc_requirements"))
        await s.execute(text("DELETE FROM member_sessions"))
        await s.execute(text("DELETE FROM audit_log WHERE table_name = 'members'"))
        await s.execute(text("DELETE FROM members"))
        await s.commit()


async def _create_member(client: AsyncClient) -> dict[str, Any]:
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
    return resp.json()


async def test_get_requirements_not_shadowed_by_member_id_route(
    client: AsyncClient,
) -> None:
    # Regression: /members/kyc-requirements must be registered before
    # /members/{member_id} or this returns 422 (UUID parse failure).
    resp = await client.get("/members/kyc-requirements", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 14
    by_key = {i["key"]: i for i in items}
    assert by_key["full_name"]["locked"] is True
    assert by_key["occupation"]["required"] is False  # default_required=False


async def test_put_requirements_replaces_and_ignores_locked(
    client: AsyncClient,
) -> None:
    resp = await client.put(
        "/members/kyc-requirements",
        json={"required": {"full_name": False, "phone": False, "occupation": True}},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    by_key = {i["key"]: i for i in resp.json()["items"]}
    assert by_key["full_name"]["required"] is True  # locked ignored
    assert by_key["phone"]["required"] is False
    assert by_key["occupation"]["required"] is True


async def test_member_kyc_completion_endpoint(client: AsyncClient) -> None:
    member = await _create_member(client)
    resp = await client.get(f"/members/{member['id']}/kyc", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["member_id"] == member["id"]
    assert body["completion"]["is_complete"] is False
    assert body["completion"]["required_total"] > 0


async def test_member_kyc_unknown_member_404(client: AsyncClient) -> None:
    resp = await client.get(f"/members/{uuid.uuid4()}/kyc", headers=HEADERS)
    assert resp.status_code == 404


async def test_member_me_kyc(client: AsyncClient, test_engine: AsyncEngine) -> None:
    member = await _create_member(client)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(
            text(
                "UPDATE members SET status='active', portal_enabled=true WHERE id = :mid"
            ),
            {"mid": member["id"]},
        )
        await s.commit()

    resp = await client.get(
        "/member/me/kyc", headers={**HEADERS, "X-Member-Actor-ID": member["id"]}
    )
    assert resp.status_code == 200, resp.text
    completion = resp.json()["completion"]
    assert completion["is_complete"] is False
    assert any(i["key"] == "next_of_kin_name" for i in completion["items"])
