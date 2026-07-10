"""Celery beat tasks for the notifications framework.

dispatch_pending_notifications  — 30s: claim due queued events (SKIP LOCKED), dispatch
retry_failed_notifications      — 5 min: re-queue failed/partial events under the attempt cap
purge_old_notification_events   — daily: delete terminal events older than 180 days

Each task iterates the platform schema plus every active tenant schema
(same pattern as app/modules/fees/beat.py).
"""
from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")

_RETRY_BACKOFF_MINUTES = 5


async def _schemas(engine: AsyncEngine) -> list[str]:
    """All dispatch scopes: the platform schema + active tenant schemas."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
        )
        tenant_schemas = [row[0] for row in result.fetchall() if _SCHEMA_RE.match(row[0])]
    return ["platform", *tenant_schemas]


def _event_model(schema: str) -> Any:
    from app.core.notifications.models import (
        PlatformNotificationEvent,
        TenantNotificationEvent,
    )

    return PlatformNotificationEvent if schema == "platform" else TenantNotificationEvent


def _delivery_model(schema: str) -> Any:
    from app.core.notifications.models import (
        PlatformNotificationDelivery,
        TenantNotificationDelivery,
    )

    return (
        PlatformNotificationDelivery if schema == "platform" else TenantNotificationDelivery
    )


async def _dispatch_for_schema(engine: AsyncEngine, schema: str) -> int:
    from app.core.notifications.dispatcher import dispatch_event

    model = _event_model(schema)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    dispatched = 0
    async with factory() as session:
        if schema == "platform":
            session.sync_session.info["is_platform"] = True
        await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))  # noqa: S608
        events = list(
            (
                await session.execute(
                    select(model)
                    .where(model.status == "queued", model.scheduled_at <= func.now())
                    .order_by(model.scheduled_at)
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
            ).scalars()
        )
        for event in events:
            await dispatch_event(session, event)
            dispatched += 1
        await session.commit()
    return dispatched


async def _retry_for_schema(
    engine: AsyncEngine, schema: str, *, max_attempts: int = 3
) -> int:
    model = _event_model(schema)
    delivery_model = _delivery_model(schema)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    requeued = 0
    async with factory() as session:
        if schema == "platform":
            session.sync_session.info["is_platform"] = True
        await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))  # noqa: S608
        events = list(
            (
                await session.execute(
                    select(model)
                    .where(model.status.in_(("partial", "failed")))
                    .with_for_update(skip_locked=True)
                )
            ).scalars()
        )
        for event in events:
            deliveries = list(
                (
                    await session.execute(
                        select(delivery_model).where(
                            delivery_model.notification_event_id == event.id
                        )
                    )
                ).scalars()
            )
            failed_channels = {
                d.channel for d in deliveries if d.status == "failed"
            } - {d.channel for d in deliveries if d.status == "sent"}
            if not failed_channels:
                continue
            max_attempt_per_channel = {
                channel: max(d.attempt for d in deliveries if d.channel == channel)
                for channel in failed_channels
            }
            if any(a >= max_attempts for a in max_attempt_per_channel.values()):
                continue  # terminal — at least one channel exhausted its attempts
            newest = max(d.sent_at for d in deliveries)
            if newest >= datetime.now(UTC) - timedelta(minutes=_RETRY_BACKOFF_MINUTES):
                continue  # too soon — wait out the backoff window
            event.status = "queued"
            event.scheduled_at = datetime.now(UTC)
            requeued += 1
        await session.commit()
    return requeued


async def _purge_for_schema(engine: AsyncEngine, schema: str, *, days: int = 180) -> int:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))  # noqa: S608
        result = await session.execute(
            text(
                "DELETE FROM notification_events "
                "WHERE status != 'queued' "
                "AND created_at < now() - make_interval(days => :days)"
            ),
            {"days": days},
        )
        await session.commit()
    deleted: int = getattr(result, "rowcount", 0) or 0
    return deleted


async def _run_all(job: Callable[[AsyncEngine, str], Awaitable[int]]) -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    totals: dict[str, int] = {}
    try:
        for schema in await _schemas(engine):
            try:
                count = await job(engine, schema)
                if count:
                    totals[schema] = count
            except Exception as exc:  # keep other schemas running
                _log.warning(
                    "notification.beat_schema_failed", schema=schema, error=str(exc)
                )
                totals[schema] = -1
    finally:
        await engine.dispose()
    return totals


@celery_app.task(name="app.core.notifications.beat.dispatch_pending_notifications")  # type: ignore[misc]
def dispatch_pending_notifications() -> dict[str, int]:
    """Every 30s: dispatch due queued notification events in every schema."""
    return asyncio.run(_run_all(_dispatch_for_schema))


@celery_app.task(name="app.core.notifications.beat.retry_failed_notifications")  # type: ignore[misc]
def retry_failed_notifications() -> dict[str, int]:
    """Every 5 min: re-queue failed/partial events still under the attempt cap."""
    return asyncio.run(_run_all(_retry_for_schema))


@celery_app.task(name="app.core.notifications.beat.purge_old_notification_events")  # type: ignore[misc]
def purge_old_notification_events() -> dict[str, int]:
    """Daily: delete terminal notification events older than 180 days."""
    return asyncio.run(_run_all(_purge_for_schema))
