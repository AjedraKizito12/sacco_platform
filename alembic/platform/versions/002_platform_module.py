"""
Create platform.tenants and platform.platform_users.
Add foreign keys from approval tables to platform_users.
Seed the bootstrap superuser (idempotent).
"""
from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("schema_name", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("provisioning_state", sa.Text(), nullable=True),
        sa.Column("failed_step", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("provisioning_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("provisioning_completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("seed_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('pending','provisioning','active','suspended','failed','deprovisioning','archived')",
            name="ck_tenants_status",
        ),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
        sa.UniqueConstraint("schema_name", name="uq_tenants_schema_name"),
        schema="platform",
    )
    op.create_index("ix_platform_tenants_slug", "tenants", ["slug"], schema="platform")
    op.create_index("ix_platform_tenants_status", "tenants", ["status"], schema="platform")

    op.create_table(
        "platform_users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_platform_users_email"),
        schema="platform",
    )
    op.create_index("ix_platform_users_email", "platform_users", ["email"], schema="platform")

    # Add FKs from approval tables to platform_users.
    # These are DB-level only; the SQLAlchemy models do not declare them
    # to avoid cross-module model imports (per CLAUDE.md).
    op.create_foreign_key(
        "fk_platform_approval_requests_requested_by",
        "approval_requests", "platform_users",
        ["requested_by"], ["id"],
        source_schema="platform", referent_schema="platform",
    )
    op.create_foreign_key(
        "fk_platform_approval_actions_actor_user_id",
        "approval_actions", "platform_users",
        ["actor_user_id"], ["id"],
        source_schema="platform", referent_schema="platform",
    )

    # Bootstrap superuser seed (idempotent).
    # Inserts only when no superuser exists yet; skips on email conflict.
    bootstrap_email = os.environ.get("PLATFORM_BOOTSTRAP_EMAIL", "").strip()
    bootstrap_name = os.environ.get("PLATFORM_BOOTSTRAP_FULL_NAME", "Platform Admin").strip()

    if bootstrap_email:
        conn = op.get_bind()
        row = conn.execute(
            sa.text("SELECT COUNT(*) FROM platform.platform_users WHERE is_superuser = true")
        ).scalar_one()
        if row == 0:
            conn.execute(
                sa.text(
                    "INSERT INTO platform.platform_users"
                    " (email, full_name, is_active, is_superuser, created_at, updated_at)"
                    " VALUES (:email, :name, true, true, now(), now())"
                    " ON CONFLICT (email) DO NOTHING"
                ),
                {"email": bootstrap_email, "name": bootstrap_name},
            )


def downgrade() -> None:
    op.drop_constraint(
        "fk_platform_approval_actions_actor_user_id", "approval_actions", schema="platform"
    )
    op.drop_constraint(
        "fk_platform_approval_requests_requested_by", "approval_requests", schema="platform"
    )
    op.drop_index("ix_platform_users_email", table_name="platform_users", schema="platform")
    op.drop_table("platform_users", schema="platform")
    op.drop_index("ix_platform_tenants_status", table_name="tenants", schema="platform")
    op.drop_index("ix_platform_tenants_slug", table_name="tenants", schema="platform")
    op.drop_table("tenants", schema="platform")
