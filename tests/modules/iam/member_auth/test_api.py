"""HTTP tests: operator enable-portal-access + member set-password.

Stub auth mode (conftest). The client sends X-Tenant-Slug + X-Tenant-Actor-ID
for operator routes. Login via JWT needs real keys (covered by service tests);
here we exercise the enable + set-password (reset/confirm) HTTP surface.
"""
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
        # No Redis in the test sandbox. MemberAuthService supports redis=None
        # (documented fallback): the reset-token jti check is skipped.
        original_redis = app.state.redis
        app.state.redis = None
        c.headers["X-Tenant-Slug"] = "test-tenant"
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        try:
            yield c
        finally:
            app.state.redis = original_redis
    app.dependency_overrides.pop(get_tenant_session, None)


async def _create_member(client, *, email: str | None = None) -> str:  # noqa: ANN001
    body = {
        "full_name": f"Member {uuid.uuid4().hex[:6]}",
        "date_of_birth": "1990-05-15",
        "gender": "female",
    }
    if email is not None:
        body["email"] = email
    resp = await client.post("/members", json=body, headers=HEADERS)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_enable_portal_access_returns_token(client) -> None:  # noqa: ANN001
    member_id = await _create_member(client, email=f"m-{uuid.uuid4().hex[:6]}@example.com")
    resp = await client.post(f"/members/{member_id}/enable-portal-access", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["portal_enabled"] is True
    assert body["set_password_token"]
    assert body["expires_in"] == 86400


async def test_enable_rejects_member_without_email(client) -> None:  # noqa: ANN001
    member_id = await _create_member(client)  # no email
    resp = await client.post(f"/members/{member_id}/enable-portal-access", headers=HEADERS)
    assert resp.status_code == 400, resp.text


async def test_enable_then_set_password(client) -> None:  # noqa: ANN001
    member_id = await _create_member(client, email=f"m-{uuid.uuid4().hex[:6]}@example.com")
    token = (
        await client.post(f"/members/{member_id}/enable-portal-access", headers=HEADERS)
    ).json()["set_password_token"]
    resp = await client.post(
        "/member/auth/password-reset/confirm",
        json={"token": token, "new_password": "Br4nd-New-Pass!"},
        headers=HEADERS,
    )
    assert resp.status_code == 204, resp.text
