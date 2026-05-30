# app/modules/reporting/models.py
"""SQLAlchemy models for the reporting module.

ReportRun — audit record for each nightly materialization job.
Five summary tables — truncated and repopulated on each run.
No schema= on any model: resolved at runtime via SET LOCAL search_path.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReportRun(Base):
    """One row per (report_type, materialization run). Tracks status and timing."""

    __tablename__ = "report_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('running', 'done', 'failed')", name="ck_rr_status"),
        CheckConstraint(
            "report_type IN ('trial_balance', 'loan_portfolio', 'income_statement', "
            "'savings_statement', 'fee_collection')",
            name="ck_rr_report_type",
        ),
        Index("ix_rr_type_date", "report_type", text("as_of_date DESC")),
    )


class ReportTrialBalanceLine(Base):
    """One row per GL account per trial balance run."""

    __tablename__ = "report_trial_balance_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_runs.id", name="fk_rtbl_run"), nullable=False
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_name: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    debit_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    credit_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)

    __table_args__ = (Index("ix_rtbl_run_id", "report_run_id"),)


class ReportLoanPortfolioRow(Base):
    """One row per loan per portfolio run."""

    __tablename__ = "report_loan_portfolio_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_runs.id", name="fk_rlpr_run"), nullable=False
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    loan_reference: Mapped[str] = mapped_column(Text, nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    disbursed_at: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    outstanding_principal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    accrued_interest: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    total_written_off: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    days_in_arrears: Mapped[int] = mapped_column(Integer, nullable=False)
    aging_bucket: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "aging_bucket IN ('current', '1_30', '31_60', '61_90', '90_plus')",
            name="ck_rlpr_aging_bucket",
        ),
        Index("ix_rlpr_run_id", "report_run_id"),
    )


class ReportIncomeStatementLine(Base):
    """One row per income/expense GL account per income statement run."""

    __tablename__ = "report_income_statement_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_runs.id", name="fk_risl_run"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_name: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    debit_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    credit_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    net_movement: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)

    __table_args__ = (Index("ix_risl_run_id", "report_run_id"),)


class ReportSavingsStatementLine(Base):
    """One row per savings transaction per savings statement run."""

    __tablename__ = "report_savings_statement_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_runs.id", name="fk_rssl_run"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    savings_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    transaction_type: Mapped[str] = mapped_column(Text, nullable=False)
    narration: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    running_balance: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)

    __table_args__ = (Index("ix_rssl_run_id", "report_run_id"),)


class ReportFeeCollectionRow(Base):
    """One row per fee type per fee collection run."""

    __tablename__ = "report_fee_collection_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_runs.id", name="fk_rfcr_run"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    fee_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fee_type_name: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    assessed_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    collected_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    outstanding_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    waived_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)

    __table_args__ = (Index("ix_rfcr_run_id", "report_run_id"),)
