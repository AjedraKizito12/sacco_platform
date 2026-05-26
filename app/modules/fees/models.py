from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class FeeType(AuditableMixin, Base):
    """Fee catalog. One row per fee type. Seeded at provisioning."""

    __tablename__ = "fee_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicable_to: Mapped[str] = mapped_column(Text, nullable=False)
    amount_kind: Mapped[str] = mapped_column(Text, nullable=False, default="fixed")
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    percentage_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    percentage_rate: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_kind: Mapped[str] = mapped_column(Text, nullable=False)
    event_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    gl_income_account_code: Mapped[str] = mapped_column(Text, nullable=False)
    gl_receivable_account_code: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_collection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_fee_types_code"),
        CheckConstraint("amount_kind IN ('fixed', 'percentage', 'tiered')", name="ck_fee_types_amount_kind"),
        CheckConstraint("trigger_kind IN ('event', 'schedule', 'manual')", name="ck_fee_types_trigger_kind"),
        CheckConstraint(
            "applicable_to IN ('member', 'savings_account', 'loan', 'share_account')",
            name="ck_fee_types_applicable_to",
        ),
        CheckConstraint("amount >= 0", name="ck_fee_types_amount"),
        Index("ix_fee_types_is_active_trigger", "is_active", "trigger_kind"),
    )


class FeeAssessment(AuditableMixin, Base):
    """One row per (fee_type, target, period). Idempotent via unique constraint."""

    __tablename__ = "fee_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fee_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_types.id", name="fk_fa_fee_type"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="assessed")
    assessed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    waived_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    waiver_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id", name="fk_fa_journal"), nullable=False
    )
    triggered_by_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "fee_type_id", "target_type", "target_id", "period_start",
            name="uq_fee_assessments_idempotency",
        ),
        CheckConstraint(
            "status IN ('assessed', 'partially_paid', 'paid', 'waived', 'cancelled')",
            name="ck_fee_assessments_status",
        ),
        CheckConstraint("amount > 0", name="ck_fee_assessments_amount"),
        Index("ix_fa_status", "status"),
        Index("ix_fa_target", "target_type", "target_id"),
        Index("ix_fa_fee_type_status", "fee_type_id", "status"),
    )


class FeeCollection(AuditableMixin, Base):
    """One row per payment toward an assessment. Append-only."""

    __tablename__ = "fee_collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fee_assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fee_assessments.id", name="fk_fc_assessment"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    collected_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id", name="fk_fc_journal"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_module: Mapped[str] = mapped_column(Text, nullable=False, default="fees")
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_fc_idempotency_key"),
        CheckConstraint("amount > 0", name="ck_fc_amount"),
        CheckConstraint(
            "method IN ('savings_deduction', 'cash', 'journal_voucher')",
            name="ck_fc_method",
        ),
        Index("ix_fc_assessment_id", "fee_assessment_id"),
    )
