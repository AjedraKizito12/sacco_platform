"""Billing notifications consumer (notifications increment 2).

Bridges platform-outbox billing events to tenant-admin notification feeds:
billing runs in platform transactions, but its recipients (tenant admins)
read tenant-schema feeds. At-least-once via platform processed_events;
every publish carries a dedupe_key so redelivery cannot double-notify.

Ordering per event: tenant-session publishes commit FIRST, then the
processed_events marker commits — a crash between the two is healed by
the dedupe keys on redelivery.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
_CONSUMER_NAME = "notifications.billing_consumer"
_HANDLED_EVENTS = frozenset(
    {"BillingInvoiceIssued", "BillingInvoiceOverdue", "BillingSubscriptionSuspended"}
)
_BATCH = 50

_FETCH_SQL = (
    "SELECT id, event_type, payload FROM platform.outbox_events "  # noqa: S608 — constants only
    "WHERE event_type IN ('BillingInvoiceIssued', 'BillingInvoiceOverdue', "
    "'BillingSubscriptionSuspended') "
    "AND id NOT IN ("
    "    SELECT event_id FROM platform.processed_events "
    f"    WHERE consumer_name = '{_CONSUMER_NAME}'"
    f") ORDER BY occurred_at LIMIT {_BATCH}"
)


def _notification(event_type: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """(event_code, context) for a billing outbox event."""
    if event_type == "BillingInvoiceIssued":
        return "invoice_issued", {
            "invoice_number": payload["invoice_number"],
            "amount": payload["amount_total"],
            "currency": payload["currency"],
            "due_date": payload["due_at"],
        }
    if event_type == "BillingInvoiceOverdue":
        return "invoice_overdue", {
            "invoice_number": payload["invoice_number"],
            "amount": payload["amount_outstanding"],
            "currency": payload["currency"],
        }
    return "subscription_suspended", {}


async def _publish_to_tenant_admins(
    engine: AsyncEngine,
    schema: str,
    event_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
) -> int:
    """Publish the notification to every admin tenant_user. Own transaction."""
    from app.core.notifications.service import NotificationService  # noqa: PLC0415
    from app.modules.iam.tenant_users.models import TenantUser  # noqa: PLC0415

    code, context = _notification(event_type, payload)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    published = 0
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))  # noqa: S608
        admins = list(
            (
                await session.execute(
                    select(TenantUser).where(
                        TenantUser.is_active.is_(True),
                        TenantUser.is_admin.is_(True),
                        TenantUser.impersonation_id.is_(None),
                    )
                )
            ).scalars()
        )
        svc = NotificationService(session)
        for user in admins:
            await svc.publish(
                event_code=code,
                recipient_kind="tenant_user",
                recipient_user_id=user.id,
                recipient_email=user.email,
                context=context,
                dedupe_key=f"{event_type}:{event_id}:{user.id}",
            )
            published += 1
        await session.commit()
    return published


async def _consume_batch(engine: AsyncEngine) -> int:
    """Process one batch of unhandled billing events. Returns events processed."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    processed = 0
    async with factory() as session:
        rows = list((await session.execute(text(_FETCH_SQL))).all())
        for row in rows:
            event_id: uuid.UUID = row[0]
            event_type: str = row[1]
            payload: dict[str, Any] = row[2]
            try:
                schema = await session.scalar(
                    text(
                        "SELECT schema_name FROM platform.tenants "
                        "WHERE id = :tid AND is_active = true"
                    ),
                    {"tid": payload.get("tenant_id")},
                )
                if schema is not None and _SCHEMA_RE.match(schema):
                    await _publish_to_tenant_admins(
                        engine, schema, event_id, event_type, payload
                    )
                # Unknown/inactive tenant: mark processed and move on.
                await session.execute(
                    text(
                        "INSERT INTO platform.processed_events "
                        "(event_id, consumer_name, processed_at) "
                        "VALUES (:eid, :cn, now()) ON CONFLICT DO NOTHING"
                    ),
                    {"eid": event_id, "cn": _CONSUMER_NAME},
                )
                await session.commit()
                processed += 1
            except Exception as exc:
                await session.rollback()
                _log.error(
                    "notifications.billing_consumer.event_error",
                    event_id=str(event_id),
                    event_type=event_type,
                    error=str(exc),
                )
    return processed


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        count = await _consume_batch(engine)
    finally:
        await engine.dispose()
    return {"processed": count}


@celery_app.task(name="app.platform_.billing.consumer.consume_billing_notification_events")  # type: ignore[misc]
def consume_billing_notification_events() -> dict[str, int]:
    """Every minute: bridge billing platform events to tenant-admin feeds."""
    return asyncio.run(_run())
