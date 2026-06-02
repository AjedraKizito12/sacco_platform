"""Tests for billing maker-checker executors.

Verifies each executor reads its payload, calls the right service, and is
idempotent on re-execution.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.executors import (
    execute_cancel_subscription,
    execute_confirm_payment,
    execute_void_invoice,
)
from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Payment,
    Subscription,
    SubscriptionPlan,
)
from app.platform_.billing.services import (
    InvoiceService,
    PaymentService,
    SubscriptionService,
)
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(factory) -> Tenant:
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Test Tenant",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t


async def _make_plan(factory) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p


async def _make_platform_user(factory) -> PlatformUser:
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        u = PlatformUser(
            email=f"u-{uuid.uuid4().hex[:8]}@test.example",
            full_name="Test Operator",
            is_active=True,
            is_superuser=True,
            created_at=now,
            updated_at=now,
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


async def _cleanup(factory) -> None:
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.tenants SET current_subscription_id = NULL, "
                "subscription_status = 'pending'"
            )
        )
        await s.execute(delete(Payment))
        await s.execute(delete(InvoiceLineItem))
        await s.execute(delete(Invoice))
        await s.execute(delete(Subscription))
        await s.execute(delete(SubscriptionPlan))
        await s.execute(delete(Tenant))
        await s.execute(delete(PlatformUser))
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.commit()


@pytest.fixture
async def factory(test_engine: AsyncEngine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def _setup_pending_payment(factory, plan, tenant, maker) -> uuid.UUID:
    """Create a subscription, invoice, and pending payment. Return payment_id."""
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(
            tenant_id=tenant.id, plan_id=plan.id
        )
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        inv = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = inv.id
    async with factory() as s:
        await _set_platform(s)
        pmt = await PaymentService(s).record(
            invoice_id=invoice_id,
            amount=Decimal("50000"),
            currency="UGX",
            payment_method="bank_transfer",
            recorded_by=maker.id,
            idempotency_key=f"exec-test-{uuid.uuid4().hex[:8]}",
        )
        await s.commit()
        return pmt.id


@pytest.mark.anyio
async def test_confirm_payment_executor_marks_invoice_paid(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    maker = await _make_platform_user(factory)
    payment_id = await _setup_pending_payment(factory, plan, tenant, maker)
    try:
        async with factory() as s:
            await _set_platform(s)
            result = await execute_confirm_payment(
                s,
                {"payment_id": str(payment_id)},
            )
            await s.commit()
            assert result["status"] == "confirmed"
            assert result["payment_id"] == str(payment_id)

        async with factory() as s:
            await _set_platform(s)
            pmt = await s.get(Payment, payment_id)
            assert pmt is not None
            assert pmt.status == "confirmed"
            inv = await s.get(Invoice, pmt.invoice_id)
            assert inv is not None
            assert inv.status == "paid"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_confirm_payment_executor_is_idempotent(factory) -> None:
    """Calling the executor twice with the same payload returns success
    the second time without re-applying."""
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    maker = await _make_platform_user(factory)
    payment_id = await _setup_pending_payment(factory, plan, tenant, maker)
    try:
        payload = {"payment_id": str(payment_id)}
        async with factory() as s:
            await _set_platform(s)
            await execute_confirm_payment(s, payload)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            second = await execute_confirm_payment(s, payload)
            await s.commit()
            assert second["status"] == "confirmed"
            assert second.get("idempotent") is True
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_void_invoice_executor_voids_invoice(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(
            tenant_id=tenant.id, plan_id=plan.id
        )
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        inv = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = inv.id
    try:
        async with factory() as s:
            await _set_platform(s)
            result = await execute_void_invoice(
                s,
                {
                    "invoice_id": str(invoice_id),
                    "reason": "duplicate issuance",
                },
            )
            await s.commit()
            assert result["status"] == "void"

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Invoice, invoice_id)
            assert refreshed is not None
            assert refreshed.status == "void"
            assert refreshed.void_reason == "duplicate issuance"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_void_invoice_executor_is_idempotent(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(
            tenant_id=tenant.id, plan_id=plan.id
        )
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        inv = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = inv.id
    try:
        payload = {"invoice_id": str(invoice_id), "reason": "x"}
        async with factory() as s:
            await _set_platform(s)
            await execute_void_invoice(s, payload)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            result = await execute_void_invoice(s, payload)
            await s.commit()
            assert result["status"] == "void"
            assert result.get("idempotent") is True
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancel_subscription_executor_hard_cancels(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(
            tenant_id=tenant.id, plan_id=plan.id
        )
        await s.commit()
        sub_id = sub.id
    try:
        async with factory() as s:
            await _set_platform(s)
            result = await execute_cancel_subscription(
                s,
                {
                    "subscription_id": str(sub_id),
                    "reason": "tenant requested",
                },
            )
            await s.commit()
            assert result["status"] == "cancelled"

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Subscription, sub_id)
            assert refreshed is not None
            assert refreshed.status == "cancelled"
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "cancelled"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancel_subscription_executor_is_idempotent(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(
            tenant_id=tenant.id, plan_id=plan.id
        )
        await s.commit()
        sub_id = sub.id
    try:
        payload = {"subscription_id": str(sub_id), "reason": "x"}
        async with factory() as s:
            await _set_platform(s)
            await execute_cancel_subscription(s, payload)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            result = await execute_cancel_subscription(s, payload)
            await s.commit()
            assert result["status"] == "cancelled"
            assert result.get("idempotent") is True
    finally:
        await _cleanup(factory)
