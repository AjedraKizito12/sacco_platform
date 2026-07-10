"""Notification tables. Dual-schema pattern (see maker_checker.models).

Templates live in the PLATFORM schema only. Events / deliveries /
preferences exist in both schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 (runtime use by SQLAlchemy)
from typing import Any

from sqlalchemy import (
    UUID,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="en")
    subject_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sms_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "code", "channel", "locale",
            name="uq_notification_templates_code_channel_locale",
        ),
        {"schema": "platform"},
    )


class NotificationEventMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_code: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_kind: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipient_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class NotificationDeliveryMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )


class NotificationPreferenceMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recipient_kind: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_code: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TenantNotificationEvent(NotificationEventMixin, Base):
    __tablename__ = "notification_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_notification_events_dedupe_key"),
        Index("ix_notification_events_dispatch", "status", "scheduled_at"),
        Index(
            "ix_notification_events_recipient",
            "recipient_kind", "recipient_user_id", "created_at",
        ),
    )


class PlatformNotificationEvent(NotificationEventMixin, Base):
    __tablename__ = "notification_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_platform_notification_events_dedupe_key"),
        Index("ix_platform_notification_events_dispatch", "status", "scheduled_at"),
        Index(
            "ix_platform_notification_events_recipient",
            "recipient_kind", "recipient_user_id", "created_at",
        ),
        {"schema": "platform"},
    )


class TenantNotificationDelivery(NotificationDeliveryMixin, Base):
    __tablename__ = "notification_deliveries"
    notification_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    __table_args__ = (
        Index("ix_notification_deliveries_event", "notification_event_id"),
    )


class PlatformNotificationDelivery(NotificationDeliveryMixin, Base):
    __tablename__ = "notification_deliveries"
    notification_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.notification_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    __table_args__ = (
        Index("ix_platform_notification_deliveries_event", "notification_event_id"),
        {"schema": "platform"},
    )


class TenantNotificationPreference(NotificationPreferenceMixin, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "recipient_kind", "user_id", "event_code", "channel",
            name="uq_notification_preferences_scope",
        ),
    )


class PlatformNotificationPreference(NotificationPreferenceMixin, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "recipient_kind", "user_id", "event_code", "channel",
            name="uq_platform_notification_preferences_scope",
        ),
        {"schema": "platform"},
    )
