"""Integration tests for the new tenant lifecycle endpoints:
PATCH, POST /suspend (maker-checker), POST /reactivate, POST /assign-plan.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.platform_.tenants.executors  # noqa: F401 — register executor
from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.billing.models import SubscriptionPlan
from app.platform_.models import PlatformUser, Tenant


def _make_platform_session_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
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


async def _create_superuser(
    factory: async_sessionmaker[AsyncSession], prefix: str = "u",
) -> PlatformUser:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"{prefix}-{uuid.uuid4().hex[:6]}@test.example",
            full_name=prefix.title(),
            is_active=True, is_superuser=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(u)
    return u


async def _create_tenant(
    factory: async_sessionmaker[AsyncSession],
) -> Tenant:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Original Name",
            status="active",
            is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(t)
    return t


async def _create_plan(
    factory: async_sessionmaker[AsyncSession],
) -> SubscriptionPlan:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:6]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            is_active=True,
        )
        s.add(p)
    return p


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL, "
                "subscription_status = 'pending'"
            )
        )
        await s.execute(text("DELETE FROM platform.subscriptions"))
        await s.execute(text("DELETE FROM platform.subscription_plans"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_platform_session] = (
        _make_platform_session_override(test_engine)
    )
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


def _hdr(actor_id: uuid.UUID) -> dict[str, str]:
    return {"X-Platform-Actor-ID": str(actor_id)}


# ── PATCH ────────────────────────────────────────────────────────────────────


async def test_patch_updates_name(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    try:
        r = await client.patch(
            f"/platform/tenants/{tenant.id}",
            json={"name": "Renamed Tenant"},
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Renamed Tenant"
    finally:
        await _cleanup(factory)


async def test_patch_404_for_unknown_tenant(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        r = await client.patch(
            f"/platform/tenants/{uuid.uuid4()}",
            json={"name": "X"},
            headers=_hdr(actor.id),
        )
        assert r.status_code == 404
    finally:
        await _cleanup(factory)


# ── POST /suspend (maker-checker) ────────────────────────────────────────────


async def test_suspend_creates_approval_request(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_superuser(factory, "maker")
    tenant = await _create_tenant(factory)
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/suspend",
            json={"reason": "Suspected fraudulent activity reported"},
            headers=_hdr(maker.id),
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "pending_approval"
        assert "approval_request_id" in body
    finally:
        await _cleanup(factory)


async def test_suspend_end_to_end_via_approval(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    """Maker submits suspend → checker approves via /platform/approvals
    → executor flips status + is_active + subscription_status.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_superuser(factory, "maker")
    checker = await _create_superuser(factory, "checker")
    tenant = await _create_tenant(factory)
    try:
        # Submit
        sub = await client.post(
            f"/platform/tenants/{tenant.id}/suspend",
            json={"reason": "Suspected fraudulent activity reported"},
            headers=_hdr(maker.id),
        )
        approval_id = sub.json()["approval_request_id"]

        # Approve
        apr = await client.post(
            f"/platform/approvals/{approval_id}/approve",
            json={"comment": "verified"},
            headers=_hdr(checker.id),
        )
        assert apr.status_code == 200, apr.text
        assert apr.json()["status"] == "executed"

        # Verify tenant state
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.is_active is False
            assert t.status == "suspended"
            assert t.subscription_status == "suspended"
    finally:
        await _cleanup(factory)


# ── POST /reactivate ─────────────────────────────────────────────────────────


async def test_reactivate_restores_state(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    # Force-suspend
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = await s.get(Tenant, tenant.id)
        assert t is not None
        t.is_active = False
        t.status = "suspended"
        t.subscription_status = "suspended"
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/reactivate",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["is_active"] is True
        assert body["status"] == "active"
        # No live subscription seeded → subscription_status returns to pending
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            t2 = await s.get(Tenant, tenant.id)
            assert t2 is not None
            assert t2.subscription_status == "pending"
    finally:
        await _cleanup(factory)


async def test_reactivate_rejects_unsuspended(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)  # status='active', is_active=True
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/reactivate",
            headers=_hdr(actor.id),
        )
        assert r.status_code == 409, r.text
    finally:
        await _cleanup(factory)


# ── POST /assign-plan ────────────────────────────────────────────────────────


async def test_assign_plan_creates_subscription(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory)
    try:
        r = await client.post(
            f"/platform/tenants/{tenant.id}/assign-plan",
            json={"plan_id": str(plan.id)},
            headers=_hdr(actor.id),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["tenant_id"] == str(tenant.id)
        assert body["plan_id"] == str(plan.id)
        assert body["status"] in {"active", "trialing"}
    finally:
        await _cleanup(factory)


async def test_assign_plan_rejects_duplicate(
    test_engine: AsyncEngine, client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory)
    try:
        r1 = await client.post(
            f"/platform/tenants/{tenant.id}/assign-plan",
            json={"plan_id": str(plan.id)},
            headers=_hdr(actor.id),
        )
        assert r1.status_code == 201
        r2 = await client.post(
            f"/platform/tenants/{tenant.id}/assign-plan",
            json={"plan_id": str(plan.id)},
            headers=_hdr(actor.id),
        )
        assert r2.status_code == 409, r2.text
    finally:
        await _cleanup(factory)
