"""End-to-end: maker records payment → checker approves via /platform/approvals
→ payment confirmed via billing.confirm_payment executor.

Validates that P1.7-01 (platform approvals API) correctly unblocks the
existing billing maker-checker flow. The executor is registered at import
time in app/platform_/billing/executors.py — imported by app/main.py.
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

from app.core.db import get_platform_session
from app.main import app, lifespan
from app.platform_.billing.models import Invoice, Payment, SubscriptionPlan
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


async def _seed_billing_invoice(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[PlatformUser, PlatformUser, uuid.UUID]:
    """Create maker, checker, tenant, plan, subscription, and invoice.

    Returns (maker, checker, invoice_id).
    """
    from app.platform_.billing.services import InvoiceService, SubscriptionService

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        maker = PlatformUser(
            email=f"maker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Maker",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        checker = PlatformUser(
            email=f"checker-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Checker",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        tenant = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="E2E Pmt Test",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        plan = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:6]}",
            name="E2E Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            is_active=True,
        )
        s.add_all([maker, checker, tenant, plan])

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        sub_id = sub.id

    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        invoice = await InvoiceService(s).generate_for_subscription(subscription_id=sub_id)
        invoice_id = invoice.id

    return maker, checker, invoice_id


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
        await s.execute(text("DELETE FROM platform.outbox_events"))


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    override = _make_platform_session_override(test_engine)
    app.dependency_overrides[get_platform_session] = override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_platform_session, None)


async def test_payment_confirmation_e2e(
    test_engine: AsyncEngine, client: AsyncClient
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    maker, checker, invoice_id = await _seed_billing_invoice(factory)
    try:
        # 1. Maker records a payment — creates Payment(pending) + ApprovalRequest.
        rec = await client.post(
            f"/platform/billing/invoices/{invoice_id}/payments",
            headers={"X-Platform-Actor-ID": str(maker.id)},
            json={
                "amount": "50000.0000",
                "currency": "UGX",
                "payment_method": "bank_transfer",
                "external_reference": "MTN-REF-12345",
                "idempotency_key": f"k-{uuid.uuid4().hex}",
            },
        )
        assert rec.status_code == 200, rec.text
        body = rec.json()
        assert body["status"] == "pending_approval"
        approval_id = body["approval_request_id"]
        payment_id = body["payment_id"]

        # 2. Checker approves via the new /platform/approvals/{id}/approve endpoint.
        appr = await client.post(
            f"/platform/approvals/{approval_id}/approve",
            headers={"X-Platform-Actor-ID": str(checker.id)},
            json={"comment": "verified receipt"},
        )
        assert appr.status_code == 200, appr.text
        assert appr.json()["status"] == "executed"

        # 3. Verify Payment.status == 'confirmed' via the DB.
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            pmt = await s.get(Payment, uuid.UUID(payment_id))
            assert pmt is not None
            assert pmt.status == "confirmed"
            assert pmt.confirmed_at is not None

        # 4. Verify Invoice.amount_paid is updated.
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            assert inv.amount_paid == Decimal("50000.0000")
            assert inv.status == "paid"
    finally:
        await _cleanup(factory)
