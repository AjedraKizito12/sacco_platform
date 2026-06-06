"""Phase 1.7 — platform.support_impersonations table.

Tracks active and historical platform-user → tenant impersonation sessions.

Revision: 008
Depends on: 007
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_impersonations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("platform_user_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        # tenant_user_id is the shadow tenant_user this impersonation maps to;
        # populated lazily by 02b on the first mint-token call. Null until then.
        sa.Column("tenant_user_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ended_by", sa.UUID(), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["platform_user_id"], ["platform.platform_users.id"],
            name="fk_support_impersonations_platform_user",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["platform.tenants.id"],
            name="fk_support_impersonations_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["approval_request_id"], ["platform.approval_requests.id"],
            name="fk_support_impersonations_approval_request",
        ),
        sa.ForeignKeyConstraint(
            ["ended_by"], ["platform.platform_users.id"],
            name="fk_support_impersonations_ended_by",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"], ["platform.platform_users.id"],
            name="fk_support_impersonations_revoked_by",
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR revoked_at IS NULL",
            name="ck_support_impersonations_not_both_ended_and_revoked",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_support_impersonations_platform_user_active",
        "support_impersonations",
        ["platform_user_id"],
        postgresql_where=sa.text("ended_at IS NULL AND revoked_at IS NULL"),
        schema="platform",
    )
    op.create_index(
        "ix_support_impersonations_tenant_active",
        "support_impersonations",
        ["tenant_id"],
        postgresql_where=sa.text("ended_at IS NULL AND revoked_at IS NULL"),
        schema="platform",
    )
    op.create_index(
        "ix_support_impersonations_expires_at",
        "support_impersonations",
        ["expires_at"],
        postgresql_where=sa.text("ended_at IS NULL AND revoked_at IS NULL"),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_support_impersonations_expires_at",
        table_name="support_impersonations",
        schema="platform",
    )
    op.drop_index(
        "ix_support_impersonations_tenant_active",
        table_name="support_impersonations",
        schema="platform",
    )
    op.drop_index(
        "ix_support_impersonations_platform_user_active",
        table_name="support_impersonations",
        schema="platform",
    )
    op.drop_table("support_impersonations", schema="platform")
