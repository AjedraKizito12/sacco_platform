from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class ShareProduct(AuditableMixin, Base):
    """A share class offered by the SACCO (e.g., 'Ordinary Shares').

    par_value — face value per share in the tenant's currency.
    share_capital_account_id — UUID of the equity ChartOfAccount that
        receives credits on purchase and debits on redemption.
    Mutable: AuditableMixin writes audit_log on every change.
    No schema= — resolved at runtime via SET LOCAL search_path.
    """

    __tablename__ = "share_products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    par_value: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    minimum_shares: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    maximum_shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # UUID of the equity ChartOfAccount — FK omitted intentionally (cross-module).
    share_capital_account_id: Mapped[uuid.UUID] = mapped_column(
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
        CheckConstraint("par_value > 0", name="ck_share_products_par_value_positive"),
        CheckConstraint("minimum_shares >= 1", name="ck_share_products_min_shares"),
        CheckConstraint(
            "maximum_shares IS NULL OR maximum_shares >= minimum_shares",
            name="ck_share_products_max_shares",
        ),
        Index("ix_share_products_is_active", "is_active"),
    )


class MemberShareAccount(AuditableMixin, Base):
    """One share account per (member, product) pair.

    Balance is NOT stored here — derive it from ShareTransaction aggregates.
    member_id — UUID FK to members.id (same tenant schema).
    Mutable: AuditableMixin records account open events.
    """

    __tablename__ = "member_share_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.id", name="fk_msa_member"),
        nullable=False,
    )
    share_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("share_products.id", name="fk_msa_product"),
        nullable=False,
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
        UniqueConstraint("member_id", "share_product_id", name="uq_msa_member_product"),
        Index("ix_msa_member_id", "member_id"),
        Index("ix_msa_share_product_id", "share_product_id"),
    )


class ShareTransaction(Base):
    """Append-only record of each share purchase or redemption.

    Never updated or deleted. Reversals = new redemption entries.
    journal_entry_id — FK to the GL journal entry posted at the same time.
    idempotency_key — unique per operation; prevents double-posting on retry.
    """

    __tablename__ = "share_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    share_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("member_share_accounts.id", name="fk_st_share_account"),
        nullable=False,
    )
    transaction_type: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("journal_entries.id", name="fk_st_journal_entry"),
        nullable=False,
    )
    posted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_st_idempotency_key"),
        CheckConstraint(
            "transaction_type IN ('purchase', 'redemption')",
            name="ck_st_transaction_type",
        ),
        CheckConstraint("quantity > 0", name="ck_st_quantity_positive"),
        CheckConstraint("amount > 0", name="ck_st_amount_positive"),
        Index("ix_st_share_account_id", "share_account_id"),
        Index("ix_st_posted_at", "posted_at"),
    )
