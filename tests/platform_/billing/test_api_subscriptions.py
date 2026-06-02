"""Integration tests for /platform/billing/subscriptions endpoints."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.models import PlatformUser


def _make_platform_session_override(engine: AsyncEngine) -> Any:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text("SET LOCAL search_path TO platform"))
            session.sync_session.info["is_platform"] = True
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


async def _create_superuser(factory: async_sessionmaker[AsyncSession]) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"super-{uuid.uuid4()}@test.example",
            full_name="Super",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _create_tenant(factory: async_sessionmaker[AsyncSession]):  # type: ignore[return]
    from app.platform_.models import Tenant

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Sub Test",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(t)
    return t


async def _create_plan(
    factory: async_sessionmaker[AsyncSession],
    *,
    is_active: bool = True,
):  # type: ignore[return]
    from app.platform_.billing.models import SubscriptionPlan

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Sub Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            is_active=is_active,
        )
        s.add(p)
    return p


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        # Null FKs first
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL, "
                "subscription_status = 'pending'"
            )
        )
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.subscriptions"))
        await s.execute(text("DELETE FROM platform.subscription_plans"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


async def test_assign_subscription(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory)
    try:
        r = await client.post(
            "/platform/billing/subscriptions",
            headers={"X-Platform-Actor-ID": str(actor.id)},
            json={
                "tenant_id": str(tenant.id),
                "plan_id": str(plan.id),
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["tenant_id"] == str(tenant.id)
        assert body["status"] == "active"
    finally:
        await _cleanup(factory)


async def test_assign_subscription_rejects_inactive_plan(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory, is_active=False)
    try:
        r = await client.post(
            "/platform/billing/subscriptions",
            headers={"X-Platform-Actor-ID": str(actor.id)},
            json={"tenant_id": str(tenant.id), "plan_id": str(plan.id)},
        )
        assert r.status_code == 409
    finally:
        await _cleanup(factory)


async def test_list_subscriptions_filters_by_tenant(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory)
    try:
        headers = {"X-Platform-Actor-ID": str(actor.id)}
        await client.post(
            "/platform/billing/subscriptions",
            headers=headers,
            json={"tenant_id": str(tenant.id), "plan_id": str(plan.id)},
        )
        r = await client.get(
            f"/platform/billing/subscriptions?tenant_id={tenant.id}",
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        assert body[0]["tenant_id"] == str(tenant.id)
    finally:
        await _cleanup(factory)


async def test_cancel_subscription_at_period_end(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory)
    try:
        headers = {"X-Platform-Actor-ID": str(actor.id)}
        create = await client.post(
            "/platform/billing/subscriptions",
            headers=headers,
            json={"tenant_id": str(tenant.id), "plan_id": str(plan.id)},
        )
        sub_id = create.json()["id"]
        r = await client.post(
            f"/platform/billing/subscriptions/{sub_id}/cancel",
            headers=headers,
            json={"reason": "test cancellation"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "cancellation_scheduled"
    finally:
        await _cleanup(factory)


async def test_cancel_subscription_immediate_creates_approval_request(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory)
    try:
        headers = {"X-Platform-Actor-ID": str(actor.id)}
        create = await client.post(
            "/platform/billing/subscriptions",
            headers=headers,
            json={"tenant_id": str(tenant.id), "plan_id": str(plan.id)},
        )
        sub_id = create.json()["id"]
        r = await client.post(
            f"/platform/billing/subscriptions/{sub_id}/cancel?mode=immediate",
            headers=headers,
            json={"reason": "hard cancel"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending_approval"
        assert "approval_request_id" in body
    finally:
        await _cleanup(factory)


async def test_reactivate_subscription_from_suspended(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory)
    try:
        headers = {"X-Platform-Actor-ID": str(actor.id)}
        create = await client.post(
            "/platform/billing/subscriptions",
            headers=headers,
            json={"tenant_id": str(tenant.id), "plan_id": str(plan.id)},
        )
        sub_id = create.json()["id"]
        # Force the subscription into 'suspended' via raw SQL
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(
                text(
                    "UPDATE platform.subscriptions SET status = 'suspended' "
                    "WHERE id = :id"
                ),
                {"id": sub_id},
            )
            await s.execute(
                text(
                    "UPDATE platform.tenants SET subscription_status = 'suspended' "
                    "WHERE id = :id"
                ),
                {"id": str(tenant.id)},
            )
        r = await client.post(
            f"/platform/billing/subscriptions/{sub_id}/reactivate",
            headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "active"
    finally:
        await _cleanup(factory)
