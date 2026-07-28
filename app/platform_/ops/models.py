"""Operational telemetry for the backup/restore pipeline (platform schema).

These tables are written by the backup container's scripts (via psql) and by
OpsService. They are NOT audited business state — no AuditableMixin.
"""
from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — runtime use by SQLAlchemy

from sqlalchemy import CheckConstraint, Index, Integer, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class BackupRun(Base):
    __tablename__ = "backup_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','succeeded','failed')",
            name="ck_backup_runs_status",
        ),
        CheckConstraint(
            "backup_type IN ('full','incr','diff')",
            name="ck_backup_runs_type",
        ),
        Index("ix_platform_backup_runs_created_at", "created_at"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    backup_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    repo_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wal_lag_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


class BackupVerification(Base):
    __tablename__ = "backup_verifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested','running','passed','failed')",
            name="ck_backup_verifications_status",
        ),
        Index("ix_platform_backup_verifications_created_at", "created_at"),
        Index("ix_platform_backup_verifications_status", "status"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="requested")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
