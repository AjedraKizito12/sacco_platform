# alembic/tenant/versions/012_credit_v1b_tables.py
"""Credit v1b: guarantors, guarantor liens, restructurings, payroll tables;
add required_guarantors to loan_products; add restructuring_id + is_superseded
to loan_installments; add 'written_off' → 'in_arrears' recovery transition.

Revision: 012
Depends on: 011
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── loan_products: add required_guarantors ────────────────────────────────
    op.add_column(
        "loan_products",
        sa.Column("required_guarantors", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_lp_required_guarantors",
        "loan_products",
        "required_guarantors >= 0",
    )

    # ── loan_guarantors ───────────────────────────────────────────────────────
    op.create_table(
        "loan_guarantors",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_application_id", sa.UUID(), sa.ForeignKey("loan_applications.id", name="fk_lg_application"), nullable=False),
        sa.Column("loan_id", sa.UUID(), sa.ForeignKey("loans.id", name="fk_lg_loan"), nullable=True),
        sa.Column("guarantor_member_id", sa.UUID(), nullable=False),
        sa.Column("guaranteed_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="nominated"),
        sa.Column("consented_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("released_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_lg_idempotency_key"),
        sa.UniqueConstraint("loan_application_id", "guarantor_member_id", name="uq_lg_application_member"),
        sa.CheckConstraint(
            "status IN ('nominated', 'accepted', 'declined', 'released')",
            name="ck_lg_status",
        ),
        sa.CheckConstraint("guaranteed_amount > 0", name="ck_lg_guaranteed_amount"),
    )
    op.create_index("ix_lg_loan_application_id", "loan_guarantors", ["loan_application_id"])
    op.create_index("ix_lg_guarantor_member_id", "loan_guarantors", ["guarantor_member_id"])
    op.create_index("ix_lg_loan_id", "loan_guarantors", ["loan_id"])

    # ── loan_restructurings (before loan_installments FK) ─────────────────────
    op.create_table(
        "loan_restructurings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_id", sa.UUID(), sa.ForeignKey("loans.id", name="fk_lr_loan"), nullable=False),
        sa.Column("restructuring_type", sa.Text(), nullable=False),
        sa.Column("periods_added", sa.Integer(), nullable=False),
        sa.Column("new_term_periods", sa.Integer(), nullable=False),
        sa.Column("new_maturity_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("executed_by", sa.UUID(), nullable=False),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_lrs_idempotency_key"),
        sa.CheckConstraint(
            "restructuring_type IN ('term_extension', 'payment_holiday')",
            name="ck_lrs_type",
        ),
        sa.CheckConstraint("periods_added >= 1", name="ck_lrs_periods_added"),
    )
    op.create_index("ix_lrs_loan_id", "loan_restructurings", ["loan_id"])

    # ── loan_installments: drop old unique constraint, add restructuring columns
    op.drop_constraint("uq_li_loan_period", "loan_installments", type_="unique")
    op.add_column(
        "loan_installments",
        sa.Column("restructuring_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "loan_installments",
        sa.Column("is_superseded", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_foreign_key(
        "fk_li_restructuring",
        "loan_installments",
        "loan_restructurings",
        ["restructuring_id"],
        ["id"],
    )
    op.create_index("ix_li_restructuring_id", "loan_installments", ["restructuring_id"])
    op.create_index(
        "ix_li_loan_active",
        "loan_installments",
        ["loan_id"],
        postgresql_where=sa.text("NOT is_superseded"),
    )

    # ── loan_guarantor_liens ──────────────────────────────────────────────────
    op.create_table(
        "loan_guarantor_liens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_guarantor_id", sa.UUID(), sa.ForeignKey("loan_guarantors.id", name="fk_lgl_guarantor"), nullable=False),
        sa.Column("savings_account_id", sa.UUID(), nullable=False),
        sa.Column("original_lien", sa.Numeric(19, 4), nullable=False),
        sa.Column("current_lien", sa.Numeric(19, 4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("original_lien > 0", name="ck_lgl_original_lien"),
        sa.CheckConstraint("current_lien >= 0", name="ck_lgl_current_lien"),
    )
    op.create_index("ix_lgl_loan_guarantor_id", "loan_guarantor_liens", ["loan_guarantor_id"])
    op.create_index(
        "ix_lgl_savings_account_active",
        "loan_guarantor_liens",
        ["savings_account_id", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ── payroll_batches ───────────────────────────────────────────────────────
    op.create_table(
        "payroll_batches",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_review"),
        sa.Column("submitted_by", sa.UUID(), nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("matched_rows", sa.Integer(), nullable=False),
        sa.Column("unmatched_rows", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("source_format", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("reference", name="uq_pb_reference"),
        sa.UniqueConstraint("idempotency_key", name="uq_pb_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'applied')",
            name="ck_pb_status",
        ),
        sa.CheckConstraint("source_format IN ('csv', 'json')", name="ck_pb_source_format"),
    )

    # ── payroll_batch_lines ───────────────────────────────────────────────────
    op.create_table(
        "payroll_batch_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("payroll_batch_id", sa.UUID(), sa.ForeignKey("payroll_batches.id", name="fk_pbl_batch"), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=True),
        sa.Column("raw_member_ref", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("loan_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="unmatched"),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("repayment_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('matched', 'unmatched', 'applied', 'error')",
            name="ck_pbl_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_pbl_amount"),
    )
    op.create_index("ix_pbl_payroll_batch_id", "payroll_batch_lines", ["payroll_batch_id"])
    op.create_index("ix_pbl_loan_id", "payroll_batch_lines", ["loan_id"])

    # ── payroll_batch_number_seq ──────────────────────────────────────────────
    op.execute("CREATE SEQUENCE IF NOT EXISTS payroll_batch_number_seq START 1")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS payroll_batch_number_seq")
    op.drop_table("payroll_batch_lines")
    op.drop_table("payroll_batches")
    op.drop_index("ix_lgl_savings_account_active", "loan_guarantor_liens")
    op.drop_index("ix_lgl_loan_guarantor_id", "loan_guarantor_liens")
    op.drop_table("loan_guarantor_liens")
    op.drop_constraint("fk_li_restructuring", "loan_installments", type_="foreignkey")
    op.drop_index("ix_li_loan_active", "loan_installments")
    op.drop_index("ix_li_restructuring_id", "loan_installments")
    op.drop_column("loan_installments", "is_superseded")
    op.drop_column("loan_installments", "restructuring_id")
    op.create_unique_constraint("uq_li_loan_period", "loan_installments", ["loan_id", "period_number"])
    op.drop_index("ix_lrs_loan_id", "loan_restructurings")
    op.drop_table("loan_restructurings")
    op.drop_index("ix_lg_loan_id", "loan_guarantors")
    op.drop_index("ix_lg_guarantor_member_id", "loan_guarantors")
    op.drop_index("ix_lg_loan_application_id", "loan_guarantors")
    op.drop_table("loan_guarantors")
    op.drop_constraint("ck_lp_required_guarantors", "loan_products", type_="check")
    op.drop_column("loan_products", "required_guarantors")
