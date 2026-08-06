"""Daily tenant-offboarding transition beat jobs (Phase 7).

Three staggered daily sweeps advance tenants through the lifecycle once their
retention window elapses:

    transition_cancelled_to_read_only   00:00 UTC — cancelled  → read_only
    transition_read_only_to_archived    00:30 UTC — read_only  → archived
    transition_archived_to_hard_deleted 01:00 UTC — archived   → hard_deleted

Each runs in a platform session; the physical archival (pg_dump/encrypt/upload/
DROP SCHEMA) is infra-side (infra/offboarding/), keyed off the `archived` state.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.platform_.tenants.offboarding_service import OffboardingService
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)


async def _run_sweep(engine: AsyncEngine, method_name: str) -> list[uuid.UUID]:
    """Open a platform session, run one sweep, commit. Returns transitioned ids."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text("SET LOCAL search_path TO platform"))
        # is_platform routes lifecycle-event outbox rows to platform.outbox_events.
        session.sync_session.info["is_platform"] = True
        sweep = getattr(OffboardingService(session), method_name)
        ids: list[uuid.UUID] = await sweep(now=datetime.now(UTC))
        await session.commit()
        return ids


async def _run(method_name: str) -> dict[str, int]:
    engine = create_async_engine(get_settings().database_url)
    try:
        ids = await _run_sweep(engine, method_name)
    except Exception as exc:  # a bad batch must not wedge the beat
        _log.error("offboarding.beat.error", task=method_name, error=str(exc))
        ids = []
    finally:
        await engine.dispose()
    _log.info("offboarding.beat.done", task=method_name, transitioned=len(ids))
    return {"transitioned": len(ids)}


@celery_app.task(  # type: ignore[misc]
    name="app.platform_.tenants.beat.transition_cancelled_to_read_only"
)
def transition_cancelled_to_read_only() -> dict[str, int]:
    """Daily: cancelled tenants past the read-only window → read_only."""
    return asyncio.run(_run("sweep_cancelled_to_read_only"))


@celery_app.task(  # type: ignore[misc]
    name="app.platform_.tenants.beat.transition_read_only_to_archived"
)
def transition_read_only_to_archived() -> dict[str, int]:
    """Daily: read_only tenants past the archive window (no hold) → archived."""
    return asyncio.run(_run("sweep_read_only_to_archived"))


@celery_app.task(  # type: ignore[misc]
    name="app.platform_.tenants.beat.transition_archived_to_hard_deleted"
)
def transition_archived_to_hard_deleted() -> dict[str, int]:
    """Daily: archived tenants past the hard-delete window → hard_deleted."""
    return asyncio.run(_run("sweep_archived_to_hard_deleted"))
