"""Subscription gate tests — verifies _check_subscription_gate maps each
subscription status to the correct HTTPException (or allow).
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

import app.core.db as _db_module
from app.core.db import _check_subscription_gate
from app.platform_.billing.models import Subscription, SubscriptionPlan
from app.platform_.billing.services import SubscriptionService
from app.platform_.models import PlatformUser, Tenant


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


async def _make_tenant(factory: async_sessionmaker[AsyncSession], slug: str) -> Tenant:
    async with factory() as s:
        await _set_platform(s)
        now = datetime.now(UTC)
        t = Tenant(
            slug=slug,
            schema_name=f"tenant_{slug.replace('-', '_')}",
            name="Gate Test",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t


async def _make_plan(factory: async_sessionmaker[AsyncSession]) -> SubscriptionPlan:
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
    """Return a session factory bound to test_engine.

    Also patches app.core.db.engine so that _check_subscription_gate uses
    the test database rather than the production engine.  Safe because
    test_engine is session-scoped and tests run sequentially.
    """
    _db_module.engine = test_engine
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_gate_allows_pending_tenant(factory: async_sessionmaker[AsyncSession]) -> None:
    slug = f"sg-pending-{uuid.uuid4().hex[:6]}"
    await _make_tenant(factory, slug)
    try:
        # No assertion needed — allow path returns None
        await _check_subscription_gate(slug)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_allows_active_tenant(factory: async_sessionmaker[AsyncSession]) -> None:
    slug = f"sg-active-{uuid.uuid4().hex[:6]}"
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    try:
        await _check_subscription_gate(slug)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_allows_trialing_tenant(factory: async_sessionmaker[AsyncSession]) -> None:
    slug = f"sg-trial-{uuid.uuid4().hex[:6]}"
    # Trialing requires a plan with trial_period_days > 0
    async with factory() as s:
        await _set_platform(s)
        plan = SubscriptionPlan(
            code=f"plan-{uuid.uuid4().hex[:8]}",
            name="Trial Plan",
            base_price=Decimal("50000.0000"),
            billing_period="monthly",
            trial_period_days=14,
        )
        s.add(plan)
        await s.commit()
        await s.refresh(plan)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    try:
        await _check_subscription_gate(slug)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_allows_past_due_within_grace(factory: async_sessionmaker[AsyncSession]) -> None:
    slug = f"sg-pd-grace-{uuid.uuid4().hex[:6]}"
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).transition_to_past_due(
            subscription_id=(
                await s.execute(
                    text("SELECT id FROM platform.subscriptions LIMIT 1")
                )
            ).scalar_one()
        )
        await s.commit()
    try:
        # grace_period_ends_at defaults to today+30 — well within grace
        await _check_subscription_gate(slug)
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_blocks_past_due_past_grace_with_402(factory: async_sessionmaker[AsyncSession]) -> None:
    slug = f"sg-pd-exp-{uuid.uuid4().hex[:6]}"
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        sub_id = (
            await s.execute(text("SELECT id FROM platform.subscriptions LIMIT 1"))
        ).scalar_one()
        await SubscriptionService(s).transition_to_past_due(subscription_id=sub_id)
        # Force the grace period into the past
        await s.execute(
            text(
                "UPDATE platform.subscriptions SET grace_period_ends_at = :gpe "
                "WHERE id = :id"
            ),
            {"gpe": date.today() - timedelta(days=1), "id": sub_id},
        )
        await s.commit()
    try:
        with pytest.raises(HTTPException) as exc:
            await _check_subscription_gate(slug)
        assert exc.value.status_code == 402
        assert "grace" in str(exc.value.detail).lower()
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_blocks_suspended_with_403(factory: async_sessionmaker[AsyncSession]) -> None:
    slug = f"sg-susp-{uuid.uuid4().hex[:6]}"
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        sub_id = (
            await s.execute(text("SELECT id FROM platform.subscriptions LIMIT 1"))
        ).scalar_one()
        svc = SubscriptionService(s)
        await svc.transition_to_past_due(subscription_id=sub_id)
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        sub_id = (
            await s.execute(text("SELECT id FROM platform.subscriptions LIMIT 1"))
        ).scalar_one()
        await SubscriptionService(s).transition_to_suspended(subscription_id=sub_id)
        await s.commit()
    try:
        with pytest.raises(HTTPException) as exc:
            await _check_subscription_gate(slug)
        assert exc.value.status_code == 403
        assert "suspended" in str(exc.value.detail).lower()
    finally:
        await _cleanup(factory)


@pytest.mark.anyio
async def test_gate_blocks_cancelled_with_403(factory: async_sessionmaker[AsyncSession]) -> None:
    slug = f"sg-cnx-{uuid.uuid4().hex[:6]}"
    plan = await _make_plan(factory)
    tenant = await _make_tenant(factory, slug)
    async with factory() as s:
        await _set_platform(s)
        await SubscriptionService(s).assign(tenant_id=tenant.id, plan_id=plan.id)
        await s.commit()
    async with factory() as s:
        await _set_platform(s)
        sub_id = (
            await s.execute(text("SELECT id FROM platform.subscriptions LIMIT 1"))
        ).scalar_one()
        await SubscriptionService(s).cancel(
            subscription_id=sub_id,
            reason="test",
            cancel_at_period_end=False,
        )
        await s.commit()
    try:
        with pytest.raises(HTTPException) as exc:
            await _check_subscription_gate(slug)
        assert exc.value.status_code == 403
        assert "cancelled" in str(exc.value.detail).lower()
    finally:
        await _cleanup(factory)
