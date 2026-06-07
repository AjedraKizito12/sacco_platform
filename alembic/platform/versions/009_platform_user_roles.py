"""Phase 1.7 — platform_users.role four-tier hierarchy.

Adds the role column with a CHECK constraint, back-fills role='superuser'
for every is_superuser=true row, and leaves is_superuser in place for
backward compat. Future cleanup may drop is_superuser.

Revision: 009
Depends on: 008
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_users",
        sa.Column(
            "role",
            sa.Text(),
            nullable=False,
            server_default="support",
        ),
        schema="platform",
    )
    op.create_check_constraint(
        "ck_platform_users_role",
        "platform_users",
        "role IN ('superuser', 'admin', 'finance', 'support')",
        schema="platform",
    )
    op.create_index(
        "ix_platform_users_role",
        "platform_users",
        ["role"],
        schema="platform",
    )
    # Back-fill: every existing superuser gets role='superuser'.
    op.execute(
        "UPDATE platform.platform_users SET role = 'superuser' "
        "WHERE is_superuser = true"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_users_role", table_name="platform_users", schema="platform",
    )
    op.drop_constraint(
        "ck_platform_users_role", "platform_users", schema="platform",
    )
    op.drop_column("platform_users", "role", schema="platform")
