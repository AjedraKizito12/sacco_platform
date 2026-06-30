"""Platform-global SACCO KYC required-set overrides.

Revision: 010
Depends on: 009
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sacco_kyc_requirements",
        sa.Column("field_key", sa.Text(), primary_key=True),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("sacco_kyc_requirements", schema="platform")
