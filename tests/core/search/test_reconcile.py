from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.core.search.reconcile import next_watermark


def test_next_watermark_takes_max_updated_at():
    base = datetime(2026, 7, 1, tzinfo=UTC)
    rows = [
        SimpleNamespace(updated_at=base),
        SimpleNamespace(updated_at=base + timedelta(hours=2)),
    ]
    assert next_watermark(rows, base - timedelta(days=1)) == base + timedelta(hours=2)


def test_next_watermark_keeps_current_when_no_rows():
    base = datetime(2026, 7, 1, tzinfo=UTC)
    assert next_watermark([], base) == base
