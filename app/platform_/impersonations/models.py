"""SQLAlchemy model for platform.support_impersonations.

Carries AuditableMixin so every insert/update/delete writes to platform.audit_log.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — used at runtime by SQLAlchemy

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class SupportImpersonation(AuditableMixin, Base):
    __tablename__ = "support_impersonations"
    __table_args__ = (
        CheckConstraint(
            "ended_at IS NULL OR revoked_at IS NULL",
            name="ck_support_impersonations_not_both_ended_and_revoked",
        ),
        Index(
            "ix_support_impersonations_platform_user_active",
            "platform_user_id",
            postgresql_where=text("ended_at IS NULL AND revoked_at IS NULL"),
        ),
        Index(
            "ix_support_impersonations_tenant_active",
            "tenant_id",
            postgresql_where=text("ended_at IS NULL AND revoked_at IS NULL"),
        ),
        Index(
            "ix_support_impersonations_expires_at",
            "expires_at",
            postgresql_where=text("ended_at IS NULL AND revoked_at IS NULL"),
        ),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    platform_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.platform_users.id", name="fk_support_impersonations_platform_user"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.tenants.id", name="fk_support_impersonations_tenant"),
        nullable=False,
    )
    # tenant_user_id is the shadow tenant_user created lazily on first mint
    # in 02b. Null until then.
    tenant_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "platform.approval_requests.id",
            name="fk_support_impersonations_approval_request",
        ),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    ended_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.platform_users.id", name="fk_support_impersonations_ended_by"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "platform.platform_users.id", name="fk_support_impersonations_revoked_by"
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
