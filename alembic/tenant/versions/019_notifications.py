"""Tenant notification tables: events, deliveries, preferences.

Revision: 019
Depends on: 018
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_code", sa.Text(), nullable=False),
        sa.Column("recipient_kind", sa.Text(), nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_email", sa.Text(), nullable=True),
        sa.Column("recipient_phone", sa.Text(), nullable=True),
        sa.Column("channels", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column(
            "scheduled_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_events_dedupe_key"),
    )
    op.create_index(
        "ix_notification_events_dispatch",
        "notification_events",
        ["status", "scheduled_at"],
    )
    op.create_index(
        "ix_notification_events_recipient",
        "notification_events",
        ["recipient_kind", "recipient_user_id", "created_at"],
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "notification_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notification_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "sent_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_notification_deliveries_event",
        "notification_deliveries",
        ["notification_event_id"],
    )

    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recipient_kind", sa.Text(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_code", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint(
            "recipient_kind", "user_id", "event_code", "channel",
            name="uq_notification_preferences_scope",
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_table("notification_deliveries")
    op.drop_table("notification_events")
