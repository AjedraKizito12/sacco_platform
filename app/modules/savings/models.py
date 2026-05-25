from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class SavingsProduct(AuditableMixin, Base):
    """A savings product offered by the SACCO (e.g., 'Regular Savings').

    liability_account_id — UUID of the liability ChartOfAccount that
        receives credits on deposit and debits on withdrawal.
    No schema= — resolved at runtime via SET LOCAL search_path.
    """

    __tablename__ = "savings_products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    minimum_balance: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, default=Decimal("0")
    )
    # UUID of the liability ChartOfAccount — FK omitted intentionally (cross-module).
    liability_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
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
        CheckConstraint("interest_rate >= 0", name="ck_savings_products_interest_rate"),
        CheckConstraint("minimum_balance >= 0", name="ck_savings_products_min_balance"),
        Index("ix_savings_products_is_active", "is_active"),
    )


class SavingsAccount(AuditableMixin, Base):
    """One savings account per (member, product) pair.

    Product terms are snapshotted at open time — never reference live product
    config for historical records (CLAUDE.md rule 10).
    Balance is NOT stored — derive from SavingsTransaction aggregates.
    """

    __tablename__ = "savings_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", name="fk_sa_member"),
        nullable=False,
    )
    savings_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("savings_products.id", name="fk_sa_product"),
        nullable=False,
    )
    # Snapshotted product terms — immutable after account open.
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    minimum_balance: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    liability_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
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
        UniqueConstraint("member_id", "savings_product_id", name="uq_sa_member_product"),
        Index("ix_sa_member_id", "member_id"),
        Index("ix_sa_savings_product_id", "savings_product_id"),
    )


class SavingsTransaction(Base):
    """Append-only record of each deposit or withdrawal.

    Never updated or deleted. Reversals = new entries.
    journal_entry_id — FK to the GL journal entry posted at the same time.
    idempotency_key — unique per operation; prevents double-posting on retry.
    No AuditableMixin — append-only financial table (CLAUDE.md rule 4).
    """

    __tablename__ = "savings_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    savings_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("savings_accounts.id", name="fk_savtx_account"),
        nullable=False,
    )
    transaction_type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    narration: Mapped[str | None] = mapped_column(Text, nullable=True)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", name="fk_savtx_journal"),
        nullable=False,
    )
    posted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_savtx_idempotency_key"),
        CheckConstraint(
            "transaction_type IN ('deposit', 'withdrawal')",
            name="ck_savtx_transaction_type",
        ),
        CheckConstraint("amount > 0", name="ck_savtx_amount_positive"),
        Index("ix_savtx_savings_account_id", "savings_account_id"),
        Index("ix_savtx_posted_at", "posted_at"),
    )
