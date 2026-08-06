"""Unit tests for the Phase 7 tenant lifecycle model + settings additions."""
from __future__ import annotations

from app.platform_.models import Tenant, TenantLifecycleEvent


def test_tenant_has_lifecycle_columns() -> None:
    cols = Tenant.__table__.columns
    assert "lifecycle_state" in cols
    assert cols["lifecycle_state"].default.arg == "active"
    for c in (
        "cancelled_at", "read_only_at", "archived_at", "hard_deleted_at",
        "retention_hold_until", "archive_storage_key", "archive_size_bytes",
        "archive_checksum",
    ):
        assert c in cols


def test_lifecycle_event_table() -> None:
    cols = TenantLifecycleEvent.__table__.columns
    assert {
        "tenant_id", "from_state", "to_state", "occurred_at", "reason",
        "actor_id", "metadata",
    } <= set(cols.keys())


def test_offboarding_settings_defaults() -> None:
    from app.core.config import Settings

    s = Settings()
    assert (
        s.offboarding_read_only_days,
        s.offboarding_archive_days,
        s.offboarding_hard_delete_days,
    ) == (7, 83, 2555)
