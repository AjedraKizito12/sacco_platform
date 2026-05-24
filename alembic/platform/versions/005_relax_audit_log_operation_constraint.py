"""Relax audit_log operation check constraint to allow auth event names.

The original constraint only permitted 'insert' | 'update' | 'delete',
which was appropriate for CRUD audit rows written by AuditableMixin.
Auth audit events (login_success, logout, refresh, etc.) use domain-specific
operation names and cannot be forced into DML categories without losing
semantic meaning. Drop the restrictive constraint; application code is
responsible for writing meaningful, non-empty operation values.

Revision: 005
Depends on: 004
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_audit_log_operation", "audit_log", schema="platform")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_audit_log_operation",
        "audit_log",
        "operation IN ('insert', 'update', 'delete')",
        schema="platform",
    )
