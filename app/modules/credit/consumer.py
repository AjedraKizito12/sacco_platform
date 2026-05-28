"""Credit event consumer: polls tenant outbox_events for fee-relevant events.

Runs as a Celery beat task (every 60 seconds per tenant). Checks
processed_events to guarantee at-most-once processing per (event_id, consumer).

Handles:
  - FeeAssessmentCreated  → increments loan.accrued_penalties
  - FeeCollectionCreated  → decrements loan.accrued_penalties,
                            increments loan.total_paid_penalties
"""
from __future__ import annotations

import asyncio
import re
import uuid
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
_CONSUMER_NAME = "credit.event_consumer"
_HANDLED_EVENTS = frozenset({"FeeAssessmentCreated", "FeeCollectionCreated"})
_BATCH = 50


def _fetch_sql(schema: str) -> str:
    event_types_sql = ", ".join(f"'{et}'" for et in sorted(_HANDLED_EVENTS))
    return (  # noqa: S608
        f"SELECT id, event_type, payload "  # noqa: S608
        f"FROM {schema}.outbox_events "  # noqa: S608
        f"WHERE event_type IN ({event_types_sql}) "  # noqa: S608
        f"AND id NOT IN ("  # noqa: S608
        f"    SELECT event_id FROM {schema}.processed_events "  # noqa: S608
        f"    WHERE consumer_name = '{_CONSUMER_NAME}'"  # noqa: S608
        f") ORDER BY occurred_at LIMIT {_BATCH}"  # noqa: S608
    )


async def _process_tenant_events(schema_name: str, engine) -> int:
    """Process unhandled credit-relevant outbox events for one tenant schema.

    All table references are fully schema-qualified so the query works on a
    fresh connection whose search_path has not been customised.

    Returns count of events processed.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    processed = 0

    async with factory() as session:
        rows = list((await session.execute(text(_fetch_sql(schema_name)))).all())

        for row in rows:
            event_id: uuid.UUID = row[0]
            event_type: str = row[1]
            payload: dict = row[2]
            try:
                async with session.begin_nested():
                    # Double-check idempotency inside savepoint.
                    check_sql = (  # noqa: S608
                        f"SELECT 1 FROM {schema_name}.processed_events "  # noqa: S608
                        "WHERE event_id = :eid AND consumer_name = :cn"
                    )
                    already = await session.scalar(
                        text(check_sql),
                        {"eid": event_id, "cn": _CONSUMER_NAME},
                    )
                    if already:
                        continue

                    await _handle_event(session, schema_name, event_id, event_type, payload)

                    insert_sql = (  # noqa: S608
                        f"INSERT INTO {schema_name}.processed_events "  # noqa: S608
                        "(event_id, consumer_name, processed_at) VALUES (:eid, :cn, now())"
                    )
                    await session.execute(
                        text(insert_sql),
                        {"eid": event_id, "cn": _CONSUMER_NAME},
                    )
                    processed += 1
            except Exception as exc:
                _log.error(
                    "credit.consumer.event_error",
                    event_id=str(event_id),
                    event_type=event_type,
                    schema=schema_name,
                    error=str(exc),
                )

        await session.commit()

    return processed


async def _handle_event(  # noqa: PLR0913
    session,
    schema_name: str,
    event_id: uuid.UUID,
    event_type: str,
    payload: dict,
) -> None:
    """Dispatch a single event to the appropriate handler."""
    if event_type == "FeeAssessmentCreated":
        if payload.get("target_type") != "loan":
            return
        loan_id = uuid.UUID(payload["target_id"])
        amount = Decimal(payload["amount"])
        update_sql = (  # noqa: S608
            f"UPDATE {schema_name}.loans "  # noqa: S608
            "SET accrued_penalties = accrued_penalties + :amount WHERE id = :loan_id"
        )
        updated = await session.execute(
            text(update_sql),
            {"amount": amount, "loan_id": loan_id},
        )
        if updated.rowcount == 0:
            _log.warning(
                "credit.consumer.loan_not_found",
                loan_id=str(loan_id),
                event_id=str(event_id),
            )

    elif event_type == "FeeCollectionCreated":
        if payload.get("target_type") != "loan":
            return
        loan_id = uuid.UUID(payload["target_id"])
        amount_collected = Decimal(payload["amount_collected"])
        update_sql = (  # noqa: S608
            f"UPDATE {schema_name}.loans "  # noqa: S608
            "SET accrued_penalties = GREATEST(accrued_penalties - :amount, 0), "
            "    total_paid_penalties = total_paid_penalties + :amount "
            "WHERE id = :loan_id"
        )
        updated = await session.execute(
            text(update_sql),
            {"amount": amount_collected, "loan_id": loan_id},
        )
        if updated.rowcount == 0:
            _log.warning(
                "credit.consumer.loan_not_found",
                loan_id=str(loan_id),
                event_id=str(event_id),
            )


async def _run_consume_credit_events() -> dict[str, int]:
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
                _log.error("credit.consumer.invalid_schema", schema=schema_name)
                continue
            try:
                count = await _process_tenant_events(schema_name, engine)
                if count:
                    totals[schema_name] = count
            except Exception as exc:
                _log.error("credit.consumer.tenant_error", schema=schema_name, error=str(exc))
    finally:
        await engine.dispose()

    return totals


@celery_app.task(name="app.modules.credit.consumer.consume_credit_events")  # type: ignore[misc]
def consume_credit_events() -> dict[str, int]:
    """Every 60 s: process unhandled credit-relevant outbox events for all tenants."""
    return asyncio.run(_run_consume_credit_events())
