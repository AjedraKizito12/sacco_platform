from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 (used at runtime by SQLAlchemy)
from typing import Any

from sqlalchemy import UUID, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class _AuditLogBase:
    """Column definitions shared by platform and tenant audit_log tables."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_name: Mapped[str] = mapped_column(Text, nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)  # insert | update | delete
    # actor_type values: platform_user | tenant_user | system | api_client
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlatformAuditLog(_AuditLogBase, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_platform_audit_log_table_record", "table_name", "record_id"),
        Index("ix_platform_audit_log_occurred_at", text("occurred_at DESC")),
        {"schema": "platform"},
    )


class TenantAuditLog(_AuditLogBase, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_tenant_audit_log_table_record", "table_name", "record_id"),
        Index("ix_tenant_audit_log_occurred_at", text("occurred_at DESC")),
    )
