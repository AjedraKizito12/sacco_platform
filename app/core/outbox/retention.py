"""
Outbox retention task. Purges old published events to prevent unbounded table growth.
Runs monthly via Celery beat.
"""
from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.outbox.models import PlatformOutboxEvent, TenantOutboxEvent, _OutboxEventBase
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)

_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


async def _purge(
    schema: str, model_cls: type[_OutboxEventBase], cutoff: datetime, engine: AsyncEngine
) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))  # noqa: S608
        result = await session.execute(
            delete(model_cls).where(
                model_cls.published_at.is_not(None),
                model_cls.published_at < cutoff,
            )
        )
        return int(result.rowcount)


async def _run_purge() -> None:
    settings = get_settings()
    retention_days = settings.outbox_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    engine = create_async_engine(settings.database_url)
    try:
        deleted = await _purge("platform", PlatformOutboxEvent, cutoff, engine)
        _log.info("outbox.retention.platform", deleted=deleted, cutoff=cutoff.isoformat())

        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
                )
                tenants = [row[0] for row in result.fetchall()]
        except Exception as exc:
            _log.warning("outbox.retention.tenant_list_unavailable", error=str(exc))
            tenants = []

        for schema in tenants:
            if not _SCHEMA_RE.match(schema):
                _log.error("outbox.retention.invalid_schema", schema=schema)
                continue
            deleted = await _purge(schema, TenantOutboxEvent, cutoff, engine)
            _log.info("outbox.retention.tenant", schema=schema, deleted=deleted)
    finally:
        await engine.dispose()


@celery_app.task(name="app.core.outbox.retention.purge_outbox_retention")  # type: ignore[misc]
def purge_outbox_retention() -> None:
    asyncio.run(_run_purge())
