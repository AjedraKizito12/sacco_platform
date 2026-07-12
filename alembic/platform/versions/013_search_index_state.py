"""Search reconcile watermark state.

Revision: 013
Depends on: 011
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

from alembic import op

revision = "013"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_index_state",
        sa.Column("index_name", sa.Text(), primary_key=True),
        sa.Column("scope", sa.Text(), primary_key=True),
        sa.Column("last_watermark", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_run_at", TIMESTAMP(timezone=True), nullable=True),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("search_index_state", schema="platform")
