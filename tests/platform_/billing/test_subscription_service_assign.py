"""SubscriptionService.assign() tests.

Uses the async_sessionmaker + commit pattern (not the platform_session
fixture) because AuditableMixin's after_insert hook conflicts with the
connection-bound rollback fixture. See SP01 test docstring for context.
"""
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

from app.platform_.billing.exceptions import (
    PlanInactive,
    SubscriptionConflict,
)
from app.platform_.billing.models import Subscription, SubscriptionPlan
from app.platform_.billing.services import SubscriptionService
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(factory: async_sessionmaker[AsyncSession]) -> Tenant:
    now = datetime.now(UTC)
    async with factory() as s:
        await _set_platform(s)
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
    billing_period: str = "monthly",
    is_active: bool = True,
) -> SubscriptionPlan:
    async with factory() as s:
        await _set_platform(s)
        p = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Test Plan",
            base_price=Decimal("50000.0000"),
            billing_period=billing_period,
            trial_period_days=trial_period_days,
            is_active=is_active,
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


@pytest.mark.anyio
async def test_assign_active_for_no_trial_plan(factory) -> None:
    plan = await _make_plan(factory, trial_period_days=0, billing_period="monthly")
    tenant = await _make_tenant(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
            await s.commit()

            assert sub.status == "active"
            assert sub.current_period_end == sub.current_period_start + timedelta(days=30)

        async with factory() as s:
            await _set_platform(s)
            refreshed = await s.get(Tenant, tenant.id)
            assert refreshed is not None
            assert refreshed.subscription_status == "active"
            assert refreshed.current_subscription_id == sub.id
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_trialing_when_plan_has_trial(factory) -> None:
    plan = await _make_plan(factory, trial_period_days=14)
    tenant = await _make_tenant(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
            await s.commit()
            assert sub.status == "trialing"
            assert sub.current_period_end == sub.current_period_start + timedelta(days=14)

        async with factory() as s:
            await _set_platform(s)
            t = await s.get(Tenant, tenant.id)
            assert t is not None
            assert t.subscription_status == "trialing"
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_uses_start_date_override(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    custom_start = date(2027, 1, 15)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            sub = await svc.assign(
                tenant_id=tenant.id, plan_id=plan.id, start_date=custom_start
            )
            await s.commit()
            assert sub.current_period_start == custom_start
            assert sub.current_period_end == custom_start + timedelta(days=30)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_rejects_unknown_tenant(factory) -> None:
    plan = await _make_plan(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(ValueError, match="Tenant"):
                await svc.assign(tenant_id=uuid.uuid4(), plan_id=plan.id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_rejects_unknown_plan(factory) -> None:
    tenant = await _make_tenant(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(ValueError, match="SubscriptionPlan"):
                await svc.assign(tenant_id=tenant.id, plan_id=uuid.uuid4())
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_rejects_inactive_plan(factory) -> None:
    plan = await _make_plan(factory, is_active=False)
    tenant = await _make_tenant(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(PlanInactive, match="not active"):
                await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_assign_raises_conflict_on_existing_live_sub(factory) -> None:
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory)
    try:
        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
            await s.commit()

        async with factory() as s:
            await _set_platform(s)
            svc = SubscriptionService(s)
            with pytest.raises(SubscriptionConflict):
                await svc.assign(tenant_id=tenant.id, plan_id=plan.id)
    finally:
        await _cleanup(factory)
