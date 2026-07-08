"""Member KYC submissions + next-of-kin/occupation member columns.

Revision: 018
Depends on: 017
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("members", sa.Column("next_of_kin_name", sa.Text(), nullable=True))
    op.add_column("members", sa.Column("next_of_kin_phone", sa.Text(), nullable=True))
    op.add_column("members", sa.Column("occupation", sa.Text(), nullable=True))

    op.create_table(
        "kyc_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("physical_address", sa.Text(), nullable=True),
        sa.Column("national_id_number", sa.Text(), nullable=True),
        sa.Column("id_document_type", sa.Text(), nullable=True),
        sa.Column("id_document_number", sa.Text(), nullable=True),
        sa.Column("id_issued_date", sa.Date(), nullable=True),
        sa.Column("id_expiry_date", sa.Date(), nullable=True),
        sa.Column("next_of_kin_name", sa.Text(), nullable=True),
        sa.Column("next_of_kin_phone", sa.Text(), nullable=True),
        sa.Column("occupation", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_kyc_submissions_status",
        ),
        sa.CheckConstraint(
            "id_document_type IS NULL OR id_document_type IN ('national_id', 'passport', 'driving_license')",
            name="ck_kyc_submissions_id_doc_type",
        ),
    )
    op.create_index(
        "uq_kyc_submissions_one_pending",
        "kyc_submissions",
        ["member_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_kyc_submissions_status", "kyc_submissions", ["status"])
    op.create_index("ix_kyc_submissions_member_id", "kyc_submissions", ["member_id"])


def downgrade() -> None:
    op.drop_table("kyc_submissions")
    op.drop_column("members", "occupation")
    op.drop_column("members", "next_of_kin_phone")
    op.drop_column("members", "next_of_kin_name")
