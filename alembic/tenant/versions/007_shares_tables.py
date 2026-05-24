"""Create shares tables: share_products, member_share_accounts, share_transactions.

share_products       — defines a share class: par value, equity GL account, limits.
member_share_accounts — one row per (member, product) pair; no balance stored.
share_transactions   — append-only; each purchase or redemption is a row.
Balance is derived: SUM(purchase qty) - SUM(redemption qty) from share_transactions.

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
    op.create_table(
        "share_products",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("par_value", sa.Numeric(19, 4), nullable=False),
        sa.Column("minimum_shares", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("maximum_shares", sa.Integer(), nullable=True),
        sa.Column("share_capital_account_id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint("par_value > 0", name="ck_share_products_par_value_positive"),
        sa.CheckConstraint("minimum_shares >= 1", name="ck_share_products_min_shares"),
        sa.CheckConstraint(
            "maximum_shares IS NULL OR maximum_shares >= minimum_shares",
            name="ck_share_products_max_shares",
        ),
    )
    op.create_index("ix_share_products_is_active", "share_products", ["is_active"])

    op.create_table(
        "member_share_accounts",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("share_product_id", sa.UUID(), nullable=False),
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
            ["member_id"], ["members.id"], name="fk_msa_member"
        ),
        sa.ForeignKeyConstraint(
            ["share_product_id"], ["share_products.id"], name="fk_msa_product"
        ),
        sa.UniqueConstraint(
            "member_id", "share_product_id", name="uq_msa_member_product"
        ),
    )
    op.create_index("ix_msa_member_id", "member_share_accounts", ["member_id"])
    op.create_index("ix_msa_share_product_id", "member_share_accounts", ["share_product_id"])

    op.create_table(
        "share_transactions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("share_account_id", sa.UUID(), nullable=False),
        sa.Column("transaction_type", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
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
            ["share_account_id"],
            ["member_share_accounts.id"],
            name="fk_st_share_account",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entries.id"],
            name="fk_st_journal_entry",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_st_idempotency_key"),
        sa.CheckConstraint(
            "transaction_type IN ('purchase', 'redemption')",
            name="ck_st_transaction_type",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_st_quantity_positive"),
        sa.CheckConstraint("amount > 0", name="ck_st_amount_positive"),
    )
    op.create_index("ix_st_share_account_id", "share_transactions", ["share_account_id"])
    op.create_index("ix_st_posted_at", "share_transactions", ["posted_at"])


def downgrade() -> None:
    op.drop_table("share_transactions")
    op.drop_table("member_share_accounts")
    op.drop_table("share_products")
