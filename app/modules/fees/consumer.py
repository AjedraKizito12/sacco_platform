"""Fee event consumer: polls tenant outbox_events for fee-relevant events.

Runs as a Celery beat task (every 60 seconds per tenant). Checks
processed_events to guarantee at-most-once processing per (event_id, consumer).
"""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
_CONSUMER_NAME = "fees.event_consumer"
_BATCH = 50


async def _process_tenant_events(schema_name: str, engine: AsyncEngine) -> int:
    """Process unhandled fee-relevant outbox events for one tenant schema.

    Returns count of events processed.
    """
    from app.core.outbox.models import TenantOutboxEvent
    from app.modules.fees.models import FeeType

    factory = async_sessionmaker(engine, expire_on_commit=False)
    processed = 0

    async with factory() as session:
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )

        # Load active event-triggered fee types for this tenant.
        fee_types = list(
            (
                await session.execute(
                    select(FeeType).where(
                        FeeType.trigger_kind == "event",
                        FeeType.is_active.is_(True),
                        FeeType.event_name.is_not(None),
                    )
                )
            ).scalars().all()
        )

        if not fee_types:
            return 0

        event_names = {ft.event_name for ft in fee_types}

        # Fetch unprocessed events for those event types.
        rows = list(
            (
                await session.execute(
                    select(TenantOutboxEvent)
                    .where(
                        TenantOutboxEvent.event_type.in_(event_names),
                        ~TenantOutboxEvent.id.in_(
                            select(
                                text("event_id")
                            ).select_from(
                                text("processed_events")
                            ).where(
                                text(f"consumer_name = '{_CONSUMER_NAME}'")  # noqa: S608
                            )
                        ),
                    )
                    .order_by(TenantOutboxEvent.occurred_at)
                    .limit(_BATCH)
                )
            ).scalars().all()
        )

        for event in rows:
            try:
                async with session.begin_nested():
                    # Double-check idempotency inside savepoint.
                    already = await session.scalar(
                        text(
                            "SELECT 1 FROM processed_events "
                            "WHERE event_id = :eid AND consumer_name = :cn"
                        ),
                        {"eid": event.id, "cn": _CONSUMER_NAME},
                    )
                    if already:
                        continue

                    await _handle_event(session, event, fee_types)

                    await session.execute(
                        text(
                            "INSERT INTO processed_events (event_id, consumer_name, processed_at) "
                            "VALUES (:eid, :cn, now())"
                        ),
                        {"eid": event.id, "cn": _CONSUMER_NAME},
                    )
                    processed += 1
            except Exception as exc:
                _log.error(
                    "fees.consumer.event_error",
                    event_id=str(event.id),
                    event_type=event.event_type,
                    schema=schema_name,
                    error=str(exc),
                )

        await session.commit()

    return processed


async def _handle_event(session: AsyncSession, event: Any, fee_types: list[Any]) -> None:
    """Dispatch a single event to all matching fee types."""
    from datetime import date

    from app.modules.fees.service import FeeAssessmentService

    matching = [ft for ft in fee_types if ft.event_name == event.event_type]
    if not matching:
        return

    svc = FeeAssessmentService(session)
    today = date.today()

    if event.event_type == "MemberActivated":
        member_id = uuid.UUID(event.payload["member_id"])
        for ft in matching:
            await svc.assess(
                fee_type=ft,
                target_type="member",
                target_id=member_id,
                period_start=today,
                period_end=None,
                triggered_by_event_id=event.id,
                actor=uuid.UUID("00000000-0000-0000-0000-000000000000"),
                idempotency_key=f"event-{event.id}-{ft.id}",
            )
    # Future event types: add elif branches here.


async def _run_consume_fee_events() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    totals: dict[str, int] = {}

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            schemas = [row[0] for row in result.fetchall()]

        for schema_name in schemas:
            if not _SCHEMA_RE.match(schema_name):
                _log.error("fees.consumer.invalid_schema", schema=schema_name)
                continue
            try:
                count = await _process_tenant_events(schema_name, engine)
                if count:
                    totals[schema_name] = count
            except Exception as exc:
                _log.error("fees.consumer.tenant_error", schema=schema_name, error=str(exc))
    finally:
        await engine.dispose()

    return totals


@celery_app.task(name="app.modules.fees.consumer.consume_fee_events")  # type: ignore[misc]
def consume_fee_events() -> dict[str, int]:
    """Every 60 s: process unhandled fee-relevant outbox events for all tenants."""
    return asyncio.run(_run_consume_fee_events())
