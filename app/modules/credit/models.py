# app/modules/credit/models.py
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class LoanProduct(AuditableMixin, Base):
    """Loan product configuration. Terms are snapshotted onto loans at disbursement.

    No schema= — resolved at runtime via SET LOCAL search_path.
    """

    __tablename__ = "loan_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    interest_method: Mapped[str] = mapped_column(Text, nullable=False)
    annual_interest_rate: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    repayment_frequency: Mapped[str] = mapped_column(Text, nullable=False)
    max_term_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    min_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    max_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    disbursement_destinations: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    repayment_allocation: Mapped[str] = mapped_column(Text, nullable=False, default="INTEREST_PRINCIPAL")
    gl_principal_receivable_code: Mapped[str] = mapped_column(Text, nullable=False)
    gl_interest_receivable_code: Mapped[str] = mapped_column(Text, nullable=False)
    gl_interest_income_code: Mapped[str] = mapped_column(Text, nullable=False)
    gl_loan_loss_expense_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    penalty_fee_type_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    write_off_threshold: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    required_guarantors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("interest_method IN ('flat', 'reducing_balance')", name="ck_lp_interest_method"),
        CheckConstraint(
            "repayment_frequency IN ('weekly', 'biweekly', 'monthly', 'quarterly', 'lump_sum')",
            name="ck_lp_repayment_frequency",
        ),
        CheckConstraint("annual_interest_rate >= 0", name="ck_lp_annual_rate"),
        CheckConstraint("min_amount > 0", name="ck_lp_min_amount"),
        CheckConstraint("max_amount >= min_amount", name="ck_lp_max_gte_min"),
        CheckConstraint("max_term_periods > 0", name="ck_lp_max_term"),
        CheckConstraint("required_approvals >= 1", name="ck_lp_required_approvals"),
        CheckConstraint("write_off_threshold >= 0", name="ck_lp_write_off_threshold"),
        CheckConstraint("repayment_allocation IN ('INTEREST_PRINCIPAL')", name="ck_lp_repayment_allocation"),
        CheckConstraint("required_guarantors >= 0", name="ck_lp_required_guarantors"),
        Index("ix_lp_is_active", "is_active"),
    )


class LoanApplication(AuditableMixin, Base):
    """Loan application. Moves through lifecycle via ApprovalService.

  status progression: submitted → under_review → approved | rejected | withdrawn
  approved_amount / approved_term_periods may differ from requested values.
  """

    __tablename__ = "loan_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_products.id", name="fk_la_product"), nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    requested_term_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    disbursement_destination: Mapped[str] = mapped_column(Text, nullable=False)
    disbursement_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="submitted")
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    approved_term_periods: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_la_idempotency_key"),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'under_review', 'approved', 'rejected', "
            "'withdrawn', 'cancelled', 'disbursed')",
            name="ck_la_status",
        ),
        CheckConstraint(
            "disbursement_destination IN ('member_savings', 'cash', 'internal_gl')",
            name="ck_la_disbursement_destination",
        ),
        CheckConstraint("requested_amount > 0", name="ck_la_requested_amount"),
        CheckConstraint("requested_term_periods > 0", name="ck_la_requested_term"),
        Index("ix_la_member_id", "member_id"),
        Index("ix_la_status", "status"),
        Index("ix_la_loan_product_id", "loan_product_id"),
    )


class Loan(AuditableMixin, Base):
    """Active loan. Created at disbursement. Product terms snapshotted at creation.

    Balance snapshot columns (outstanding_principal, accrued_interest, accrued_penalties,
    total_paid_*, total_written_off) are the authoritative source for operational balance
    queries. GL is authoritative for accounting reports.

    SINGLE-WRITER: all snapshot mutations happen inside app/modules/credit/services/
    in the same DB transaction as the GL post. See CLAUDE.md credit module contracts.
    """

    __tablename__ = "loans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_reference: Mapped[str] = mapped_column(Text, nullable=False)
    loan_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_applications.id", name="fk_ln_application"), nullable=False
    )
    loan_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_products.id", name="fk_ln_product"), nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # ── Snapshotted product terms ──────────────────────────────────────────────
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    interest_method: Mapped[str] = mapped_column(Text, nullable=False)
    annual_interest_rate: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    repayment_frequency: Mapped[str] = mapped_column(Text, nullable=False)
    term_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    repayment_allocation: Mapped[str] = mapped_column(Text, nullable=False)
    disbursement_destination: Mapped[str] = mapped_column(Text, nullable=False)
    disbursement_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # ── Snapshotted GL account IDs ─────────────────────────────────────────────
    gl_principal_receivable_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gl_interest_receivable_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gl_interest_income_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gl_disbursement_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gl_loan_loss_expense_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # ── Balance snapshot ───────────────────────────────────────────────────────
    outstanding_principal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    accrued_interest: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    accrued_penalties: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    total_paid_principal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    total_paid_interest: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    total_paid_penalties: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    total_written_off: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    last_repayment_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_repayment_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    # ── Dates ─────────────────────────────────────────────────────────────────
    disbursed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    first_repayment_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    disbursed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("loan_reference", name="uq_ln_loan_reference"),
        UniqueConstraint("loan_application_id", name="uq_ln_application_id"),
        UniqueConstraint("idempotency_key", name="uq_ln_idempotency_key"),
        CheckConstraint(
            "status IN ('disbursing', 'disbursed', 'in_arrears', 'closed', 'written_off')",
            name="ck_ln_status",
        ),
        CheckConstraint("outstanding_principal >= 0", name="ck_ln_outstanding_principal"),
        CheckConstraint("accrued_interest >= 0", name="ck_ln_accrued_interest"),
        CheckConstraint("accrued_penalties >= 0", name="ck_ln_accrued_penalties"),
        CheckConstraint("principal_amount > 0", name="ck_ln_principal_amount"),
        Index("ix_ln_member_id", "member_id"),
        Index("ix_ln_status", "status"),
        Index("ix_ln_loan_product_id", "loan_product_id"),
    )


