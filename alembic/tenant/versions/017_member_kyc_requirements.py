"""Per-tenant member KYC required-set overrides.

Revision: 017
Depends on: 016
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_kyc_requirements",
        sa.Column("field_key", sa.Text(), primary_key=True),
        sa.Column("is_required", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("member_kyc_requirements")
