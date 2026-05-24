"""Create members table with member_number_seq.

members — one row per SACCO member; mutable (status, KYC can be updated).
member_number_seq — per-tenant sequence producing M-00001, M-00002, ...
Status transitions (pending→active etc.) require maker-checker approval.

Revision: 006
Depends on: 005
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS member_number_seq START 1")

    op.create_table(
        "members",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("member_number", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("gender", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("physical_address", sa.Text(), nullable=True),
        # KYC
        sa.Column("national_id_number", sa.Text(), nullable=True),
        sa.Column("id_document_type", sa.Text(), nullable=True),
        sa.Column("id_document_number", sa.Text(), nullable=True),
        sa.Column("id_issued_date", sa.Date(), nullable=True),
        sa.Column("id_expiry_date", sa.Date(), nullable=True),
        # Status lifecycle
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("joined_at", sa.Date(), nullable=True),
        # Timestamps
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
        # Constraints
        sa.UniqueConstraint("member_number", name="uq_members_member_number"),
        sa.UniqueConstraint("email", name="uq_members_email"),
        sa.UniqueConstraint("national_id_number", name="uq_members_national_id_number"),
        sa.CheckConstraint(
            "gender IN ('male', 'female', 'other')",
            name="ck_members_gender",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'suspended', 'exited')",
            name="ck_members_status",
        ),
        sa.CheckConstraint(
            "id_document_type IS NULL OR id_document_type IN ('national_id', 'passport', 'driving_license')",
            name="ck_members_id_doc_type",
        ),
    )
    op.create_index("ix_members_status", "members", ["status"])
    op.create_index("ix_members_email", "members", ["email"])
    op.create_index("ix_members_national_id_number", "members", ["national_id_number"])


def downgrade() -> None:
    op.drop_table("members")
    op.execute("DROP SEQUENCE IF EXISTS member_number_seq")