class LoanInstallment(Base):
    """One row per scheduled repayment period. Append-only at disbursement;
    principal_paid / interest_paid / status / paid_at are updated by repayment service.

    No AuditableMixin — financial append-only table (CLAUDE.md rule 4).
    """

    __tablename__ = "loan_installments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", name="fk_li_loan"), nullable=False
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    principal_due: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    interest_due: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    total_due: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    principal_paid: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    interest_paid: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    restructuring_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loan_restructurings.id", name="fk_li_restructuring"),
        nullable=True,
    )
    is_superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'partial', 'paid', 'overdue')", name="ck_li_status"),
        CheckConstraint("principal_due >= 0", name="ck_li_principal_due"),
        CheckConstraint("interest_due >= 0", name="ck_li_interest_due"),
        CheckConstraint("period_number >= 1", name="ck_li_period_number"),
        Index("ix_li_loan_id", "loan_id"),
        Index("ix_li_due_date_status", "due_date", "status"),
        Index("ix_li_restructuring_id", "restructuring_id"),
        Index("ix_li_loan_active", "loan_id", postgresql_where=text("NOT is_superseded")),
    )


class LoanRepayment(Base):
    """One row per repayment capture. Append-only."""

    __tablename__ = "loan_repayments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", name="fk_lr_loan"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    principal_applied: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    interest_applied: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    penalties_applied: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    overpayment: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    payment_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id", name="fk_lr_journal"), nullable=False
    )
    posted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    narration: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_lr_idempotency_key"),
        CheckConstraint("amount > 0", name="ck_lr_amount"),
        CheckConstraint("principal_applied >= 0", name="ck_lr_principal_applied"),
        CheckConstraint("interest_applied >= 0", name="ck_lr_interest_applied"),
        CheckConstraint("penalties_applied >= 0", name="ck_lr_penalties_applied"),
        CheckConstraint("overpayment >= 0", name="ck_lr_overpayment"),
        Index("ix_lr_loan_id", "loan_id"),
    )


class LoanGuarantor(AuditableMixin, Base):
    """One guarantor nomination per application. Carries through to the active loan."""

    __tablename__ = "loan_guarantors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_applications.id", name="fk_lg_application"), nullable=False
    )
    loan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", name="fk_lg_loan"), nullable=True
    )
    guarantor_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    guaranteed_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="nominated")
    consented_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_lg_idempotency_key"),
        UniqueConstraint("loan_application_id", "guarantor_member_id", name="uq_lg_application_member"),
        CheckConstraint("status IN ('nominated', 'accepted', 'declined', 'released')", name="ck_lg_status"),
        CheckConstraint("guaranteed_amount > 0", name="ck_lg_guaranteed_amount"),
        Index("ix_lg_loan_application_id", "loan_application_id"),
        Index("ix_lg_guarantor_member_id", "guarantor_member_id"),
        Index("ix_lg_loan_id", "loan_id"),
    )


class LoanGuarantorLien(Base):
    """Live lien against a guarantor's savings account."""

    __tablename__ = "loan_guarantor_liens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_guarantor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_guarantors.id", name="fk_lgl_guarantor"), nullable=False
    )
    savings_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    original_lien: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    current_lien: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("original_lien > 0", name="ck_lgl_original_lien"),
        CheckConstraint("current_lien >= 0", name="ck_lgl_current_lien"),
        Index("ix_lgl_loan_guarantor_id", "loan_guarantor_id"),
        Index(
            "ix_lgl_savings_account_active",
            "savings_account_id",
            "is_active",
            postgresql_where=text("is_active = true"),
        ),
    )


class LoanRestructuring(Base):
    """One record per executed restructuring event. Append-only."""

    __tablename__ = "loan_restructurings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", name="fk_lrs_loan"), nullable=False
    )
    restructuring_type: Mapped[str] = mapped_column(Text, nullable=False)
    periods_added: Mapped[int] = mapped_column(Integer, nullable=False)
    new_term_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    new_maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    executed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_lrs_idempotency_key"),
        CheckConstraint(
            "restructuring_type IN ('term_extension', 'payment_holiday')", name="ck_lrs_type"
        ),
        CheckConstraint("periods_added >= 1", name="ck_lrs_periods_added"),
        Index("ix_lrs_loan_id", "loan_id"),
    )


class PayrollBatch(AuditableMixin, Base):
    """One row per payroll batch submission."""

    __tablename__ = "payroll_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending_review")
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    unmatched_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    source_format: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("reference", name="uq_pb_reference"),
        UniqueConstraint("idempotency_key", name="uq_pb_idempotency_key"),
        CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'applied')", name="ck_pb_status"
        ),
        CheckConstraint("source_format IN ('csv', 'json')", name="ck_pb_source_format"),
    )


class PayrollBatchLine(Base):
    """One row per member in a payroll batch."""

    __tablename__ = "payroll_batch_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payroll_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payroll_batches.id", name="fk_pbl_batch"), nullable=False
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    raw_member_ref: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    loan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="unmatched")
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    repayment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('matched', 'unmatched', 'applied', 'error')", name="ck_pbl_status"
        ),
        CheckConstraint("amount > 0", name="ck_pbl_amount"),
        Index("ix_pbl_payroll_batch_id", "payroll_batch_id"),
        Index("ix_pbl_loan_id", "loan_id"),
    )
