"""Unit tests for the pure month-series dashboard helpers."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.month_series import as_cumulative, as_flow, month_keys


def test_month_keys_spans_n_months_oldest_first():
    assert month_keys(3, today=date(2026, 6, 15)) == ["2026-04", "2026-05", "2026-06"]


def test_month_keys_crosses_year_boundary():
    assert month_keys(3, today=date(2026, 1, 10)) == ["2025-11", "2025-12", "2026-01"]


def test_as_flow_fills_missing_months_with_zero():
    movements = {"2026-05": Decimal("800"), "2026-06": Decimal("500")}
    assert as_flow(movements, 3, today=date(2026, 6, 15)) == [
        ("2026-04", Decimal("0")),
        ("2026-05", Decimal("800")),
        ("2026-06", Decimal("500")),
    ]


def test_as_cumulative_walks_back_from_current_total():
    movements = {"2026-05": Decimal("800"), "2026-06": Decimal("500")}
    # current total reflects every movement ever; the latest month-end equals it
    assert as_cumulative(
        movements, 3, today=date(2026, 6, 15), current_total=Decimal("1300")
    ) == [
        ("2026-04", Decimal("0")),
        ("2026-05", Decimal("800")),
        ("2026-06", Decimal("1300")),
    ]
