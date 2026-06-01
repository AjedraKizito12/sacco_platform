"""Integration tests for /platform/billing/invoices/{id}/payments and
/platform/billing/payments endpoints."""
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
            name="Payment Test",
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
            name="Payment Plan",
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


async def test_record_payment_creates_pending_payment_and_approval_request(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    _, _, _, inv_id = await _setup_invoice(factory)
    try:
        r = await client.post(
            f"/platform/billing/invoices/{inv_id}/payments",
            headers={"X-Platform-Actor-ID": str(actor.id)},
            json={
                "amount": "50000.0000",
                "currency": "UGX",
                "payment_method": "cash",
                "idempotency_key": f"test-pay-{uuid.uuid4().hex}",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending_approval"
        assert "payment_id" in body
        assert "approval_request_id" in body
        assert body.get("idempotent") != "true"
    finally:
        await _cleanup(factory)


async def test_record_payment_is_idempotent(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    _, _, _, inv_id = await _setup_invoice(factory)
    idem_key = f"idem-{uuid.uuid4().hex}"
    try:
        headers = {"X-Platform-Actor-ID": str(actor.id)}
        payload = {
            "amount": "50000.0000",
            "currency": "UGX",
            "payment_method": "cash",
            "idempotency_key": idem_key,
        }
        r1 = await client.post(
            f"/platform/billing/invoices/{inv_id}/payments",
            headers=headers,
            json=payload,
        )
        assert r1.status_code == 200, r1.text
        body1 = r1.json()

        # Second identical call — same idempotency_key
        r2 = await client.post(
            f"/platform/billing/invoices/{inv_id}/payments",
            headers=headers,
            json=payload,
        )
        assert r2.status_code == 200, r2.text
        body2 = r2.json()

        # Same payment_id and approval_request_id
        assert body2["payment_id"] == body1["payment_id"]
        assert body2["approval_request_id"] == body1["approval_request_id"]
        assert body2.get("idempotent") == "true"
    finally:
        await _cleanup(factory)


async def test_record_payment_404_for_unknown_invoice(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    try:
        r = await client.post(
            f"/platform/billing/invoices/{uuid.uuid4()}/payments",
            headers={"X-Platform-Actor-ID": str(actor.id)},
            json={
                "amount": "1000.0000",
                "currency": "UGX",
                "payment_method": "cash",
                "idempotency_key": f"test-404-{uuid.uuid4().hex}",
            },
        )
        assert r.status_code == 404
    finally:
        await _cleanup(factory)


async def test_reject_payment_marks_both_rejected(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_superuser(factory)
    checker = await _create_superuser(factory)
    _, _, _, inv_id = await _setup_invoice(factory)
    try:
        # Maker records the payment
        r_record = await client.post(
            f"/platform/billing/invoices/{inv_id}/payments",
            headers={"X-Platform-Actor-ID": str(maker.id)},
            json={
                "amount": "50000.0000",
                "currency": "UGX",
                "payment_method": "cash",
                "idempotency_key": f"reject-test-{uuid.uuid4().hex}",
            },
        )
        assert r_record.status_code == 200, r_record.text
        payment_id = r_record.json()["payment_id"]

        # Checker rejects (different user)
        r_reject = await client.post(
            f"/platform/billing/payments/{payment_id}/reject",
            headers={"X-Platform-Actor-ID": str(checker.id)},
            json={"reason": "test rejection"},
        )
        assert r_reject.status_code == 200, r_reject.text
        body = r_reject.json()
        assert body["status"] == "rejected"
        assert body["payment_id"] == payment_id
    finally:
        await _cleanup(factory)


async def test_reject_payment_rejects_self_rejection(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker = await _create_superuser(factory)
    _, _, _, inv_id = await _setup_invoice(factory)
    try:
        # Maker records the payment
        r_record = await client.post(
            f"/platform/billing/invoices/{inv_id}/payments",
            headers={"X-Platform-Actor-ID": str(maker.id)},
            json={
                "amount": "50000.0000",
                "currency": "UGX",
                "payment_method": "cash",
                "idempotency_key": f"self-reject-{uuid.uuid4().hex}",
            },
        )
        assert r_record.status_code == 200, r_record.text
        payment_id = r_record.json()["payment_id"]

        # Maker tries to self-reject → 409
        r_reject = await client.post(
            f"/platform/billing/payments/{payment_id}/reject",
            headers={"X-Platform-Actor-ID": str(maker.id)},
            json={"reason": "self-rejection attempt"},
        )
        assert r_reject.status_code == 409
    finally:
        await _cleanup(factory)


async def test_pending_confirmation_list_returns_only_pending(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor = await _create_superuser(factory)
    _, _, _, inv_id = await _setup_invoice(factory)
    try:
        headers = {"X-Platform-Actor-ID": str(actor.id)}
        # Record a pending payment
        r_record = await client.post(
            f"/platform/billing/invoices/{inv_id}/payments",
            headers=headers,
            json={
                "amount": "50000.0000",
                "currency": "UGX",
                "payment_method": "cash",
                "idempotency_key": f"pending-list-{uuid.uuid4().hex}",
            },
        )
        assert r_record.status_code == 200, r_record.text
        payment_id = r_record.json()["payment_id"]

        # List pending — should include our payment
        r_list = await client.get(
            "/platform/billing/payments/pending-confirmation",
            headers=headers,
        )
        assert r_list.status_code == 200, r_list.text
        ids = [p["id"] for p in r_list.json()]
        assert payment_id in ids
        # All returned items must be pending
        for p in r_list.json():
            assert p["status"] == "pending"
    finally:
        await _cleanup(factory)
