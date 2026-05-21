"""Provisioning step functions: create_schema, run_migrations, seed_defaults, finalize.

Each step is idempotent. The task executor calls them in order, committing
between steps. Any exception aborts and marks the tenant as failed.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, text, update

from app.core.outbox.publisher import EventPublisher
from app.platform_.models import Tenant
from app.platform_.provisioning.migrations import run_tenant_migrations
from app.platform_.seeds.runner import seed_defaults

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

_log = structlog.get_logger(__name__)

STEP_SEQUENCE = ["create_schema", "run_migrations", "seed_defaults", "finalize"]


async def load_tenant(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> dict[str, Any] | None:
    """Load tenant fields needed by the task. Returns a plain dict to avoid session coupling."""
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        result = await s.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            return None
        return {
            "id": tenant.id,
            "slug": tenant.slug,
            "schema_name": tenant.schema_name,
            "failed_step": tenant.failed_step,
            "seed_version": tenant.seed_version,
        }


async def update_tenant_fields(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    **fields: Any,
) -> None:
    """Update arbitrary Tenant fields in a committed transaction."""
    fields["updated_at"] = datetime.now(UTC)
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(update(Tenant).where(Tenant.id == tenant_id).values(**fields))


async def run_create_schema(engine: AsyncEngine, schema_name: str) -> None:
    """Step 1: CREATE SCHEMA IF NOT EXISTS. Idempotent."""
    async with engine.connect() as conn:
        # schema_name validated against ^tenant_[a-z0-9_]{1,40}$ by caller.
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))  # noqa: S608
        await conn.commit()
    _log.info("provision.create_schema_done", schema=schema_name)


def run_migrations_step(schema_name: str) -> None:
    """Step 2: run alembic upgrade head. Idempotent (Alembic tracks versions)."""
    run_tenant_migrations(schema_name)
    _log.info("provision.migrations_done", schema=schema_name)


async def run_seed_defaults_step(engine: AsyncEngine, schema_name: str) -> None:
    """Step 3: seed default data. All inserts are ON CONFLICT DO NOTHING."""
    await seed_defaults(engine, schema_name)
    _log.info("provision.seed_done", schema=schema_name)


async def run_finalize(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    slug: str,
    schema_name: str,
    seed_version: int,
) -> None:
    """Step 4: set status=active, is_active=true, emit TenantProvisioned event."""
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.sync_session.info["is_platform"] = True
        await s.execute(
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(
                status="active",
                is_active=True,
                provisioning_state=None,
                provisioning_completed_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await EventPublisher.publish(
            s,
            aggregate_type="tenant",
            aggregate_id=tenant_id,
            event_type="TenantProvisioned",
            payload={
                "slug": slug,
                "schema_name": schema_name,
                "seed_version": seed_version,
            },
        )
    _log.info("provision.finalize_done", tenant_id=str(tenant_id), slug=slug)
