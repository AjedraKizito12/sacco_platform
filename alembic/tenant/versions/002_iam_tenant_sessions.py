"""Create tenant_sessions in the tenant schema.

Tables are created in whatever schema is set by SET search_path
(see alembic/tenant/env.py). No schema= qualifier is used; the
session applies the search_path before running this migration.

Revision: 002
Depends on: 001 (tenant schema structure must exist)

Note: tenant_user_id has no FK yet — tenant_users does not exist
until Plan 04 migration 003_iam_tenant_users.py runs. The column
stores a UUID and the FK will be added by that migration.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_sessions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("tenant_user_id", sa.UUID(), nullable=False),
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
        sa.UniqueConstraint("jti", name="uq_tenant_sessions_jti"),
        # No schema= — resolved at runtime via search_path.
    )
    op.create_index(
        "ix_tenant_sessions_tenant_user_id",
        "tenant_sessions",
        ["tenant_user_id"],
    )
    op.create_index(
        "ix_tenant_sessions_jti",
        "tenant_sessions",
        ["jti"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_sessions_jti", table_name="tenant_sessions")
    op.drop_index("ix_tenant_sessions_tenant_user_id", table_name="tenant_sessions")
    op.drop_table("tenant_sessions")
