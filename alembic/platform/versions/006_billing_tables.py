"""Phase 1 Billing module — 5 platform tables + tenants ALTER.

Revision: 006
Depends on: 005
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscription_plans ─────────────────────────────────────────────────────
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False, server_default="UGX"),
        sa.Column("base_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("per_user_price", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("per_member_price", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("billing_period", sa.Text(), nullable=False),
        sa.Column("member_limit", sa.Integer(), nullable=True),
        sa.Column("user_limit", sa.Integer(), nullable=True),
        sa.Column(
            "features",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("trial_period_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grace_period_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "billing_period IN ('monthly', 'quarterly', 'annual')",
            name="ck_sub_plans_billing_period",
        ),
        sa.UniqueConstraint("code", name="uq_sub_plans_code"),
        schema="platform",
    )
    op.create_index(
        "ix_sub_plans_is_active", "subscription_plans", ["is_active"], schema="platform",
    )

    # ── subscriptions ──────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("current_period_start", sa.Date(), nullable=False),
        sa.Column("current_period_end", sa.Date(), nullable=False),
        sa.Column("grace_period_ends_at", sa.Date(), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("next_billing_date", sa.Date(), nullable=True),
        sa.Column(
            "metadata_json",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["platform.tenants.id"], name="fk_subscriptions_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["platform.subscription_plans.id"], name="fk_subscriptions_plan",
        ),
        sa.CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'suspended', 'cancelled')",
            name="ck_subscriptions_status",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_subscriptions_tenant_status",
        "subscriptions",
        ["tenant_id", "status"],
        schema="platform",
    )
    op.create_index(
        "ix_subscriptions_period_end",
        "subscriptions",
        ["current_period_end"],
        schema="platform",
        postgresql_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
    )
    op.create_index(
        "uq_subscriptions_live_tenant",
        "subscriptions",
        ["tenant_id"],
        unique=True,
        schema="platform",
        postgresql_where=sa.text("status IN ('trialing', 'active', 'past_due')"),
    )

    # ── invoices ───────────────────────────────────────────────────────────────
    op.create_table(
        "invoices",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("invoice_number", sa.Text(), nullable=False),
        sa.Column("subscription_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("billing_period_start", sa.Date(), nullable=False),
        sa.Column("billing_period_end", sa.Date(), nullable=False),
        sa.Column("amount_subtotal", sa.Numeric(19, 4), nullable=False),
        sa.Column("amount_tax", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("amount_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("amount_paid", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.Text(), nullable=False, server_default="UGX"),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("due_at", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("voided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("pdf_storage_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["platform.subscriptions.id"], name="fk_invoices_subscription",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["platform.tenants.id"], name="fk_invoices_tenant",
        ),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_number"),
        sa.CheckConstraint(
            "status IN ('draft', 'issued', 'partial', 'paid', 'overdue', 'void')",
            name="ck_invoices_status",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_invoices_tenant_status",
        "invoices",
        ["tenant_id", "status"],
        schema="platform",
    )
    op.create_index(
        "ix_invoices_due",
        "invoices",
        ["due_at"],
        schema="platform",
        postgresql_where=sa.text("status IN ('issued', 'partial', 'overdue')"),
    )

    # ── invoice_line_items ─────────────────────────────────────────────────────
    op.create_table(
        "invoice_line_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("line_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["platform.invoices.id"],
            ondelete="CASCADE",
            name="fk_invoice_line_items_invoice",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_invoice_line_items_invoice",
        "invoice_line_items",
        ["invoice_id"],
        schema="platform",
    )

    # ── payments ───────────────────────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="UGX"),
        sa.Column("payment_method", sa.Text(), nullable=False),
        sa.Column("external_reference", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.UUID(), nullable=False),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["platform.invoices.id"], name="fk_payments_invoice",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by"],
            ["platform.platform_users.id"],
            name="fk_payments_recorded_by",
        ),
        sa.ForeignKeyConstraint(
            ["approval_request_id"],
            ["platform.approval_requests.id"],
            name="fk_payments_approval",
        ),
        sa.CheckConstraint(
            "payment_method IN ('bank_transfer', 'mobile_money', 'cash', 'cheque')",
            name="ck_payments_payment_method",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')",
            name="ck_payments_status",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_payments_invoice", "payments", ["invoice_id"], schema="platform",
    )

    # ── ALTER platform.tenants ─────────────────────────────────────────────────
    op.add_column(
        "tenants",
        sa.Column(
            "subscription_status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        schema="platform",
    )
    op.add_column(
        "tenants",
        sa.Column("current_subscription_id", sa.UUID(), nullable=True),
        schema="platform",
    )
    op.create_foreign_key(
        "fk_tenants_current_subscription",
        "tenants",
        "subscriptions",
        ["current_subscription_id"],
        ["id"],
        source_schema="platform",
        referent_schema="platform",
    )
    op.create_check_constraint(
        "ck_tenants_subscription_status",
        "tenants",
        "subscription_status IN ('pending', 'trialing', 'active', 'past_due', 'suspended', 'cancelled')",
        schema="platform",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tenants_current_subscription",
        "tenants",
        type_="foreignkey",
        schema="platform",
    )
    op.drop_constraint(
        "ck_tenants_subscription_status", "tenants", type_="check", schema="platform",
    )
    op.drop_column("tenants", "current_subscription_id", schema="platform")
    op.drop_column("tenants", "subscription_status", schema="platform")
    op.drop_table("payments", schema="platform")
    op.drop_table("invoice_line_items", schema="platform")
    op.drop_table("invoices", schema="platform")
    op.drop_table("subscriptions", schema="platform")
    op.drop_table("subscription_plans", schema="platform")
