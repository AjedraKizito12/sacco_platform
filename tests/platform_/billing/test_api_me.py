"""Integration tests for /billing/me/* (tenant-facing billing endpoints).

These endpoints:
  - Require CurrentTenantUser auth (X-Tenant-Actor-ID stub header validated
    against tenant_users in the tenant schema).
  - Use get_platform_session to read billing data from platform.*.
  - Resolve tenant_id by joining platform.tenants on the X-Tenant-Slug header.

Test setup must:
  1. Override BOTH get_tenant_session (for user auth) AND get_platform_session
     (for billing data + tenant lookup).
  2. Create a platform.tenants row whose slug='test-tenant' and
     schema_name='tenant_test' so _get_tenant_id_from_slug resolves correctly.
  3. Create billing data (SubscriptionPlan, Subscription, Invoice) linked to
     that tenant's UUID.
  4. The tenant_actor_id fixture from conftest ensures a tenant_users row
     exists in the tenant schema for stub auth.
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

from app.core.db import get_platform_session, get_tenant_session
from app.main import app, lifespan

TEST_TENANT_SCHEMA = "tenant_test"
TEST_TENANT_SLUG = "test-tenant"


# ── Session overrides ─────────────────────────────────────────────────────────


def _make_platform_override(engine: AsyncEngine):  # type: ignore[return]
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


def _make_tenant_override(engine: AsyncEngine):  # type: ignore[return]
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


# ── Data helpers ──────────────────────────────────────────────────────────────


async def _ensure_test_tenant(
    factory: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    """Upsert a platform.tenants row for 'test-tenant'.

    Returns the tenant's UUID. This is needed because _get_tenant_id_from_slug
    queries platform.tenants; the test schema only exists in the DB if a row
    points to it.
    """
    from app.platform_.models import Tenant

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        existing = await s.scalar(
            text("SELECT id FROM platform.tenants WHERE slug = :slug"),
            {"slug": TEST_TENANT_SLUG},
        )
        if existing is not None:
            return uuid.UUID(str(existing))
        now = datetime.now(UTC)
        t = Tenant(
            slug=TEST_TENANT_SLUG,
            schema_name=TEST_TENANT_SCHEMA,
            name="Test Tenant",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        s.add(t)
    return t.id


async def _create_plan(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    from app.platform_.billing.models import SubscriptionPlan

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        p = SubscriptionPlan(
            code=f"me-plan-{uuid.uuid4().hex[:8]}",
            name="Me Plan",
            base_price=Decimal("60000.0000"),
            billing_period="monthly",
        )
        s.add(p)
    return p.id


async def _create_subscription_and_invoice(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create subscription + invoice, return (subscription_id, invoice_id)."""
    from app.platform_.billing.services import InvoiceService, SubscriptionService

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        sub = await SubscriptionService(s).assign(
            tenant_id=tenant_id,
            plan_id=plan_id,
        )
        sub_id = sub.id

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        inv = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id,
        )
        inv_id = inv.id

    return sub_id, inv_id


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL,"
                " subscription_status = 'pending'"
                " WHERE slug = :slug"
            ),
            {"slug": TEST_TENANT_SLUG},
        )
        await s.execute(text("DELETE FROM platform.invoice_line_items"))
        await s.execute(text("DELETE FROM platform.invoices"))
        await s.execute(text("DELETE FROM platform.subscriptions"))
        await s.execute(text("DELETE FROM platform.subscription_plans"))
        # Delete the test tenant row we upserted (reset for next run)
        await s.execute(
            text("DELETE FROM platform.tenants WHERE slug = :slug"),
            {"slug": TEST_TENANT_SLUG},
        )
        await s.execute(text("DELETE FROM platform.audit_log"))


# ── Client fixture ────────────────────────────────────────────────────────────


