"""Create savings tables: savings_products, savings_accounts, savings_transactions.

savings_products     — defines a savings product: interest rate, minimum balance, liability GL account.
savings_accounts     — one row per (member, product) pair; snapshots product terms at account creation.
savings_transactions — append-only; each deposit or withdrawal is a row.
Balance is derived: SUM(deposits) - SUM(withdrawals) from savings_transactions.

Revision: 008
Depends on: 007
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "savings_products",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("interest_rate", sa.Numeric(19, 4), nullable=False),
        sa.Column("minimum_balance", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("liability_account_id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.CheckConstraint("interest_rate >= 0", name="ck_savings_products_interest_rate"),
        sa.CheckConstraint("minimum_balance >= 0", name="ck_savings_products_min_balance"),
    )
    op.create_index("ix_savings_products_is_active", "savings_products", ["is_active"])

    op.create_table(
        "savings_accounts",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("savings_product_id", sa.UUID(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("interest_rate", sa.Numeric(19, 4), nullable=False),
        sa.Column("minimum_balance", sa.Numeric(19, 4), nullable=False),
        sa.Column("liability_account_id", sa.UUID(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name="fk_sa_member"
        ),
        sa.ForeignKeyConstraint(
            ["savings_product_id"], ["savings_products.id"], name="fk_sa_product"
        ),
        sa.UniqueConstraint(
            "member_id", "savings_product_id", name="uq_sa_member_product"
        ),
    )
    op.create_index("ix_sa_member_id", "savings_accounts", ["member_id"])
    op.create_index("ix_sa_savings_product_id", "savings_accounts", ["savings_product_id"])

    op.create_table(
        "savings_transactions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("savings_account_id", sa.UUID(), nullable=False),
        sa.Column("transaction_type", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("journal_entry_id", sa.UUID(), nullable=False),
        sa.Column("posted_by", sa.UUID(), nullable=False),
        sa.Column(
            "posted_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["savings_account_id"],
            ["savings_accounts.id"],
            name="fk_savtx_account",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name="fk_savtx_journal",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_savtx_idempotency_key"),
        sa.CheckConstraint(
            "transaction_type IN ('deposit', 'withdrawal')",
            name="ck_savtx_transaction_type",
        ),
        sa.CheckConstraint("amount > 0", name="ck_savtx_amount_positive"),
    )
    op.create_index("ix_savtx_savings_account_id", "savings_transactions", ["savings_account_id"])
    op.create_index("ix_savtx_posted_at", "savings_transactions", ["posted_at"])


def downgrade() -> None:
    op.drop_table("savings_transactions")
    op.drop_table("savings_accounts")
    op.drop_table("savings_products")
