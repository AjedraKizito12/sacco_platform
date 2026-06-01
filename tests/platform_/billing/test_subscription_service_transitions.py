"""SubscriptionService transition tests — past_due and suspended."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
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
    grace_period_days: int = 30,
    trial_period_days: int = 0,
) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            grace_period_days=grace_period_days,
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
async def test_past_due_from_active_succeeds_and_sets_grace(factory) -> None:
    plan = await _make_plan(factory, grace_period_days=14)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.transition_to_past_due(subscription_id=sub_id)
            await s.commit()
            assert sub.status == "past_due"
            assert sub.grace_period_ends_at == date.today() + timedelta(days=14)

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "past_due"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_past_due_rejects_when_already_past_due(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            await svc.transition_to_past_due(subscription_id=sub_id)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(InvalidTransition):
                await svc.transition_to_past_due(subscription_id=sub_id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_suspended_from_past_due_succeeds(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            await svc.transition_to_past_due(subscription_id=sub_id)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.transition_to_suspended(subscription_id=sub_id)
            await s.commit()
            assert sub.status == "suspended"

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "suspended"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_suspended_rejects_from_active(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(InvalidTransition):
                await svc.transition_to_suspended(subscription_id=sub_id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_past_due_from_trialing_succeeds(factory) -> None:
    """Trialing subscriptions whose trial ends without conversion go past_due."""
    plan = await _make_plan(factory, trial_period_days=7)
    tenant = await _make_tenant(factory)
    sub_id = await _assign(factory, plan, tenant)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.transition_to_past_due(subscription_id=sub_id)
            await s.commit()
            assert sub.status == "past_due"
    finally:
        await _cleanup(factory)
