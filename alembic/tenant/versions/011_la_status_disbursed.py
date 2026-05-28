# alembic/tenant/versions/011_la_status_disbursed.py
"""Add 'disbursed' to loan_applications.status check constraint.

Revision: 011
Depends on: 010
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_la_status", "loan_applications", type_="check")
    op.create_check_constraint(
        "ck_la_status",
        "loan_applications",
        "status IN ('draft', 'submitted', 'under_review', 'approved', 'rejected', 'withdrawn', 'cancelled', 'disbursed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_la_status", "loan_applications", type_="check")
    op.create_check_constraint(
        "ck_la_status",
        "loan_applications",
        "status IN ('draft', 'submitted', 'under_review', 'approved', 'rejected', 'withdrawn', 'cancelled')",
    )
