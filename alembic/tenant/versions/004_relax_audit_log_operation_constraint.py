"""Relax audit_log operation check constraint to allow auth event names.

Mirrors platform migration 005. Tenant audit_log also needs to store
domain-event operation names (login_success, logout, etc.).

Revision: 004
Depends on: 003
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_audit_log_operation", "audit_log")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_audit_log_operation",
        "audit_log",
        "operation IN ('insert', 'update', 'delete')",
    )
