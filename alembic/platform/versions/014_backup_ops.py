"""Backup/restore operational telemetry tables.

Revision: 014
Depends on: 013

Note: the Phase 4 plan reserved migration 012 for these tables, but the
global-search increment shipped first as 013 (chaining off 011), leaving 012
empty. This migration therefore chains onto the current head (013) as 014.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("backup_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("repo_size_bytes", sa.Integer(), nullable=True),
        sa.Column("wal_lag_seconds", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('running','succeeded','failed')", name="ck_backup_runs_status"),
        sa.CheckConstraint("backup_type IN ('full','incr','diff')", name="ck_backup_runs_type"),
        schema="platform",
    )
    op.create_index("ix_platform_backup_runs_created_at", "backup_runs", ["created_at"], schema="platform")
    op.create_table(
        "backup_verifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("requested_by", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("started_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('requested','running','passed','failed')", name="ck_backup_verifications_status"),
        schema="platform",
    )
    op.create_index("ix_platform_backup_verifications_created_at", "backup_verifications", ["created_at"], schema="platform")
    op.create_index("ix_platform_backup_verifications_status", "backup_verifications", ["status"], schema="platform")


def downgrade() -> None:
    op.drop_table("backup_verifications", schema="platform")
    op.drop_table("backup_runs", schema="platform")
