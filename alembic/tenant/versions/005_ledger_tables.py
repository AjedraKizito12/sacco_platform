"""Create ledger tables: chart_of_accounts, journal_entries, journal_lines.

chart_of_accounts — mutable account registry; hierarchy via self-referential parent_id.
journal_entries   — append-only header per double-entry posting.
journal_lines     — append-only debit/credit legs; one side must be zero per line.
Balance is derived from journal_lines, never stored.

Revision: 005
Depends on: 004
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chart_of_accounts",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("account_type", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("code", name="uq_coa_code"),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["chart_of_accounts.id"],
            name="fk_coa_parent",
        ),
        sa.CheckConstraint(
            "account_type IN ('asset', 'liability', 'equity', 'income', 'expense')",
            name="ck_coa_account_type",
        ),
    )
    op.create_index("ix_coa_code", "chart_of_accounts", ["code"])
    op.create_index("ix_coa_account_type", "chart_of_accounts", ["account_type"])

    op.create_table(
        "journal_entries",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("posted_by", sa.UUID(), nullable=False),
        sa.Column(
            "posted_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_je_idempotency_key"),
    )
    op.create_index("ix_je_reference", "journal_entries", ["reference"])
    op.create_index("ix_je_posted_at", "journal_entries", ["posted_at"])

    op.create_table(
        "journal_lines",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("journal_entry_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column(
            "debit_amount",
            sa.Numeric(19, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "credit_amount",
            sa.Numeric(19, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name="fk_jl_entry",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["chart_of_accounts.id"],
            name="fk_jl_account",
        ),
        sa.CheckConstraint(
            "debit_amount >= 0 AND credit_amount >= 0"
            " AND (debit_amount > 0 OR credit_amount > 0)"
            " AND NOT (debit_amount > 0 AND credit_amount > 0)",
            name="ck_jl_amounts",
        ),
    )
    op.create_index("ix_jl_journal_entry_id", "journal_lines", ["journal_entry_id"])
    op.create_index("ix_jl_account_id", "journal_lines", ["account_id"])


def downgrade() -> None:
    op.drop_table("journal_lines")
    op.drop_table("journal_entries")
    op.drop_table("chart_of_accounts")
