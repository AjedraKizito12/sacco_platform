"""
Create core tables in the tenant schema: audit_log, outbox_events,
processed_events, approval_requests, approval_actions.

Platform and tenant Alembic chains are independent.
Version numbers do not correlate across chains.
001 in platform and 001 in tenant are unrelated migrations.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables are created in the schema set by TENANT_SCHEMA env var (via SET search_path in env.py).
    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_label", sa.Text(), nullable=True),
        sa.Column("before_state", postgresql.JSONB(), nullable=True),
        sa.Column("after_state", postgresql.JSONB(), nullable=True),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.CheckConstraint("operation IN ('insert', 'update', 'delete')", name="ck_audit_log_operation"),
    )
    op.create_index("ix_tenant_audit_log_table_record", "audit_log", ["table_name", "record_id"])
    op.create_index("ix_tenant_audit_log_occurred_at", "audit_log", [sa.text("occurred_at DESC")])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_dead_lettered", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(
        "ix_tenant_outbox_pending",
        "outbox_events",
        ["next_attempt_at"],
        postgresql_where=sa.text("published_at IS NULL AND is_dead_lettered = false"),
    )

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("consumer_name", sa.Text(), nullable=False),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("event_id", "consumer_name"),
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("operation_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("required_approvals", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("execution_result", postgresql.JSONB(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )

    op.create_table(
        "approval_actions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("approval_request_id", sa.UUID(), sa.ForeignKey("approval_requests.id"), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("acted_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.UniqueConstraint("approval_request_id", "actor_user_id", name="uq_tenant_approval_actions_no_double_vote"),
    )

    # Dynamically name the function/trigger using the actual schema from search_path
    op.execute("""
        DO $$
        DECLARE
            schema_name text := current_schema();
        BEGIN
            EXECUTE format($f$
                CREATE OR REPLACE FUNCTION %I.check_approval_self_action()
                RETURNS trigger LANGUAGE plpgsql AS $fn$
                DECLARE maker UUID;
                BEGIN
                    SELECT requested_by INTO maker FROM %I.approval_requests WHERE id = NEW.approval_request_id;
                    IF NEW.actor_user_id = maker THEN
                        RAISE EXCEPTION 'maker cannot be checker';
                    END IF;
                    RETURN NEW;
                END;
                $fn$
            $f$, schema_name, schema_name);

            EXECUTE format($f$
                CREATE TRIGGER trg_approval_actions_no_self_approval
                BEFORE INSERT ON %I.approval_actions
                FOR EACH ROW EXECUTE FUNCTION %I.check_approval_self_action()
            $f$, schema_name, schema_name);
        END;
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_approval_actions_no_self_approval ON approval_actions")
    op.execute("DROP FUNCTION IF EXISTS check_approval_self_action()")
    op.drop_table("approval_actions")
    op.drop_table("approval_requests")
    op.drop_table("processed_events")
    op.drop_table("outbox_events")
    op.drop_table("audit_log")
