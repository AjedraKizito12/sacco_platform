"""Tenant offboarding lifecycle state + archival telemetry + audit.

Revision: 015
Depends on: 014
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

_STATES = "('active','cancelled','read_only','archived','hard_deleted')"


def upgrade() -> None:
    op.add_column("tenants", sa.Column("lifecycle_state", sa.Text(), nullable=False, server_default="active"), schema="platform")
    for col in ("cancelled_at", "read_only_at", "archived_at", "hard_deleted_at", "retention_hold_until"):
        op.add_column("tenants", sa.Column(col, TIMESTAMP(timezone=True), nullable=True), schema="platform")
    op.add_column("tenants", sa.Column("archive_storage_key", sa.Text(), nullable=True), schema="platform")
    op.add_column("tenants", sa.Column("archive_size_bytes", sa.BigInteger(), nullable=True), schema="platform")
    op.add_column("tenants", sa.Column("archive_checksum", sa.Text(), nullable=True), schema="platform")
    op.create_check_constraint("ck_tenants_lifecycle_state", "tenants", f"lifecycle_state IN {_STATES}", schema="platform")
    op.create_index("ix_platform_tenants_lifecycle_state", "tenants", ["lifecycle_state"], schema="platform")

    op.create_table(
        "tenant_lifecycle_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("platform.tenants.id"), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=False),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("occurred_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("platform.platform_users.id"), nullable=True),
        sa.Column("metadata", JSONB(), server_default="{}", nullable=False),
        schema="platform",
    )
    op.create_index("ix_platform_tenant_lifecycle_events_tenant", "tenant_lifecycle_events", ["tenant_id", "occurred_at"], schema="platform")


def downgrade() -> None:
    op.drop_table("tenant_lifecycle_events", schema="platform")
    op.drop_index("ix_platform_tenants_lifecycle_state", table_name="tenants", schema="platform")
    op.drop_constraint("ck_tenants_lifecycle_state", "tenants", schema="platform")
    for col in ("archive_checksum", "archive_size_bytes", "archive_storage_key", "retention_hold_until",
                "hard_deleted_at", "archived_at", "read_only_at", "cancelled_at", "lifecycle_state"):
        op.drop_column("tenants", col, schema="platform")