@pytest.fixture
async def me_client(
    test_engine: AsyncEngine,
    tenant_actor_id: uuid.UUID,
) -> AsyncGenerator[AsyncClient, None]:
    """Test client with both session overrides + tenant auth headers."""
    app.dependency_overrides[get_platform_session] = _make_platform_override(test_engine)
    app.dependency_overrides[get_tenant_session] = _make_tenant_override(test_engine)

    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = TEST_TENANT_SLUG
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        yield c

    app.dependency_overrides.pop(get_platform_session, None)
    app.dependency_overrides.pop(get_tenant_session, None)


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_my_subscription_returns_active(
    test_engine: AsyncEngine,
    me_client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    tenant_id = await _ensure_test_tenant(factory)
    plan_id = await _create_plan(factory)
    try:
        _sub_id, _inv_id = await _create_subscription_and_invoice(
            factory, tenant_id, plan_id
        )
        r = await me_client.get("/billing/me/subscription")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tenant_id"] == str(tenant_id)
        assert body["status"] == "active"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_get_my_subscription_404_when_none(
    test_engine: AsyncEngine,
    me_client: AsyncClient,
) -> None:
    """When no active subscription exists for the tenant, return 404."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    # Create the tenant row but NO subscription.
    await _ensure_test_tenant(factory)
    try:
        r = await me_client.get("/billing/me/subscription")
        assert r.status_code == 404, r.text
    finally:
        # Clean up only the tenant row (no billing data created).
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(
                text("DELETE FROM platform.tenants WHERE slug = :slug"),
                {"slug": TEST_TENANT_SLUG},
            )
            await s.execute(text("DELETE FROM platform.audit_log"))


@pytest.mark.anyio
async def test_list_my_invoices_returns_own(
    test_engine: AsyncEngine,
    me_client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    tenant_id = await _ensure_test_tenant(factory)
    plan_id = await _create_plan(factory)
    try:
        _sub_id, inv_id = await _create_subscription_and_invoice(
            factory, tenant_id, plan_id
        )
        r = await me_client.get("/billing/me/invoices")
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        ids = [item["id"] for item in body]
        assert str(inv_id) in ids
        # All returned invoices must belong to this tenant.
        for item in body:
            assert item["tenant_id"] == str(tenant_id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_get_my_invoice_404_for_other_tenant(
    test_engine: AsyncEngine,
    me_client: AsyncClient,
) -> None:
    """Cross-tenant access returns 404, not 403 (don't leak existence)."""
    from app.platform_.models import Tenant

    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    # Ensure the test tenant exists (for the slug lookup to work).
    await _ensure_test_tenant(factory)
    # Create a DIFFERENT tenant and an invoice for it.
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        now = datetime.now(UTC)
        other = Tenant(
            slug=f"other-{uuid.uuid4().hex[:6]}",
            schema_name=f"tenant_o{uuid.uuid4().hex[:8]}",
            name="Other Tenant",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        s.add(other)
    other_tenant_id = other.id

    plan_id = await _create_plan(factory)
    try:
        _sub_id, other_inv_id = await _create_subscription_and_invoice(
            factory, other_tenant_id, plan_id
        )
        # The me_client is authenticated as the test tenant.
        r = await me_client.get(f"/billing/me/invoices/{other_inv_id}")
        assert r.status_code == 404, r.text
    finally:
        # Full cleanup.
        async with factory() as s, s.begin():
            await s.execute(text("SET LOCAL search_path TO platform"))
            await s.execute(
                text(
                    "UPDATE platform.tenants SET current_subscription_id = NULL,"
                    " subscription_status = 'pending'"
                )
            )
            await s.execute(text("DELETE FROM platform.invoice_line_items"))
            await s.execute(text("DELETE FROM platform.invoices"))
            await s.execute(text("DELETE FROM platform.subscriptions"))
            await s.execute(text("DELETE FROM platform.subscription_plans"))
            await s.execute(text("DELETE FROM platform.tenants"))
            await s.execute(text("DELETE FROM platform.audit_log"))


@pytest.mark.anyio
async def test_get_my_invoice_pdf_returns_pdf_bytes(
    test_engine: AsyncEngine,
    me_client: AsyncClient,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    tenant_id = await _ensure_test_tenant(factory)
    plan_id = await _create_plan(factory)
    try:
        _sub_id, inv_id = await _create_subscription_and_invoice(
            factory, tenant_id, plan_id
        )
        r = await me_client.get(f"/billing/me/invoices/{inv_id}.pdf")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
    finally:
        await _cleanup(factory)
