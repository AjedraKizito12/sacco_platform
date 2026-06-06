"""Phase 1.7 — add impersonation_id column to tenant_users and audit_log.

Both columns ship in 02a. They are populated in 02b (shadow tenant_user
creation on first mint; AuditableMixin extension reads from contextvars).

Revision: 014
Depends on: 013
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_users",
        sa.Column("impersonation_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_tenant_users_impersonation_id",
        "tenant_users",
        ["impersonation_id"],
        postgresql_where=sa.text("impersonation_id IS NOT NULL"),
    )

    op.add_column(
        "audit_log",
        sa.Column("impersonation_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_tenant_audit_log_impersonation_id",
        "audit_log",
        ["impersonation_id"],
        postgresql_where=sa.text("impersonation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_audit_log_impersonation_id", table_name="audit_log")
    op.drop_column("audit_log", "impersonation_id")
    op.drop_index("ix_tenant_users_impersonation_id", table_name="tenant_users")
    op.drop_column("tenant_users", "impersonation_id")
