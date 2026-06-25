"""Phase 4a — member portal auth: members credential columns + member_sessions.

Revision: 015
Depends on: 014
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "members",
        sa.Column("hashed_password", sa.Text(), nullable=True),
    )
    op.add_column(
        "members",
        sa.Column(
            "portal_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "members",
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "member_sessions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("jti", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("jti", name="uq_member_sessions_jti"),
    )
    op.create_index("ix_member_sessions_member_id", "member_sessions", ["member_id"])
    op.create_index("ix_member_sessions_jti", "member_sessions", ["jti"])


def downgrade() -> None:
    op.drop_index("ix_member_sessions_jti", table_name="member_sessions")
    op.drop_index("ix_member_sessions_member_id", table_name="member_sessions")
    op.drop_table("member_sessions")
    op.drop_column("members", "last_login_at")
    op.drop_column("members", "portal_enabled")
    op.drop_column("members", "hashed_password")
