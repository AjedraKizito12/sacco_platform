"""Phase 1 Billing — payments.idempotency_key + invoice_seq_2026.

Revision: 007
Depends on: 006
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotency key for the payments table (SP01 carryover).
    # The table has no production rows yet, so NOT NULL is safe.
    op.add_column(
        "payments",
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        schema="platform",
    )
    op.create_unique_constraint(
        "uq_payments_idempotency_key",
        "payments",
        ["idempotency_key"],
        schema="platform",
    )

    # Invoice numbering sequence for the current year.
    # InvoiceService creates additional yearly sequences lazily.
    op.execute("CREATE SEQUENCE IF NOT EXISTS platform.invoice_seq_2026")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS platform.invoice_seq_2026")
    op.drop_constraint(
        "uq_payments_idempotency_key",
        "payments",
        type_="unique",
        schema="platform",
    )
    op.drop_column("payments", "idempotency_key", schema="platform")
