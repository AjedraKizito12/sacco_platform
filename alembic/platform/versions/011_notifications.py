"""Platform notification tables: templates, events, deliveries, preferences.

Also seeds the default templates (locale 'en') for every catalog default
channel — the same rows tests seed via seed_default_templates().

Revision: 011
Depends on: 010
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("locale", sa.Text(), nullable=False, server_default="en"),
        sa.Column("subject_template", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("sms_body", sa.Text(), nullable=True),
        sa.Column("variables", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.UniqueConstraint(
            "code", "channel", "locale",
            name="uq_notification_templates_code_channel_locale",
        ),
        schema="platform",
    )

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
        sa.UniqueConstraint("dedupe_key", name="uq_platform_notification_events_dedupe_key"),
        schema="platform",
    )
    op.create_index(
        "ix_platform_notification_events_dispatch",
        "notification_events",
        ["status", "scheduled_at"],
        schema="platform",
    )
    op.create_index(
        "ix_platform_notification_events_recipient",
        "notification_events",
        ["recipient_kind", "recipient_user_id", "created_at"],
        schema="platform",
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "notification_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform.notification_events.id", ondelete="CASCADE"),
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
        schema="platform",
    )
    op.create_index(
        "ix_platform_notification_deliveries_event",
        "notification_deliveries",
        ["notification_event_id"],
        schema="platform",
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
            name="uq_platform_notification_preferences_scope",
        ),
        schema="platform",
    )

    _seed_templates()


def _seed_templates() -> None:
    from app.core.notifications.seed_templates import DEFAULT_TEMPLATES

    templates = sa.table(
        "notification_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.Text()),
        sa.column("channel", sa.Text()),
        sa.column("locale", sa.Text()),
        sa.column("subject_template", sa.Text()),
        sa.column("body_html", sa.Text()),
        sa.column("body_text", sa.Text()),
        sa.column("sms_body", sa.Text()),
        sa.column("variables", postgresql.JSONB()),
        schema="platform",
    )
    op.bulk_insert(
        templates,
        [{"id": uuid.uuid4(), **row} for row in DEFAULT_TEMPLATES],
    )


def downgrade() -> None:
    op.drop_table("notification_preferences", schema="platform")
    op.drop_table("notification_deliveries", schema="platform")
    op.drop_table("notification_events", schema="platform")
    op.drop_table("notification_templates", schema="platform")
