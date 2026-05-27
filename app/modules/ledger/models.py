from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class ChartOfAccount(AuditableMixin, Base):
    """Mutable account registry. AuditableMixin writes audit_log on insert/update/delete."""

    __tablename__ = "chart_of_accounts"
    # No schema — resolved at runtime via SET LOCAL search_path.

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", name="fk_coa_parent"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="now()", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    parent: Mapped[ChartOfAccount | None] = relationship(
        "ChartOfAccount", remote_side="ChartOfAccount.id", back_populates="children"
    )
    children: Mapped[list[ChartOfAccount]] = relationship(
        "ChartOfAccount", back_populates="parent"
    )
    lines: Mapped[list[JournalLine]] = relationship(
        "JournalLine", back_populates="account", lazy="raise"
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_coa_code"),
        CheckConstraint(
            "account_type IN ('asset', 'liability', 'equity', 'income', 'expense')",
            name="ck_coa_account_type",
        ),
        Index("ix_coa_code", "code"),
        Index("ix_coa_account_type", "account_type"),
    )


class JournalEntry(Base):
    """Append-only journal entry header. Never updated or deleted."""

    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # FK omitted intentionally — actor may be a platform_user (cross-schema) or tenant_user.
    posted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="now()", nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)

    lines: Mapped[list[JournalLine]] = relationship(
        "JournalLine", back_populates="entry", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_je_idempotency_key"),
        Index("ix_je_reference", "reference"),
        Index("ix_je_posted_at", "posted_at"),
    )


class JournalLine(Base):
    """Append-only debit/credit leg. One of debit_amount/credit_amount must be zero."""

    __tablename__ = "journal_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", name="fk_jl_entry"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chart_of_accounts.id", name="fk_jl_account"),
        nullable=False,
    )
    debit_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, server_default="0"
    )
    credit_amount: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, server_default="0"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_ledger_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_ledger_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    entry: Mapped[JournalEntry] = relationship("JournalEntry", back_populates="lines", lazy="raise")
    account: Mapped[ChartOfAccount] = relationship(
        "ChartOfAccount", back_populates="lines", lazy="raise"
    )

    __table_args__ = (
        CheckConstraint(
            "debit_amount >= 0 AND credit_amount >= 0"
            " AND (debit_amount > 0 OR credit_amount > 0)"
            " AND NOT (debit_amount > 0 AND credit_amount > 0)",
            name="ck_jl_amounts",
        ),
        Index("ix_jl_journal_entry_id", "journal_entry_id"),
        Index("ix_jl_account_id", "account_id"),
        Index(
            "ix_jl_sub_ledger",
            "sub_ledger_type",
            "sub_ledger_id",
            postgresql_where=text("sub_ledger_id IS NOT NULL"),
        ),
    )
