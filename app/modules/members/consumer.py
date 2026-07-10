"""Member notifications consumer (notifications increment 2).

Derives the member_activated notification from the existing MemberActivated
tenant-outbox event (published by the member status-change executor).
At-least-once via per-schema processed_events; the dedupe_key heals
redelivery.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)
_SCHEMA_RE = re.compile(r"^tenant_[a-z0-9_]{1,40}$")
_CONSUMER_NAME = "notifications.member_consumer"
_BATCH = 50


def _fetch_sql(schema: str) -> str:
    return (  # noqa: S608 — schema is regex-validated, constants otherwise
        f"SELECT id, payload FROM {schema}.outbox_events "  # noqa: S608
        f"WHERE event_type = 'MemberActivated' "
        f"AND id NOT IN ("
        f"    SELECT event_id FROM {schema}.processed_events "  # noqa: S608
        f"    WHERE consumer_name = '{_CONSUMER_NAME}'"
        f") ORDER BY occurred_at LIMIT {_BATCH}"
    )


async def _consume_for_tenant(engine: AsyncEngine, schema: str) -> int:
    from app.core.notifications.service import NotificationService  # noqa: PLC0415
    from app.modules.members.models import Member  # noqa: PLC0415

    factory = async_sessionmaker(engine, expire_on_commit=False)
    processed = 0
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path TO {schema}, platform"))  # noqa: S608
        rows = list((await session.execute(text(_fetch_sql(schema)))).all())
        for row in rows:
            event_id: uuid.UUID = row[0]
            payload: dict[str, Any] = row[1]
            try:
                async with session.begin_nested():
                    member = await session.get(
                        Member, uuid.UUID(payload["member_id"])
                    )
                    if member is not None:
                        await NotificationService(session).publish(
                            event_code="member_activated",
                            recipient_kind="member",
                            recipient_user_id=member.id,
                            recipient_email=member.email,
                            context={
                                "full_name": member.full_name,
                                "member_number": member.member_number,
                            },
                            dedupe_key=f"member_activated:{event_id}",
                        )
                    await session.execute(
                        text(
                            f"INSERT INTO {schema}.processed_events "  # noqa: S608
                            "(event_id, consumer_name, processed_at) "
                            "VALUES (:eid, :cn, now())"
                        ),
                        {"eid": event_id, "cn": _CONSUMER_NAME},
                    )
                    processed += 1
            except Exception as exc:
                _log.error(
                    "notifications.member_consumer.event_error",
                    event_id=str(event_id),
                    schema=schema,
                    error=str(exc),
                )
        await session.commit()
    return processed


async def _run() -> dict[str, int]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    totals: dict[str, int] = {}
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT schema_name FROM platform.tenants WHERE is_active = true")
            )
            schemas = [row[0] for row in result.fetchall()]
        for schema in schemas:
            if not _SCHEMA_RE.match(schema):
                continue
            try:
                count = await _consume_for_tenant(engine, schema)
                if count:
                    totals[schema] = count
            except Exception as exc:
                _log.warning(
                    "notifications.member_consumer.schema_failed",
                    schema=schema,
                    error=str(exc),
                )
    finally:
        await engine.dispose()
    return totals


@celery_app.task(name="app.modules.members.consumer.consume_member_notification_events")  # type: ignore[misc]
def consume_member_notification_events() -> dict[str, int]:
    """Every minute: derive member_activated notifications from MemberActivated."""
    return asyncio.run(_run())
