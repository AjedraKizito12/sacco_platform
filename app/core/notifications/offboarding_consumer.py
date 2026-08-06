"""Tenant offboarding notifications consumer (Phase 7).

Bridges platform-outbox tenant-offboarding events to tenant-admin notification
feeds: offboarding runs in platform transactions, but its recipients (tenant
admins) read tenant-schema feeds. At-least-once via platform processed_events;
every publish carries a dedupe_key so redelivery cannot double-notify.

Mirror of app.platform_.billing.consumer — the shared pattern is intentional.
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
_CONSUMER_NAME = "notifications.offboarding_consumer"
_BATCH = 50

# outbox event_type → notification event_code.
_CODE_FOR_EVENT: dict[str, str] = {
    "TenantOffboardingCancelled": "tenant_offboarding_cancelled",
    "TenantOffboardingReadOnly": "tenant_offboarding_read_only",
    "TenantOffboardingArchived": "tenant_offboarding_archived",
    "TenantOffboardingRestored": "tenant_offboarding_restored",
}

_FETCH_SQL = (
    "SELECT id, event_type, payload FROM platform.outbox_events "  # noqa: S608 — constants only
    "WHERE event_type IN ('TenantOffboardingCancelled', 'TenantOffboardingReadOnly', "
    "'TenantOffboardingArchived', 'TenantOffboardingRestored') "
    "AND id NOT IN ("
    "    SELECT event_id FROM platform.processed_events "
    f"    WHERE consumer_name = '{_CONSUMER_NAME}'"
    f") ORDER BY occurred_at LIMIT {_BATCH}"
)


def _context(payload: dict[str, Any]) -> dict[str, Any]:
    """Notice context — notices only, no secrets/PII."""
    return {
        "tenant_name": payload["tenant_name"],
        "to_state": payload["to_state"],
        "occurred_at": payload["occurred_at"],
    }


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

    code = _CODE_FOR_EVENT[event_type]
    context = _context(payload)
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
    """Process one batch of unhandled offboarding events. Returns count."""
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
                    "notifications.offboarding_consumer.event_error",
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


@celery_app.task(  # type: ignore[misc]
    name="app.core.notifications.offboarding_consumer.consume_offboarding_notification_events"
)
def consume_offboarding_notification_events() -> dict[str, int]:
    """Every minute: bridge offboarding platform events to tenant-admin feeds."""
    return asyncio.run(_run())
