"""Integration tests for the tenant provisioning workflow."""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform_.models import Tenant
from app.platform_.provisioning.steps import (
    run_create_schema,
    run_seed_defaults_step,
)
from app.platform_.provisioning.tasks import _execute_steps, _run_provision

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _insert_tenant(
    factory: async_sessionmaker[AsyncSession],
    *,
    slug: str,
    status: str = "pending",
    failed_step: str | None = None,
) -> Tenant:
    schema_name = f"tenant_{slug.replace('-', '_')}"
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        t = Tenant(
            slug=slug,
            schema_name=schema_name,
            name=f"Test {slug}",
            status=status,
            failed_step=failed_step,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        s.add(t)
    return t


async def _delete_tenant(factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID) -> None:
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        result = await s.execute(select(Tenant).where(Tenant.id == tenant_id))
        t = result.scalar_one_or_none()
        if t:
            await s.delete(t)


async def _drop_schema_if_exists(engine: AsyncEngine, schema_name: str) -> None:
    async with engine.connect() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))  # noqa: S608
        await conn.commit()


# ── create_schema step ────────────────────────────────────────────────────────


async def test_create_schema_step_idempotent(test_engine: AsyncEngine) -> None:
    schema = "tenant_prov_test_1"
    try:
        await run_create_schema(test_engine, schema)
        await run_create_schema(test_engine, schema)  # second call — no error
        async with test_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata"
                    " WHERE schema_name = :s"
                ),
                {"s": schema},
            )
            assert result.scalar_one_or_none() == schema
    finally:
        await _drop_schema_if_exists(test_engine, schema)


# ── Full workflow state transitions ───────────────────────────────────────────


async def test_full_provision_sets_status_active(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    slug = f"prov-ok-{uuid.uuid4().hex[:8]}"
    tenant = await _insert_tenant(factory, slug=slug)

    with (
        patch("app.platform_.provisioning.steps.run_tenant_migrations"),
        patch("app.platform_.provisioning.steps.seed_defaults", new=AsyncMock()),
    ):
        await _execute_steps(test_engine, factory, tenant.id)

    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        updated = (
            await s.execute(select(Tenant).where(Tenant.id == tenant.id))
        ).scalar_one()

    assert updated.status == "active"
    assert updated.is_active is True
    assert updated.provisioning_completed_at is not None
    assert updated.failed_step is None

    await _delete_tenant(factory, tenant.id)
    await _drop_schema_if_exists(test_engine, updated.schema_name)


# ── Failure injection ─────────────────────────────────────────────────────────


async def test_failure_in_create_schema_marks_failed(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    slug = f"prov-fail-{uuid.uuid4().hex[:8]}"
    tenant = await _insert_tenant(factory, slug=slug)

    with patch(
        "app.platform_.provisioning.tasks.run_create_schema",
        new=AsyncMock(side_effect=RuntimeError("disk full")),
    ):
        await _execute_steps(test_engine, factory, tenant.id)

    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        updated = (
            await s.execute(select(Tenant).where(Tenant.id == tenant.id))
        ).scalar_one()

    assert updated.status == "failed"
    assert updated.failed_step == "create_schema"
    assert "disk full" in (updated.failure_reason or "")

    await _delete_tenant(factory, tenant.id)


async def test_failure_in_run_migrations_marks_correct_step(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    slug = f"prov-failmig-{uuid.uuid4().hex[:8]}"
    tenant = await _insert_tenant(factory, slug=slug)

    with (
        patch("app.platform_.provisioning.tasks.run_create_schema", new=AsyncMock()),
        patch(
            "app.platform_.provisioning.tasks.run_migrations_step",
            side_effect=RuntimeError("migration error"),
        ),
    ):
        await _execute_steps(test_engine, factory, tenant.id)

    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        updated = (
            await s.execute(select(Tenant).where(Tenant.id == tenant.id))
        ).scalar_one()

    assert updated.failed_step == "run_migrations"
    assert updated.status == "failed"

    await _delete_tenant(factory, tenant.id)
    await _drop_schema_if_exists(test_engine, f"tenant_{slug.replace('-', '_')}")


# ── Retry resumes from failed_step ────────────────────────────────────────────


async def test_retry_resumes_from_failed_step(test_engine: AsyncEngine) -> None:
    """Tenant failed at run_migrations — retry must skip create_schema."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    slug = f"prov-retry-{uuid.uuid4().hex[:8]}"
    schema = f"tenant_{slug.replace('-', '_')}"
    tenant = await _insert_tenant(
        factory, slug=slug, status="failed", failed_step="run_migrations"
    )

    create_schema_mock = AsyncMock()
    with (
        patch("app.platform_.provisioning.tasks.run_create_schema", new=create_schema_mock),
        patch("app.platform_.provisioning.tasks.run_migrations_step"),
        patch("app.platform_.provisioning.tasks.run_seed_defaults_step", new=AsyncMock()),
    ):
        await _execute_steps(test_engine, factory, tenant.id)

    create_schema_mock.assert_not_called()

    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        updated = (
            await s.execute(select(Tenant).where(Tenant.id == tenant.id))
        ).scalar_one()

    assert updated.status == "active"

    await _delete_tenant(factory, tenant.id)
    await _drop_schema_if_exists(test_engine, schema)


# ── Advisory lock prevents concurrent execution ───────────────────────────────


async def test_advisory_lock_prevents_concurrent_runs(test_engine: AsyncEngine) -> None:
    """Two concurrent provision calls on the same tenant: only one proceeds."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    slug = f"prov-lock-{uuid.uuid4().hex[:8]}"
    tenant = await _insert_tenant(factory, slug=slug)

    execution_count = 0

    async def _slow_create_schema(engine: AsyncEngine, schema_name: str) -> None:
        nonlocal execution_count
        execution_count += 1
        await asyncio.sleep(0.05)

    with (
        patch("app.platform_.provisioning.tasks.run_create_schema", new=_slow_create_schema),
        patch("app.platform_.provisioning.tasks.run_migrations_step"),
        patch("app.platform_.provisioning.tasks.run_seed_defaults_step", new=AsyncMock()),
    ):
        await asyncio.gather(
            _run_provision(tenant.id),
            _run_provision(tenant.id),
        )

    assert execution_count == 1

    await _delete_tenant(factory, tenant.id)
    await _drop_schema_if_exists(test_engine, f"tenant_{slug.replace('-', '_')}")


# ── Seed step: graceful skip on missing tables ────────────────────────────────


async def test_seed_defaults_skips_missing_tables(test_engine: AsyncEngine) -> None:
    """seed_defaults runs against a schema with no tables — no exception raised."""
    schema = "tenant_prov_seed_test"
    try:
        async with test_engine.connect() as conn:
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))  # noqa: S608
            await conn.commit()
        await run_seed_defaults_step(test_engine, schema)
    finally:
        await _drop_schema_if_exists(test_engine, schema)
