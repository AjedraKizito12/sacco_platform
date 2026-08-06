"""Unit tests for OffboardingService — the tenant lifecycle state machine."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform_.models import PlatformUser, Tenant
from app.platform_.tenants.offboarding_service import (
    OffboardingError,
    OffboardingService,
)


async def _seed_actor(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        u = PlatformUser(
            email=f"a-{uuid.uuid4().hex[:6]}@test.example",
            full_name="Actor",
            is_active=True,
            is_superuser=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(u)
        await s.flush()
        return u.id


async def _seed_tenant(
    factory: async_sessionmaker[AsyncSession], **overrides: object
) -> uuid.UUID:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Offboard Co",
            status="active",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        for k, v in overrides.items():
            setattr(t, k, v)
        s.add(t)
        await s.flush()
        return t.id


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.tenant_lifecycle_events"))
        await s.execute(text("DELETE FROM platform.tenants"))
        await s.execute(text("DELETE FROM platform.platform_users"))


async def test_cancel_from_active_sets_state_and_event(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor_id = await _seed_actor(factory)
    tid = await _seed_tenant(factory)
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = OffboardingService(s)
            t = await svc.cancel(tenant_id=tid, actor_id=actor_id, reason="customer left")
            await s.commit()
            assert t.lifecycle_state == "cancelled"
            assert t.cancelled_at is not None
            events = await svc.lifecycle_events(tenant_id=tid)
            assert events[-1].to_state == "cancelled"
            assert events[-1].from_state == "active"
            assert events[-1].reason == "customer left"
    finally:
        await _cleanup(factory)


async def test_cancel_twice_rejected(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor_id = await _seed_actor(factory)
    tid = await _seed_tenant(factory)
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = OffboardingService(s)
            await svc.cancel(tenant_id=tid, actor_id=actor_id, reason="x")
            await s.commit()
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = OffboardingService(s)
            with pytest.raises(OffboardingError):
                await svc.cancel(tenant_id=tid, actor_id=actor_id, reason="x")
    finally:
        await _cleanup(factory)


async def test_restore_from_cancelled(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor_id = await _seed_actor(factory)
    tid = await _seed_tenant(
        factory, lifecycle_state="cancelled", cancelled_at=datetime.now(UTC)
    )
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = OffboardingService(s)
            t = await svc.restore(tenant_id=tid, actor_id=actor_id)
            await s.commit()
            assert t.lifecycle_state == "active"
            assert t.cancelled_at is None
            events = await svc.lifecycle_events(tenant_id=tid)
            assert events[-1].to_state == "active"
    finally:
        await _cleanup(factory)


async def test_restore_blocked_after_physical_archive(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor_id = await _seed_actor(factory)
    tid = await _seed_tenant(
        factory, lifecycle_state="archived", archive_checksum="sha256:abc"
    )
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = OffboardingService(s)
            with pytest.raises(OffboardingError):
                await svc.restore(tenant_id=tid, actor_id=actor_id)
    finally:
        await _cleanup(factory)


async def test_extend_retention(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    actor_id = await _seed_actor(factory)
    tid = await _seed_tenant(factory, lifecycle_state="read_only")
    hold = datetime.now(UTC) + timedelta(days=30)
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = OffboardingService(s)
            t = await svc.extend_retention(
                tenant_id=tid, actor_id=actor_id, hold_until=hold
            )
            await s.commit()
            assert t.retention_hold_until is not None
            events = await svc.lifecycle_events(tenant_id=tid)
            assert events[-1].from_state == events[-1].to_state == "read_only"
    finally:
        await _cleanup(factory)


async def test_sweep_cancelled_to_read_only_respects_window(
    test_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    # Due: cancelled 8 days ago (> 7-day window).
    due = await _seed_tenant(
        factory,
        lifecycle_state="cancelled",
        cancelled_at=datetime.now(UTC) - timedelta(days=8),
    )
    # Not due: cancelled 2 days ago.
    fresh = await _seed_tenant(
        factory,
        lifecycle_state="cancelled",
        cancelled_at=datetime.now(UTC) - timedelta(days=2),
    )
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = OffboardingService(s)
            ids = await svc.sweep_cancelled_to_read_only(now=datetime.now(UTC))
            await s.commit()
            assert due in ids
            assert fresh not in ids
            evts = await svc.lifecycle_events(tenant_id=due)
            assert evts[-1].to_state == "read_only"
    finally:
        await _cleanup(factory)


async def test_sweep_to_archived_blocked_by_hold(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    tid = await _seed_tenant(
        factory,
        lifecycle_state="read_only",
        read_only_at=datetime.now(UTC) - timedelta(days=90),
        retention_hold_until=datetime.now(UTC) + timedelta(days=30),
    )
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = OffboardingService(s)
            ids = await svc.sweep_read_only_to_archived(now=datetime.now(UTC))
            await s.commit()
            assert tid not in ids
    finally:
        await _cleanup(factory)


async def test_sweep_archived_to_hard_deleted(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    tid = await _seed_tenant(
        factory,
        lifecycle_state="archived",
        archived_at=datetime.now(UTC) - timedelta(days=2600),
    )
    try:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            svc = OffboardingService(s)
            ids = await svc.sweep_archived_to_hard_deleted(now=datetime.now(UTC))
            await s.commit()
            assert tid in ids
            evts = await svc.lifecycle_events(tenant_id=tid)
            assert evts[-1].to_state == "hard_deleted"
    finally:
        await _cleanup(factory)
