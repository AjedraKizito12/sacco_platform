"""Create fee tables; extend savings_transactions for system-initiated transactions.

fee_types        — fee catalog (seeded at provisioning)
fee_assessments  — one row per (fee_type, target, period); idempotency via unique constraint
fee_collections  — one row per payment toward an assessment; append-only
savings_transactions — add source_module, source_id, reason; extend transaction_type CHECK

Revision: 009
Depends on: 008
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── savings_transactions: drop old CHECK, add new columns, re-add CHECK ────
    op.drop_constraint("ck_savtx_transaction_type", "savings_transactions")
    op.add_column("savings_transactions", sa.Column("source_module", sa.Text(), nullable=True))
    op.add_column("savings_transactions", sa.Column("source_id", sa.UUID(), nullable=True))
    op.add_column("savings_transactions", sa.Column("reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_savtx_transaction_type",
        "savings_transactions",
        "transaction_type IN ('deposit', 'withdrawal', 'SYSTEM_DEBIT', 'SYSTEM_CREDIT')",
    )
    op.create_check_constraint(
        "ck_savtx_reason",
        "savings_transactions",
        "reason IS NULL OR reason IN ('FEE_COLLECTION', 'LOAN_REPAYMENT', "
        "'LOAN_DISBURSEMENT', 'REFUND', 'RECEIVABLE_RECOVERY')",
    )
    op.create_index("ix_savtx_source_module", "savings_transactions", ["source_module"],
                    postgresql_where=sa.text("source_module IS NOT NULL"))

    # ── fee_types ─────────────────────────────────────────────────────────────
    op.create_table(
        "fee_types",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("applicable_to", sa.Text(), nullable=False),
        sa.Column("amount_kind", sa.Text(), nullable=False, server_default="fixed"),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("percentage_basis", sa.Text(), nullable=True),
        sa.Column("percentage_rate", sa.Numeric(19, 4), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("trigger_kind", sa.Text(), nullable=False),
        sa.Column("event_name", sa.Text(), nullable=True),
        sa.Column("schedule_config", JSONB(), nullable=True),
        sa.Column("gl_income_account_code", sa.Text(), nullable=False),
        sa.Column("gl_receivable_account_code", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("requires_collection", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("code", name="uq_fee_types_code"),
        sa.CheckConstraint("amount_kind IN ('fixed', 'percentage', 'tiered')", name="ck_fee_types_amount_kind"),
        sa.CheckConstraint("trigger_kind IN ('event', 'schedule', 'manual')", name="ck_fee_types_trigger_kind"),
        sa.CheckConstraint(
            "applicable_to IN ('member', 'savings_account', 'loan', 'share_account')",
            name="ck_fee_types_applicable_to",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_fee_types_amount"),
    )
    op.create_index("ix_fee_types_is_active_trigger", "fee_types", ["is_active", "trigger_kind"])
    op.create_index("ix_fee_types_event_name", "fee_types", ["event_name"],
                    postgresql_where=sa.text("event_name IS NOT NULL"))

    # ── fee_assessments ───────────────────────────────────────────────────────
    op.create_table(
        "fee_assessments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("fee_type_id", sa.UUID(), sa.ForeignKey("fee_types.id", name="fk_fa_fee_type"), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="assessed"),
        sa.Column("assessed_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("due_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("waived_by", sa.UUID(), nullable=True),
        sa.Column("waiver_reason", sa.Text(), nullable=True),
        sa.Column("journal_entry_id", sa.UUID(), sa.ForeignKey("journal_entries.id", name="fk_fa_journal"), nullable=False),
        sa.Column("triggered_by_event_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "fee_type_id", "target_type", "target_id", "period_start",
            name="uq_fee_assessments_idempotency",
        ),
        sa.CheckConstraint(
            "status IN ('assessed', 'partially_paid', 'paid', 'waived', 'cancelled')",
            name="ck_fee_assessments_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_fee_assessments_amount"),
        sa.CheckConstraint(
            "target_type IN ('member', 'savings_account', 'loan', 'share_account')",
            name="ck_fee_assessments_target_type",
        ),
    )
    op.create_index("ix_fa_status", "fee_assessments", ["status"])
    op.create_index("ix_fa_target", "fee_assessments", ["target_type", "target_id"])
    op.create_index("ix_fa_fee_type_status", "fee_assessments", ["fee_type_id", "status"])

    # ── fee_collections ───────────────────────────────────────────────────────
    op.create_table(
        "fee_collections",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "fee_assessment_id", sa.UUID(),
            sa.ForeignKey("fee_assessments.id", name="fk_fc_assessment"), nullable=False,
        ),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("collected_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("collected_by", sa.UUID(), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), sa.ForeignKey("journal_entries.id", name="fk_fc_journal"), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("source_module", sa.Text(), nullable=False, server_default="fees"),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_fc_idempotency_key"),
        sa.CheckConstraint("amount > 0", name="ck_fc_amount"),
        sa.CheckConstraint(
            "method IN ('savings_deduction', 'cash', 'journal_voucher')",
            name="ck_fc_method",
        ),
    )
    op.create_index("ix_fc_assessment_id", "fee_collections", ["fee_assessment_id"])


def downgrade() -> None:
    op.drop_table("fee_collections")
    op.drop_table("fee_assessments")
    op.drop_table("fee_types")
    op.drop_constraint("ck_savtx_reason", "savings_transactions")
    op.drop_index("ix_savtx_source_module", "savings_transactions")
    op.drop_constraint("ck_savtx_transaction_type", "savings_transactions")
    op.drop_column("savings_transactions", "reason")
    op.drop_column("savings_transactions", "source_id")
    op.drop_column("savings_transactions", "source_module")
    op.create_check_constraint(
        "ck_savtx_transaction_type",
        "savings_transactions",
        "transaction_type IN ('deposit', 'withdrawal')",
    )
