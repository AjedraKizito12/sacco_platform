"""Tests for the daily offboarding transition beat sweeps."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform_.models import Tenant, TenantLifecycleEvent
from app.platform_.tenants.beat import _run_sweep


async def _seed_tenant(
    factory: async_sessionmaker[AsyncSession], **overrides: object
) -> uuid.UUID:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=f"t-{uuid.uuid4().hex[:8]}",
            schema_name=f"tenant_t_{uuid.uuid4().hex[:8]}",
            name="Beat Co",
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


async def _state(factory: async_sessionmaker[AsyncSession], tid: uuid.UUID) -> str:
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = await s.get(Tenant, tid)
        assert t is not None
        return t.lifecycle_state


async def _cleanup(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.tenant_lifecycle_events"))
        await s.execute(
            text("DELETE FROM platform.outbox_events "
                 "WHERE event_type LIKE 'TenantOffboarding%'")
        )
        await s.execute(text("DELETE FROM platform.tenants"))


async def test_cancelled_to_read_only_sweep(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    due = await _seed_tenant(
        factory,
        lifecycle_state="cancelled",
        cancelled_at=datetime.now(UTC) - timedelta(days=8),
    )
    fresh = await _seed_tenant(
        factory,
        lifecycle_state="cancelled",
        cancelled_at=datetime.now(UTC) - timedelta(days=1),
    )
    try:
        ids = await _run_sweep(test_engine, "sweep_cancelled_to_read_only")
        assert due in ids
        assert fresh not in ids
        assert await _state(factory, due) == "read_only"
        assert await _state(factory, fresh) == "cancelled"
    finally:
        await _cleanup(factory)


async def test_read_only_to_archived_sweep(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    due = await _seed_tenant(
        factory,
        lifecycle_state="read_only",
        read_only_at=datetime.now(UTC) - timedelta(days=90),
    )
    held = await _seed_tenant(
        factory,
        lifecycle_state="read_only",
        read_only_at=datetime.now(UTC) - timedelta(days=90),
        retention_hold_until=datetime.now(UTC) + timedelta(days=30),
    )
    try:
        ids = await _run_sweep(test_engine, "sweep_read_only_to_archived")
        assert due in ids
        assert held not in ids
        assert await _state(factory, due) == "archived"
        assert await _state(factory, held) == "read_only"
    finally:
        await _cleanup(factory)


async def test_archived_to_hard_deleted_sweep(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    due = await _seed_tenant(
        factory,
        lifecycle_state="archived",
        archived_at=datetime.now(UTC) - timedelta(days=2600),
    )
    try:
        ids = await _run_sweep(test_engine, "sweep_archived_to_hard_deleted")
        assert due in ids
        assert await _state(factory, due) == "hard_deleted"
        # A lifecycle event was recorded for the transition.
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            evts = list(
                (
                    await s.execute(
                        TenantLifecycleEvent.__table__.select().where(
                            TenantLifecycleEvent.tenant_id == due
                        )
                    )
                ).all()
            )
        assert any(e.to_state == "hard_deleted" for e in evts)
    finally:
        await _cleanup(factory)
