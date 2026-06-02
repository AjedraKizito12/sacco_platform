"""Unit tests for billing beat tasks.

Each test calls the underscore-prefixed async helper directly (not the
Celery wrapper), so we can run inside the test event loop without
asyncio.run.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.beat import (
    _run_assess_subscription_state,
    _run_generate_next_period_invoices,
    _run_mark_overdue_invoices,
    _run_send_invoice_reminders,
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
    SubscriptionService,
)
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(factory: async_sessionmaker[AsyncSession]) -> Tenant:
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Beat Test",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t


async def _make_plan(
    factory: async_sessionmaker[AsyncSession],
    *,
    grace_period_days: int = 30,
) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Beat Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            grace_period_days=grace_period_days,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
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
        await s.execute(text("DELETE FROM platform.outbox_events"))
        await s.commit()


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(test_engine, expire_on_commit=False)


# IMPORTANT: The beat helpers create their own engine via create_async_engine
# (using settings.database_url). For tests we need to patch
# `app.platform_.billing.beat.create_async_engine` to return test_engine.


@pytest.fixture
def patched_beat(test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the beat module's engine constructor to return test_engine
    instead of creating a new one. The test_engine has NullPool which
    avoids event-loop conflicts in the test suite.
    """

    class _Wrapper:
        def __init__(self, engine: AsyncEngine) -> None:
            self._engine = engine

        async def dispose(self) -> None:
            # Don't actually dispose — the test session owns the engine
            pass

        def __getattr__(self, name: str) -> object:
            return getattr(self._engine, name)

    wrapper = _Wrapper(test_engine)
    monkeypatch.setattr(
        "app.platform_.billing.beat.create_async_engine",
        lambda *a, **kw: wrapper,
    )


# ── assess_subscription_state ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_assess_transitions_expired_active_to_past_due(
    factory: async_sessionmaker[AsyncSession], patched_beat: None
) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id
    # Force the subscription's period_end into the past
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.subscriptions SET current_period_end = :pe WHERE id = :id"
            ),
            {"pe": date.today() - timedelta(days=1), "id": sub_id},
        )
        await s.commit()

    try:
        counts = await _run_assess_subscription_state()
        assert counts["past_due"] >= 1

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Subscription, sub_id)
            assert refreshed is not None
            assert refreshed.status == "past_due"
            assert refreshed.grace_period_ends_at is not None
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assess_transitions_past_due_with_expired_grace_to_suspended(
    factory: async_sessionmaker[AsyncSession], patched_beat: None
) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id

    # Force into past_due with an expired grace period
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.subscriptions SET status = 'past_due', "
                "grace_period_ends_at = :gpe WHERE id = :id"
            ),
            {"gpe": date.today() - timedelta(days=1), "id": sub_id},
        )
        await s.execute(
            text(
                "UPDATE platform.tenants SET subscription_status = 'past_due' WHERE id = :id"
            ),
            {"id": str(tenant.id)},
        )
        await s.commit()

    try:
        counts = await _run_assess_subscription_state()
        assert counts["suspended"] >= 1

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Subscription, sub_id)
            assert refreshed is not None
            assert refreshed.status == "suspended"
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "suspended"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assess_is_idempotent(
    factory: async_sessionmaker[AsyncSession], patched_beat: None
) -> None:
    """Running assess twice on the same day should not double-transition."""
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id

    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.subscriptions SET current_period_end = :pe WHERE id = :id"
            ),
            {"pe": date.today() - timedelta(days=1), "id": sub_id},
        )
        await s.commit()

    try:
        first = await _run_assess_subscription_state()
        assert first["past_due"] >= 1
        # Second run: subscription is now past_due, not active. Should not transition again.
        second = await _run_assess_subscription_state()
        # past_due count should be 0 in the second run (already transitioned)
        # suspended count should be 0 (grace not yet expired)
        assert second["past_due"] == 0
    finally:
        await _cleanup(factory)


# ── generate_next_period_invoices ────────────────────────────────────────────


