from __future__ import annotations

import uuid  # noqa: TC003 (used at runtime)
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002 (used at runtime)

from app.core.outbox.models import PlatformOutboxEvent, TenantOutboxEvent


class EventPublisher:
    """The ONLY permitted path for emitting cross-module events.

    Call publish() inside an open session transaction. The outbox row is
    committed or rolled back with the caller's business transaction.
    Direct aio_pika / pika usage outside app/core/outbox/ is forbidden.
    """

    @staticmethod
    async def publish(
        session: AsyncSession,
        *,
        aggregate_type: str,
        aggregate_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        is_platform = session.sync_session.info.get("is_platform", False)
        model_cls = PlatformOutboxEvent if is_platform else TenantOutboxEvent
        row = model_cls(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
        session.add(row)
