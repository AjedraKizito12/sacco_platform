"""SubscriptionService.cancel() + reactivate() tests."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.exceptions import InvalidTransition
from app.platform_.billing.models import Subscription, SubscriptionPlan
from app.platform_.billing.services import SubscriptionService
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(factory: async_sessionmaker[AsyncSession]) -> Tenant:
    """COPY the helper from test_subscription_service_assign.py — including
    the created_at/updated_at fix that the SP02-3 implementer added."""
    from datetime import UTC, datetime
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


async def _make_plan(
    factory: async_sessionmaker[AsyncSession],
    *,
    trial_period_days: int = 0,
) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            trial_period_days=trial_period_days,
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
        await s.execute(delete(Subscription))
        await s.execute(delete(SubscriptionPlan))
        await s.execute(delete(Tenant))
        await s.execute(delete(PlatformUser))
        await s.execute(text("DELETE FROM platform.audit_log"))
        await s.commit()


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def _assign(factory, plan, tenant) -> uuid.UUID:
    async with factory() as s:
        await _set_platform(s)
        svc = SubscriptionService(s)
        sub = await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
        return sub.id


@pytest.mark.anyio
async def test_cancel_at_period_end_marks_but_keeps_status(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.cancel(
                subscription_id=sub_id,
                reason="not needed",
                cancel_at_period_end=True,
            )
            await s.commit()
            assert sub.status == "active"  # unchanged
            assert sub.cancelled_at is not None
            assert sub.cancellation_reason == "not needed"

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "active"  # unchanged
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancel_immediate_transitions_and_syncs_tenant(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.cancel(
                subscription_id=sub_id,
                reason="hard cancel",
                cancel_at_period_end=False,
            )
            await s.commit()
            assert sub.status == "cancelled"
            assert sub.cancelled_at is not None

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "cancelled"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancel_rejects_already_cancelled(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            await svc.cancel(
                subscription_id=sub_id, reason="x", cancel_at_period_end=False
            )
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(InvalidTransition):
                await svc.cancel(
                    subscription_id=sub_id,
                    reason="again",
                    cancel_at_period_end=False,
                )
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_cancel_rejects_unknown_subscription(factory) -> None:
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(ValueError, match="Subscription"):
                await svc.cancel(
                    subscription_id=uuid.uuid4(),
                    reason="x",
                )
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_reactivate_from_suspended_resets_period(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        # Force the subscription into 'suspended'
        async with factory() as s:
            await _set_platform(s)
            sub = await s.get(Subscription, sub_id)
            assert sub is not None
            sub.status = "suspended"
            sub.grace_period_ends_at = date.today() - timedelta(days=1)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            t.subscription_status = "suspended"
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.reactivate(subscription_id=sub_id)
            await s.commit()
            assert sub.status == "active"
            assert sub.grace_period_ends_at is None
            assert sub.current_period_end == date.today() + timedelta(days=30)

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "active"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_reactivate_rejects_from_active(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(InvalidTransition):
                await svc.reactivate(subscription_id=sub_id)
    finally:
        await _cleanup(factory)
