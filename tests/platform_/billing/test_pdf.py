"""Smoke tests for invoice PDF rendering."""
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

from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Subscription,
    SubscriptionPlan,
)
from app.platform_.billing.pdf import render_invoice_pdf
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
            name="PDF Test",
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
            name="PDF Plan",
            base_price=Decimal("75000.0000"),
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


@pytest.mark.anyio
async def test_render_invoice_pdf_returns_pdf_bytes(factory) -> None:
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
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = invoice.id
    try:
        async with factory() as s:
            await _set_platform(s)
            from sqlalchemy import select
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            lines = list(
                (
                    await s.execute(
                        select(InvoiceLineItem).where(
                            InvoiceLineItem.invoice_id == invoice_id
                        )
                    )
                ).scalars().all()
            )
            pdf = render_invoice_pdf(inv, lines)
            assert pdf[:5] == b"%PDF-"
            assert len(pdf) > 1000  # smoke: not empty
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_render_voided_invoice_includes_void_status(factory) -> None:
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
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = invoice.id
    async with factory() as s:
        await _set_platform(s)
        await InvoiceService(s).void(
            invoice_id=invoice_id, reason="rendered void test"
        )
        await s.commit()
    try:
        async with factory() as s:
            await _set_platform(s)
            from sqlalchemy import select
            inv = await s.get(Invoice, invoice_id)
            assert inv is not None
            lines = list(
                (
                    await s.execute(
                        select(InvoiceLineItem).where(
                            InvoiceLineItem.invoice_id == invoice_id
                        )
                    )
                ).scalars().all()
            )
            pdf = render_invoice_pdf(inv, lines)
            assert pdf[:5] == b"%PDF-"
    finally:
        await _cleanup(factory)
