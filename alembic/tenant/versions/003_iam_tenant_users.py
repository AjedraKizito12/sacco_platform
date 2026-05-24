"""Create tenant_users; add FK from tenant_sessions to tenant_users.

Revision: 003
Depends on: 002 (tenant_sessions must exist for the FK addition)

The tenant_sessions.tenant_user_id FK was deferred in migration 002
because tenant_users did not exist yet. We add it here now that the
referencing table exists.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_users",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_tenant_users_email"),
        # No schema= — resolved at runtime via search_path.
    )
    op.create_index("ix_tenant_users_email", "tenant_users", ["email"])

    # Retrofit the FK that was deferred in migration 002.
    op.create_foreign_key(
        "fk_tenant_sessions_tenant_user_id",
        "tenant_sessions",
        "tenant_users",
        ["tenant_user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_tenant_sessions_tenant_user_id",
        "tenant_sessions",
        type_="foreignkey",
    )
    op.drop_index("ix_tenant_users_email", table_name="tenant_users")
    op.drop_table("tenant_users")
