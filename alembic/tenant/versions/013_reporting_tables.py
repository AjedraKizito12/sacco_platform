# alembic/tenant/versions/013_reporting_tables.py
"""Reporting module: report_runs + 5 summary tables.

Revision: 013
Depends on: 012
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── report_runs ───────────────────────────────────────────────────────────
    op.create_table(
        "report_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_type", sa.Text(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="ck_rr_status",
        ),
        sa.CheckConstraint(
            "report_type IN ('trial_balance', 'loan_portfolio', 'income_statement', 'savings_statement', 'fee_collection')",
            name="ck_rr_report_type",
        ),
    )
    op.create_index(
        "ix_rr_type_date",
        "report_runs",
        ["report_type", sa.text("as_of_date DESC")],
    )

    # ── report_trial_balance_lines ────────────────────────────────────────────
    op.create_table(
        "report_trial_balance_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_run_id", sa.UUID(), sa.ForeignKey("report_runs.id", name="fk_rtbl_run"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("account_code", sa.Text(), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=False),
        sa.Column("account_type", sa.Text(), nullable=False),
        sa.Column("debit_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("credit_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("balance", sa.Numeric(19, 4), nullable=False),
    )
    op.create_index("ix_rtbl_run_id", "report_trial_balance_lines", ["report_run_id"])

    # ── report_loan_portfolio_rows ────────────────────────────────────────────
    op.create_table(
        "report_loan_portfolio_rows",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_run_id", sa.UUID(), sa.ForeignKey("report_runs.id", name="fk_rlpr_run"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("loan_id", sa.UUID(), nullable=False),
        sa.Column("loan_reference", sa.Text(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("disbursed_at", sa.Date(), nullable=False),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("outstanding_principal", sa.Numeric(19, 4), nullable=False),
        sa.Column("accrued_interest", sa.Numeric(19, 4), nullable=False),
        sa.Column("total_written_off", sa.Numeric(19, 4), nullable=False),
        sa.Column("days_in_arrears", sa.Integer(), nullable=False),
        sa.Column("aging_bucket", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "aging_bucket IN ('current', '1_30', '31_60', '61_90', '90_plus')",
            name="ck_rlpr_aging_bucket",
        ),
    )
    op.create_index("ix_rlpr_run_id", "report_loan_portfolio_rows", ["report_run_id"])

    # ── report_income_statement_lines ─────────────────────────────────────────
    op.create_table(
        "report_income_statement_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_run_id", sa.UUID(), sa.ForeignKey("report_runs.id", name="fk_risl_run"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("account_code", sa.Text(), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=False),
        sa.Column("account_type", sa.Text(), nullable=False),
        sa.Column("debit_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("credit_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("net_movement", sa.Numeric(19, 4), nullable=False),
    )
    op.create_index("ix_risl_run_id", "report_income_statement_lines", ["report_run_id"])

    # ── report_savings_statement_lines ────────────────────────────────────────
    op.create_table(
        "report_savings_statement_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_run_id", sa.UUID(), sa.ForeignKey("report_runs.id", name="fk_rssl_run"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("savings_account_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("posted_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("transaction_type", sa.Text(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("running_balance", sa.Numeric(19, 4), nullable=False),
    )
    op.create_index("ix_rssl_run_id", "report_savings_statement_lines", ["report_run_id"])

    # ── report_fee_collection_rows ────────────────────────────────────────────
    op.create_table(
        "report_fee_collection_rows",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_run_id", sa.UUID(), sa.ForeignKey("report_runs.id", name="fk_rfcr_run"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("fee_type_id", sa.UUID(), nullable=False),
        sa.Column("fee_type_name", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("assessed_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("collected_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("outstanding_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("waived_total", sa.Numeric(19, 4), nullable=False),
    )
    op.create_index("ix_rfcr_run_id", "report_fee_collection_rows", ["report_run_id"])


def downgrade() -> None:
    op.drop_table("report_fee_collection_rows")
    op.drop_table("report_savings_statement_lines")
    op.drop_table("report_income_statement_lines")
    op.drop_table("report_loan_portfolio_rows")
    op.drop_table("report_trial_balance_lines")
    op.drop_index("ix_rr_type_date", "report_runs")
    op.drop_table("report_runs")
