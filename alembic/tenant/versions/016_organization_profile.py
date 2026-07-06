"""SACCO organization KYC singleton profile.

Revision: 016
Depends on: 015
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_profile",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("legal_name", sa.Text(), nullable=True),
        sa.Column("registration_number", sa.Text(), nullable=True),
        sa.Column("registered_address", sa.Text(), nullable=True),
        sa.Column("primary_contact_name", sa.Text(), nullable=True),
        sa.Column("primary_contact_email", sa.Text(), nullable=True),
        sa.Column("registration_date", sa.Date(), nullable=True),
        sa.Column("regulator_name", sa.Text(), nullable=True),
        sa.Column("license_number", sa.Text(), nullable=True),
        sa.Column("tax_id", sa.Text(), nullable=True),
        sa.Column("primary_contact_phone", sa.Text(), nullable=True),
        sa.Column("postal_address", sa.Text(), nullable=True),
        sa.Column("district_region", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("verified_by_platform_user_id", sa.UUID(), nullable=True),
        sa.Column("singleton", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("singleton", name="uq_organization_profile_singleton"),
    )


def downgrade() -> None:
    op.drop_table("organization_profile")
