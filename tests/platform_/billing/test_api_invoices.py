"""Integration tests for /platform/billing/invoices endpoints."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.models import PlatformUser


def _make_platform_session_override(engine: AsyncEngine):  # type: ignore[return]
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
            name="Invoice Test",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(t)
    return t


async def _create_plan(factory: async_sessionmaker[AsyncSession]):  # type: ignore[return]
    from app.platform_.billing.models import SubscriptionPlan

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Invoice Plan",
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
        await s.execute(text("DELETE FROM platform.payments"))
        await s.execute(text("DELETE FROM platform.invoice_line_items"))
        await s.execute(text("DELETE FROM platform.invoices"))
        await s.execute(text("DELETE FROM platform.approval_actions"))
        await s.execute(text("DELETE FROM platform.approval_requests"))
        await s.execute(text("DELETE FROM platform.subscriptions"))
        await s.execute(text("DELETE FROM platform.subscription_plans"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))
        await s.execute(text("DELETE FROM platform.audit_log"))


async def _setup_invoice(factory: async_sessionmaker[AsyncSession]):  # type: ignore[return]
    from app.platform_.billing.services import InvoiceService, SubscriptionService

    tenant = await _create_tenant(factory)
    plan = await _create_plan(factory)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        sub_id = sub.id
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        inv = await InvoiceService(s).generate_for_subscription(subscription_id=sub_id)
        inv_id = inv.id
    return tenant, plan, sub_id, inv_id


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


async def test_list_invoices_empty(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        r = await client.get(
            "/platform/billing/invoices",
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        assert r.status_code == 200, r.text
        assert r.json() == []
    finally:
        await _cleanup(factory)


async def test_list_invoices_returns_invoices(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    _, _, _, inv_id = await _setup_invoice(factory)
    try:
        r = await client.get(
            "/platform/billing/invoices",
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) >= 1
        ids = [item["id"] for item in body]
        assert str(inv_id) in ids
    finally:
        await _cleanup(factory)


async def test_list_invoices_filtered_by_tenant(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant, _, _, inv_id = await _setup_invoice(factory)
    # Create a second tenant + invoice
    await _setup_invoice(factory)
    try:
        r = await client.get(
            f"/platform/billing/invoices?tenant_id={tenant.id}",
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        assert body[0]["tenant_id"] == str(tenant.id)
    finally:
        await _cleanup(factory)


async def test_get_invoice_detail_includes_line_items(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    _, _, _, inv_id = await _setup_invoice(factory)
    try:
        r = await client.get(
            f"/platform/billing/invoices/{inv_id}",
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == str(inv_id)
        assert "line_items" in body
        assert len(body["line_items"]) >= 1
        # Each line item must have expected fields
        line = body["line_items"][0]
        assert "description" in line
        assert "amount" in line
    finally:
        await _cleanup(factory)


async def test_get_invoice_404_for_unknown(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        r = await client.get(
            f"/platform/billing/invoices/{uuid.uuid4()}",
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        assert r.status_code == 404
    finally:
        await _cleanup(factory)


async def test_void_invoice_creates_approval_request(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    _, _, _, inv_id = await _setup_invoice(factory)
    try:
        r = await client.post(
            f"/platform/billing/invoices/{inv_id}/void",
            headers={"X-Platform-Actor-ID": str(actor.id)},
            json={"reason": "test void"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending_approval"
        assert "approval_request_id" in body
    finally:
        await _cleanup(factory)


async def test_get_invoice_pdf(test_engine: AsyncEngine, client: AsyncClient) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    tenant, plan, sub_id, invoice_id = await _setup_invoice(factory)
    try:
        r = await client.get(
            f"/platform/billing/invoices/{invoice_id}.pdf",
            headers={"X-Platform-Actor-ID": str(actor.id)},
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 1000
    finally:
        await _cleanup(factory)
