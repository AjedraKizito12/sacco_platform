# alembic/tenant/versions/010_credit_tables.py
"""Credit module: sub-ledger columns on journal_lines; EXTERNAL_CREDIT/EXTERNAL_DEBIT
on savings_transactions; loan_products, loan_applications, loans, loan_installments,
loan_repayments tables; loan_number_seq sequence.

Revision: 010
Depends on: 009
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── journal_lines: add sub-ledger tagging columns ─────────────────────────
    op.add_column("journal_lines", sa.Column("sub_ledger_type", sa.Text(), nullable=True))
    op.add_column("journal_lines", sa.Column("sub_ledger_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_jl_sub_ledger",
        "journal_lines",
        ["sub_ledger_type", "sub_ledger_id"],
        postgresql_where=sa.text("sub_ledger_id IS NOT NULL"),
    )

    # ── savings_transactions: extend transaction_type CHECK ───────────────────
    op.drop_constraint("ck_savtx_transaction_type", "savings_transactions")
    op.create_check_constraint(
        "ck_savtx_transaction_type",
        "savings_transactions",
        "transaction_type IN ('deposit', 'withdrawal', 'SYSTEM_DEBIT', 'SYSTEM_CREDIT',"
        " 'EXTERNAL_CREDIT', 'EXTERNAL_DEBIT')",
    )

    # ── loan_products ─────────────────────────────────────────────────────────
    op.create_table(
        "loan_products",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("interest_method", sa.Text(), nullable=False),
        sa.Column("annual_interest_rate", sa.Numeric(19, 4), nullable=False),
        sa.Column("repayment_frequency", sa.Text(), nullable=False),
        sa.Column("max_term_periods", sa.Integer(), nullable=False),
        sa.Column("min_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("max_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("disbursement_destinations", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("repayment_allocation", sa.Text(), nullable=False, server_default="INTEREST_PRINCIPAL"),
        sa.Column("gl_principal_receivable_code", sa.Text(), nullable=False),
        sa.Column("gl_interest_receivable_code", sa.Text(), nullable=False),
        sa.Column("gl_interest_income_code", sa.Text(), nullable=False),
        sa.Column("gl_loan_loss_expense_code", sa.Text(), nullable=True),
        sa.Column("penalty_fee_type_code", sa.Text(), nullable=True),
        sa.Column("write_off_threshold", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "interest_method IN ('flat', 'reducing_balance')",
            name="ck_lp_interest_method",
        ),
        sa.CheckConstraint(
            "repayment_frequency IN ('weekly', 'biweekly', 'monthly', 'quarterly', 'lump_sum')",
            name="ck_lp_repayment_frequency",
        ),
        sa.CheckConstraint("annual_interest_rate >= 0", name="ck_lp_annual_rate"),
        sa.CheckConstraint("min_amount > 0", name="ck_lp_min_amount"),
        sa.CheckConstraint("max_amount >= min_amount", name="ck_lp_max_gte_min"),
        sa.CheckConstraint("max_term_periods > 0", name="ck_lp_max_term"),
        sa.CheckConstraint("required_approvals >= 1", name="ck_lp_required_approvals"),
        sa.CheckConstraint("write_off_threshold >= 0", name="ck_lp_write_off_threshold"),
        sa.CheckConstraint(
            "repayment_allocation IN ('INTEREST_PRINCIPAL')",
            name="ck_lp_repayment_allocation",
        ),
    )
    op.create_index("ix_lp_is_active", "loan_products", ["is_active"])

    # ── loan_applications ─────────────────────────────────────────────────────
    op.create_table(
        "loan_applications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_product_id", sa.UUID(), sa.ForeignKey("loan_products.id", name="fk_la_product"), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("requested_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("requested_term_periods", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("disbursement_destination", sa.Text(), nullable=False),
        sa.Column("disbursement_account_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="submitted"),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("approved_amount", sa.Numeric(19, 4), nullable=True),
        sa.Column("approved_term_periods", sa.Integer(), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_la_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'under_review', 'approved', 'rejected', 'withdrawn', 'cancelled', 'disbursed')",
            name="ck_la_status",
        ),
        sa.CheckConstraint(
            "disbursement_destination IN ('member_savings', 'cash', 'internal_gl')",
            name="ck_la_disbursement_destination",
        ),
        sa.CheckConstraint("requested_amount > 0", name="ck_la_requested_amount"),
        sa.CheckConstraint("requested_term_periods > 0", name="ck_la_requested_term"),
    )
    op.create_index("ix_la_member_id", "loan_applications", ["member_id"])
    op.create_index("ix_la_status", "loan_applications", ["status"])
    op.create_index("ix_la_loan_product_id", "loan_applications", ["loan_product_id"])

    # ── loans ─────────────────────────────────────────────────────────────────
    op.create_table(
        "loans",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_reference", sa.Text(), nullable=False),
        sa.Column("loan_application_id", sa.UUID(), sa.ForeignKey("loan_applications.id", name="fk_ln_application"), nullable=False),
        sa.Column("loan_product_id", sa.UUID(), sa.ForeignKey("loan_products.id", name="fk_ln_product"), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        # Snapshotted product terms
        sa.Column("principal_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("interest_method", sa.Text(), nullable=False),
        sa.Column("annual_interest_rate", sa.Numeric(19, 4), nullable=False),
        sa.Column("repayment_frequency", sa.Text(), nullable=False),
        sa.Column("term_periods", sa.Integer(), nullable=False),
        sa.Column("repayment_allocation", sa.Text(), nullable=False),
        sa.Column("disbursement_destination", sa.Text(), nullable=False),
        sa.Column("disbursement_account_id", sa.UUID(), nullable=True),
        # Snapshotted GL account IDs
        sa.Column("gl_principal_receivable_id", sa.UUID(), nullable=False),
        sa.Column("gl_interest_receivable_id", sa.UUID(), nullable=False),
        sa.Column("gl_interest_income_id", sa.UUID(), nullable=False),
        sa.Column("gl_disbursement_account_id", sa.UUID(), nullable=False),
        sa.Column("gl_loan_loss_expense_id", sa.UUID(), nullable=True),
        # Balance snapshot
        sa.Column("outstanding_principal", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("accrued_interest", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("accrued_penalties", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total_paid_principal", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total_paid_interest", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total_paid_penalties", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total_written_off", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("last_repayment_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_repayment_amount", sa.Numeric(19, 4), nullable=True),
        # Dates
        sa.Column("disbursed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("first_repayment_due", sa.Date(), nullable=True),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("disbursed_by", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("loan_reference", name="uq_ln_loan_reference"),
        sa.UniqueConstraint("loan_application_id", name="uq_ln_application_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_ln_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('disbursing', 'disbursed', 'in_arrears', 'closed', 'written_off')",
            name="ck_ln_status",
        ),
        sa.CheckConstraint("outstanding_principal >= 0", name="ck_ln_outstanding_principal"),
        sa.CheckConstraint("accrued_interest >= 0", name="ck_ln_accrued_interest"),
        sa.CheckConstraint("accrued_penalties >= 0", name="ck_ln_accrued_penalties"),
        sa.CheckConstraint("principal_amount > 0", name="ck_ln_principal_amount"),
    )
    op.create_index("ix_ln_member_id", "loans", ["member_id"])
    op.create_index("ix_ln_status", "loans", ["status"])
    op.create_index("ix_ln_loan_product_id", "loans", ["loan_product_id"])

    # ── loan_installments ─────────────────────────────────────────────────────
    op.create_table(
        "loan_installments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_id", sa.UUID(), sa.ForeignKey("loans.id", name="fk_li_loan"), nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("principal_due", sa.Numeric(19, 4), nullable=False),
        sa.Column("interest_due", sa.Numeric(19, 4), nullable=False),
        sa.Column("total_due", sa.Numeric(19, 4), nullable=False),
        sa.Column("principal_paid", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("interest_paid", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("loan_id", "period_number", name="uq_li_loan_period"),
        sa.CheckConstraint(
            "status IN ('pending', 'partial', 'paid', 'overdue')",
            name="ck_li_status",
        ),
        sa.CheckConstraint("principal_due >= 0", name="ck_li_principal_due"),
        sa.CheckConstraint("interest_due >= 0", name="ck_li_interest_due"),
        sa.CheckConstraint("period_number >= 1", name="ck_li_period_number"),
    )
    op.create_index("ix_li_loan_id", "loan_installments", ["loan_id"])
    op.create_index("ix_li_due_date_status", "loan_installments", ["due_date", "status"])

    # ── loan_repayments ───────────────────────────────────────────────────────
    op.create_table(
        "loan_repayments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_id", sa.UUID(), sa.ForeignKey("loans.id", name="fk_lr_loan"), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("principal_applied", sa.Numeric(19, 4), nullable=False),
        sa.Column("interest_applied", sa.Numeric(19, 4), nullable=False),
        sa.Column("penalties_applied", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("overpayment", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("payment_account_id", sa.UUID(), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), sa.ForeignKey("journal_entries.id", name="fk_lr_journal"), nullable=False),
        sa.Column("posted_by", sa.UUID(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_lr_idempotency_key"),
        sa.CheckConstraint("amount > 0", name="ck_lr_amount"),
        sa.CheckConstraint("principal_applied >= 0", name="ck_lr_principal_applied"),
        sa.CheckConstraint("interest_applied >= 0", name="ck_lr_interest_applied"),
        sa.CheckConstraint("penalties_applied >= 0", name="ck_lr_penalties_applied"),
        sa.CheckConstraint("overpayment >= 0", name="ck_lr_overpayment"),
    )
    op.create_index("ix_lr_loan_id", "loan_repayments", ["loan_id"])

    # ── loan_number_seq ───────────────────────────────────────────────────────
    op.execute("CREATE SEQUENCE IF NOT EXISTS loan_number_seq START 1")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS loan_number_seq")
    op.drop_table("loan_repayments")
    op.drop_table("loan_installments")
    op.drop_table("loans")
    op.drop_table("loan_applications")
    op.drop_table("loan_products")
    op.drop_constraint("ck_savtx_transaction_type", "savings_transactions")
    op.create_check_constraint(
        "ck_savtx_transaction_type",
        "savings_transactions",
        "transaction_type IN ('deposit', 'withdrawal', 'SYSTEM_DEBIT', 'SYSTEM_CREDIT')",
    )
    op.drop_index("ix_jl_sub_ledger", "journal_lines")
    op.drop_column("journal_lines", "sub_ledger_id")
    op.drop_column("journal_lines", "sub_ledger_type")
