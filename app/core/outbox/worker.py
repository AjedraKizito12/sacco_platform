"""
Outbox relay workers. Pull unpublished events from outbox_events and
publish to RabbitMQ with publisher confirms. At-least-once delivery.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import aio_pika
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.observability import metrics
from app.core.outbox.models import PlatformOutboxEvent, TenantOutboxEvent
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)

_MAX_ROWS_PER_TICK = 1_000
_BATCH_SIZE = 100
_WALL_CLOCK_LIMIT = 30.0  # seconds
_MAX_ATTEMPTS = 10
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")


def _next_attempt_delta(attempts: int) -> timedelta:
    delay = min(30 * (2**attempts), 3600)
    return timedelta(seconds=delay)


async def _relay_outbox(
    session: AsyncSession,
    model_cls: type[Any],
    context: str,
    rabbitmq_url: str,
    search_path: str = "platform",
) -> None:
    """Drain unpublished rows from one outbox table."""
    now = datetime.now(UTC)
    deadline = time.monotonic() + _WALL_CLOCK_LIMIT
    total_processed = 0

    conn = await aio_pika.connect_robust(rabbitmq_url)
    try:
        channel = await conn.channel()
        exchange = await channel.declare_exchange(
            "sacco.events", aio_pika.ExchangeType.TOPIC, durable=True
        )

        while total_processed < _MAX_ROWS_PER_TICK and time.monotonic() < deadline:
            async with session.begin():
                await session.execute(text(f"SET LOCAL search_path TO {search_path}"))  # noqa: S608
                rows = (
                    await session.execute(
                        select(model_cls)
                        .where(
                            model_cls.published_at.is_(None),
                            model_cls.is_dead_lettered.is_(False),
                            (model_cls.next_attempt_at.is_(None))
                            | (model_cls.next_attempt_at <= now),
                        )
                        .order_by(model_cls.occurred_at)
                        .limit(_BATCH_SIZE)
                        .with_for_update(skip_locked=True)
                    )
                ).scalars().all()

                if not rows:
                    break

                for row in rows:
                    t0 = time.monotonic()
                    routing_key = f"{context}.{row.aggregate_type}.{row.event_type}"
                    try:
                        msg = aio_pika.Message(
                            body=json.dumps(row.payload).encode(),
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                            message_id=str(row.id),
                        )
                        await exchange.publish(msg, routing_key=routing_key)
                        latency_ms = int((time.monotonic() - t0) * 1000)
                        _log.info(
                            "outbox.published",
                            event_id=str(row.id),
                            event_type=row.event_type,
                            context=context,
                            latency_ms=latency_ms,
                        )
                        row.published_at = datetime.now(UTC)
                        row.attempts += 1
                        metrics.outbox_publish_duration.record(time.monotonic() - t0)
                    except Exception as exc:
                        current_attempts = row.attempts  # before incrementing
                        row.attempts += 1
                        row.last_error = str(exc)
                        row.next_attempt_at = datetime.now(UTC) + _next_attempt_delta(
                            current_attempts
                        )
                        if row.attempts >= _MAX_ATTEMPTS:
                            row.is_dead_lettered = True
                            _log.error(
                                "outbox.dead_lettered",
                                event_id=str(row.id),
                                event_type=row.event_type,
                                context=context,
                                attempts=row.attempts,
                            )
                            metrics.outbox_dead_lettered.add(1)

                total_processed += len(rows)
    finally:
        await conn.close()


async def _run_platform_relay() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.sync_session.info["is_platform"] = True
            await _relay_outbox(
                session,
                PlatformOutboxEvent,
                "platform",
                settings.rabbitmq_url,
                search_path="platform",
            )
    finally:
        await engine.dispose()


async def _run_tenant_relay() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        # Get active tenant schemas from platform.tenants (table exists after platform_ module).
        # For now, query safely and skip if table doesn't exist yet.
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT schema_name, slug FROM platform.tenants WHERE is_active = true")
                )
                tenants = result.fetchall()
        except Exception as exc:
            _log.warning("outbox.tenant_list_unavailable", error=str(exc))
            return

        factory = async_sessionmaker(engine, expire_on_commit=False)
        for schema_name, slug in tenants:
            if not _SCHEMA_RE.match(schema_name):
                _log.error("outbox.invalid_schema", schema=schema_name)
                continue
            try:
                async with factory() as session:
                    await _relay_outbox(
                        session, TenantOutboxEvent, slug, settings.rabbitmq_url,
                        search_path=f"{schema_name}, platform",  # noqa: S608
                    )
            except Exception as exc:
                _log.error("outbox.tenant_relay_error", schema=schema_name, error=str(exc))
    finally:
        await engine.dispose()


@celery_app.task(name="app.core.outbox.worker.relay_platform_outbox")  # type: ignore[misc]
def relay_platform_outbox() -> None:
    asyncio.run(_run_platform_relay())


@celery_app.task(name="app.core.outbox.worker.relay_tenant_outbox")  # type: ignore[misc]
def relay_tenant_outbox() -> None:
    asyncio.run(_run_tenant_relay())
