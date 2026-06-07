"""SQLAlchemy models for platform.tenants and platform.platform_users."""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — used at runtime by SQLAlchemy

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'pending','provisioning','active','suspended',"
            "'failed','deprovisioning','archived')",
            name="ck_tenants_status",
        ),
        CheckConstraint(
            "subscription_status IN ("
            "'pending','trialing','active','past_due','suspended','cancelled')",
            name="ck_tenants_subscription_status",
        ),
        Index("ix_platform_tenants_slug", "slug"),
        Index("ix_platform_tenants_status", "status"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    schema_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subscription_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    current_subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform.subscriptions.id", name="fk_tenants_current_subscription"),
        nullable=True,
    )
    provisioning_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provisioning_started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    provisioning_completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    seed_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class PlatformUser(AuditableMixin, Base):
    __tablename__ = "platform_users"
    __table_args__ = (
        Index("ix_platform_users_email", "email"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="support")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
