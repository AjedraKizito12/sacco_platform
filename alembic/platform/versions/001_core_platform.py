"""
Create core tables in the platform schema: audit_log, outbox_events,
processed_events, approval_requests, approval_actions.

Platform and tenant Alembic chains are independent.
Version numbers do not correlate across chains.
001 in platform and 001 in tenant are unrelated migrations.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")

    op.create_table(
        "audit_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_label", sa.Text(), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        schema="platform",
    )
    op.create_index("ix_platform_audit_log_table_record", "audit_log", ["table_name", "record_id"], schema="platform")
    op.create_index("ix_platform_audit_log_occurred_at", "audit_log", [sa.text("occurred_at DESC")], schema="platform")

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_dead_lettered", sa.Boolean(), server_default="false", nullable=False),
        schema="platform",
    )
    op.create_index(
        "ix_platform_outbox_pending",
        "outbox_events",
        ["next_attempt_at"],
        schema="platform",
        postgresql_where=sa.text("published_at IS NULL AND is_dead_lettered = false"),
    )

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("consumer_name", sa.Text(), nullable=False),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("event_id", "consumer_name"),
        schema="platform",
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("operation_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("required_approvals", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("execution_result", sa.JSON(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        schema="platform",
    )

    op.create_table(
        "approval_actions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("approval_request_id", sa.UUID(), sa.ForeignKey("platform.approval_requests.id"), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("acted_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.UniqueConstraint("approval_request_id", "actor_user_id", name="uq_platform_approval_actions_no_double_vote"),
        schema="platform",
    )

    # Trigger: prevent maker from being checker
    op.execute("""
        CREATE OR REPLACE FUNCTION platform.check_approval_self_action()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            maker UUID;
        BEGIN
            SELECT requested_by INTO maker
              FROM platform.approval_requests
             WHERE id = NEW.approval_request_id;
            IF NEW.actor_user_id = maker THEN
                RAISE EXCEPTION 'maker cannot be checker (self-approval forbidden)';
            END IF;
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_platform_approval_actions_no_self_approval
        BEFORE INSERT ON platform.approval_actions
        FOR EACH ROW EXECUTE FUNCTION platform.check_approval_self_action();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_platform_approval_actions_no_self_approval ON platform.approval_actions")
    op.execute("DROP FUNCTION IF EXISTS platform.check_approval_self_action()")
    op.drop_table("approval_actions", schema="platform")
    op.drop_table("approval_requests", schema="platform")
    op.drop_table("processed_events", schema="platform")
    op.drop_table("outbox_events", schema="platform")
    op.drop_table("audit_log", schema="platform")
