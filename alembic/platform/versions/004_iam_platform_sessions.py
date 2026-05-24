"""Create platform.platform_sessions.

Revision: 004
Depends on: 003 (platform_users must exist; platform_user_id FK references it)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_sessions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("platform_user_id", sa.UUID(), nullable=False),
        sa.Column("jti", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["platform_user_id"],
            ["platform.platform_users.id"],
            name="fk_platform_sessions_platform_user_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("jti", name="uq_platform_sessions_jti"),
        schema="platform",
    )
    op.create_index(
        "ix_platform_sessions_platform_user_id",
        "platform_sessions",
        ["platform_user_id"],
        schema="platform",
    )
    op.create_index(
        "ix_platform_sessions_jti",
        "platform_sessions",
        ["jti"],
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_sessions_jti",
        table_name="platform_sessions",
        schema="platform",
    )
    op.drop_index(
        "ix_platform_sessions_platform_user_id",
        table_name="platform_sessions",
        schema="platform",
    )
    op.drop_table("platform_sessions", schema="platform")
