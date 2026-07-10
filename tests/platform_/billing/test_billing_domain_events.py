"""Billing domain events for the notifications consumer (increment 2)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.outbox.models import PlatformOutboxEvent
from app.platform_.billing.models import (
    Invoice,
    InvoiceLineItem,
    Payment,
    Subscription,
    SubscriptionPlan,
)
from app.platform_.billing.services import InvoiceService, SubscriptionService
from app.platform_.models import Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


@pytest.fixture
async def factory(test_engine: AsyncEngine):  # noqa: ANN201
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    yield maker
    async with maker() as s:
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
        await s.execute(
            text("DELETE FROM platform.tenants WHERE slug LIKE 'bde-%'")
        )
        await s.execute(
            text(
                "DELETE FROM platform.outbox_events WHERE event_type IN "
                "('BillingInvoiceIssued', 'BillingInvoiceOverdue', "
                "'BillingSubscriptionSuspended')"
            )
        )
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.commit()


async def _seed_subscription(factory) -> tuple[uuid.UUID, uuid.UUID]:  # noqa: ANN001
    """Returns (tenant_id, subscription_id) with an assigned plan."""
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        tenant = Tenant(
            slug=f"bde-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_bde_{uuid.uuid4().hex[:8]}",
            name="BDE Tenant",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        plan = SubscriptionPlan(
            code=f"bde-plan-{uuid.uuid4().hex[:8]}",
            name="BDE Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
        )
        s.add_all([tenant, plan])
        await s.commit()
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        return tenant.id, sub.id


async def _events(factory, event_type: str) -> list[PlatformOutboxEvent]:  # noqa: ANN001
    async with factory() as s:
        await _set_platform(s)
        return list(
            (
                await s.execute(
                    select(PlatformOutboxEvent).where(
                        PlatformOutboxEvent.event_type == event_type
                    )
                )
            ).scalars()
        )


async def test_generate_invoice_publishes_issued_event_once(factory) -> None:  # noqa: ANN001
    tenant_id, sub_id = await _seed_subscription(factory)
    async with factory() as s:
        await _set_platform(s)
        svc = InvoiceService(s)
        invoice = await svc.generate_for_subscription(subscription_id=sub_id)
        await s.commit()
        # Idempotent re-generate: same invoice, no second event.
        again = await svc.generate_for_subscription(subscription_id=sub_id)
        await s.commit()
    assert again.id == invoice.id
    events = await _events(factory, "BillingInvoiceIssued")
    assert len(events) == 1
    payload = events[0].payload
    assert payload["invoice_id"] == str(invoice.id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["invoice_number"] == invoice.invoice_number
    assert set(payload) >= {"amount_total", "currency", "due_at"}


async def test_mark_overdue_batch_publishes_per_invoice(factory) -> None:  # noqa: ANN001
    tenant_id, sub_id = await _seed_subscription(factory)
    async with factory() as s:
        await _set_platform(s)
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.execute(
            text(
                "UPDATE platform.invoices SET due_at = now()::date - 10 "
                "WHERE id = :i"
            ),
            {"i": str(invoice.id)},
        )
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        count = await InvoiceService(s).mark_overdue_batch()
        await s.commit()
    assert count == 1
    events = await _events(factory, "BillingInvoiceOverdue")
    assert len(events) == 1
    payload = events[0].payload
    assert payload["invoice_id"] == str(invoice.id)
    assert payload["tenant_id"] == str(tenant_id)
    assert "amount_outstanding" in payload


async def test_transition_to_suspended_publishes_event(factory) -> None:  # noqa: ANN001
    tenant_id, sub_id = await _seed_subscription(factory)
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text("UPDATE platform.subscriptions SET status = 'past_due' WHERE id = :i"),
            {"i": str(sub_id)},
        )
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).transition_to_suspended(subscription_id=sub_id)
        await s.commit()
    events = await _events(factory, "BillingSubscriptionSuspended")
    assert len(events) == 1
    assert events[0].payload["subscription_id"] == str(sub_id)
    assert events[0].payload["tenant_id"] == str(tenant_id)
