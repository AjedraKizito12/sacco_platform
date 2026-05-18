from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 (used at runtime by SQLAlchemy)
from typing import Any

from sqlalchemy import UUID, Boolean, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class _OutboxEventBase:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    is_dead_lettered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PlatformOutboxEvent(_OutboxEventBase, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_platform_outbox_pending",
            "next_attempt_at",
            postgresql_where="published_at IS NULL AND is_dead_lettered = false",
        ),
        {"schema": "platform"},
    )


class TenantOutboxEvent(_OutboxEventBase, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_tenant_outbox_pending",
            "next_attempt_at",
            postgresql_where="published_at IS NULL AND is_dead_lettered = false",
        ),
    )
