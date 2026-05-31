"""InvoiceService.generate_for_subscription() tests."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.exceptions import InvoiceConflict
from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Payment,
    Subscription,
    SubscriptionPlan,
)
from app.platform_.billing.services import (
    InvoiceService,
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


async def _make_plan(factory, *, base_price: Decimal = Decimal("50000.0000")) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=base_price,
            billing_period="monthly",
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p


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


async def _assigned_subscription(factory, plan, tenant) -> uuid.UUID:
    async with factory() as s:
        await _set_platform(s)
        svc = SubscriptionService(s)
        sub = await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        return sub.id


@pytest.mark.anyio
async def test_generate_creates_issued_invoice_with_base_line(factory) -> None:
    plan = await _make_plan(factory, base_price=Decimal("60000"))
    tenant = await _make_tenant(factory)
    sub_id = await _assigned_subscription(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            inv = await svc.generate_for_subscription(subscription_id=sub_id)
            await s.commit()

            assert inv.status == "issued"
            assert inv.amount_subtotal == Decimal("60000")
            assert inv.amount_total == Decimal("60000")
            assert inv.amount_paid == Decimal("0")
            assert inv.due_at == inv.billing_period_start + timedelta(days=7)
            assert inv.invoice_number.startswith("INV-")

        async with factory() as s:
            await _set_platform(s)
            lines = list(
                (
                    await s.execute(
                        select(InvoiceLineItem).where(
                            InvoiceLineItem.invoice_id == inv.id
                        )
                    )
                ).scalars().all()
            )
            assert len(lines) == 1
            assert lines[0].description == "Base subscription (monthly)"
            assert lines[0].quantity == 1
            assert lines[0].unit_price == Decimal("60000")
            assert lines[0].line_order == 1
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_generate_is_idempotent_per_period(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assigned_subscription(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            a = await svc.generate_for_subscription(subscription_id=sub_id)
            await s.commit()
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            b = await svc.generate_for_subscription(subscription_id=sub_id)
            await s.commit()
        assert a.id == b.id  # idempotent
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_generate_rejects_cancelled_subscription(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assigned_subscription(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            sub = await s.get(Subscription, sub_id)
            assert sub is not None
            sub.status = "cancelled"
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            with pytest.raises(InvoiceConflict, match="cancelled"):
                await svc.generate_for_subscription(subscription_id=sub_id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_generate_rejects_unknown_subscription(factory) -> None:
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = InvoiceService(s)
            with pytest.raises(ValueError, match="Subscription"):
                await svc.generate_for_subscription(subscription_id=uuid.uuid4())
    finally:
        await _cleanup(factory)