@pytest.mark.anyio
async def test_generate_creates_invoice_for_subscription_due_today(
    factory: async_sessionmaker[AsyncSession], patched_beat: None
) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id

    # Set next_billing_date to today
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.subscriptions SET next_billing_date = :nbd WHERE id = :id"
            ),
            {"nbd": date.today(), "id": sub_id},
        )
        await s.commit()

    try:
        counts = await _run_generate_next_period_invoices()
        assert counts["generated"] == 1

        async with factory() as s:
            await _set_platform(s)
            invoices = list(
                (
                    await s.execute(
                        select(Invoice).where(Invoice.subscription_id == sub_id)
                    )
                ).scalars().all()
            )
            assert len(invoices) >= 1
            refreshed = await s.get(Subscription, sub_id)
            assert refreshed is not None
            assert refreshed.next_billing_date == date.today() + timedelta(days=30)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_generate_skips_subscriptions_not_due(
    factory: async_sessionmaker[AsyncSession], patched_beat: None
) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        # next_billing_date defaults to period_end, which is today + 30
        await s.commit()
    try:
        counts = await _run_generate_next_period_invoices()
        assert counts["generated"] == 0
    finally:
        await _cleanup(factory)


# ── send_invoice_reminders ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_reminders_emit_outbox_event_for_invoice_due_in_7_days(
    factory: async_sessionmaker[AsyncSession], patched_beat: None
) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = invoice.id

    # Force the invoice due_at to today + 7 (T-7 reminder)
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text("UPDATE platform.invoices SET due_at = :da WHERE id = :id"),
            {"da": date.today() + timedelta(days=7), "id": invoice_id},
        )
        await s.commit()

    try:
        counts = await _run_send_invoice_reminders()
        assert counts["window_-7"] == 1

        async with factory() as s:
            await _set_platform(s)
            outbox_count = await s.scalar(
                text(
                    "SELECT count(*) FROM platform.outbox_events "
                    "WHERE event_type = 'BillingInvoiceReminderDue' "
                    "AND aggregate_id = :iid"
                ),
                {"iid": str(invoice_id)},
            )
            assert outbox_count == 1
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_reminders_skip_paid_invoices(
    factory: async_sessionmaker[AsyncSession], patched_beat: None
) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        await s.commit()
        invoice_id = invoice.id

    # Mark fully paid + due in 7 days
    async with factory() as s:
        await _set_platform(s)
        await s.execute(
            text(
                "UPDATE platform.invoices SET due_at = :da, amount_paid = amount_total, status = 'paid' "
                "WHERE id = :id"
            ),
            {"da": date.today() + timedelta(days=7), "id": invoice_id},
        )
        await s.commit()

    try:
        counts = await _run_send_invoice_reminders()
        # paid invoice not in {issued, partial, overdue} → no event
        assert counts["window_-7"] == 0
    finally:
        await _cleanup(factory)


# ── mark_overdue_invoices ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_mark_overdue_transitions_eligible_invoices(
    factory: async_sessionmaker[AsyncSession], patched_beat: None
) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        # Force due_at into the past
        invoice.due_at = date.today() - timedelta(days=1)
        await s.commit()
        invoice_id = invoice.id

    try:
        counts = await _run_mark_overdue_invoices()
        assert counts["transitioned"] >= 1

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Invoice, invoice_id)
            assert refreshed is not None
            assert refreshed.status == "overdue"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_mark_overdue_idempotent_on_already_overdue(
    factory: async_sessionmaker[AsyncSession], patched_beat: None
) -> None:
    """Running mark_overdue twice doesn't double-transition (set-based UPDATE)."""
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    async with factory() as s:
        await _set_platform(s)
        sub = await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        sub_id = sub.id
    async with factory() as s:
        await _set_platform(s)
        invoice = await InvoiceService(s).generate_for_subscription(
            subscription_id=sub_id
        )
        invoice.due_at = date.today() - timedelta(days=1)
        await s.commit()

    try:
        first = await _run_mark_overdue_invoices()
        assert first["transitioned"] == 1
        second = await _run_mark_overdue_invoices()
        # Invoice is now 'overdue' — not in eligible set → 0 transitioned
        assert second["transitioned"] == 0
    finally:
        await _cleanup(factory)
