"""Celery provisioning task: provision_tenant.

Executes the four provisioning steps with a Postgres advisory lock so
concurrent invocations on the same tenant exit immediately.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.platform_.provisioning.steps import (
    STEP_SEQUENCE,
    load_tenant,
    run_create_schema,
    run_finalize,
    run_migrations_step,
    run_seed_defaults_step,
    update_tenant_fields,
)
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


@celery_app.task(name="app.platform_.provisioning.tasks.provision_tenant")  # type: ignore[misc]
def provision_tenant(tenant_id_str: str) -> None:
    asyncio.run(_run_provision(uuid.UUID(tenant_id_str)))


async def _run_provision(tenant_id: uuid.UUID) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        # Hold a dedicated connection for the session-level advisory lock.
        # Lock is released automatically when the connection closes.
        async with engine.connect() as lock_conn:
            await lock_conn.execute(text("SET search_path TO platform"))
            lock_key = f"provision:{tenant_id}"
            acquired = (
                await lock_conn.execute(
                    text("SELECT pg_try_advisory_lock(hashtext(:key))"),
                    {"key": lock_key},
                )
            ).scalar_one()

            if not acquired:
                _log.info("provision.already_running", tenant_id=str(tenant_id))
                return

            try:
                await _execute_steps(engine, factory, tenant_id)
            finally:
                await lock_conn.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:key))"),
                    {"key": lock_key},
                )
    finally:
        await engine.dispose()


async def _execute_steps(
    engine: Any,
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
) -> None:
    tenant_data = await load_tenant(factory, tenant_id)
    if tenant_data is None:
        _log.error("provision.tenant_not_found", tenant_id=str(tenant_id))
        return

    schema_name = tenant_data["schema_name"]
    if not _SCHEMA_RE.match(schema_name):
        _log.error("provision.invalid_schema", schema=schema_name, tenant_id=str(tenant_id))
        return

    # Determine starting step (resume from failed_step if retrying).
    failed_step = tenant_data["failed_step"]
    start_idx = STEP_SEQUENCE.index(failed_step) if failed_step in STEP_SEQUENCE else 0
    steps_to_run = STEP_SEQUENCE[start_idx:]

    await update_tenant_fields(
        factory,
        tenant_id,
        status="provisioning",
        provisioning_started_at=datetime.now(UTC),
        failed_step=None,
        failure_reason=None,
    )

    for step_name in steps_to_run:
        await update_tenant_fields(factory, tenant_id, provisioning_state=step_name)

        try:
            if step_name == "create_schema":
                await run_create_schema(engine, schema_name)

            elif step_name == "run_migrations":
                run_migrations_step(schema_name)  # sync

            elif step_name == "seed_defaults":
                await run_seed_defaults_step(engine, schema_name)

            elif step_name == "finalize":
                await run_finalize(
                    factory,
                    tenant_id,
                    slug=tenant_data["slug"],
                    schema_name=schema_name,
                    seed_version=tenant_data["seed_version"],
                )

            _log.info("provision.step_ok", step=step_name, tenant_id=str(tenant_id))

        except Exception as exc:
            await update_tenant_fields(
                factory,
                tenant_id,
                status="failed",
                failed_step=step_name,
                failure_reason=str(exc),
            )
            _log.error(
                "provision.step_failed",
                step=step_name,
                error=str(exc),
                tenant_id=str(tenant_id),
                exc_info=True,
            )
            return
