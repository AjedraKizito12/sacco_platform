# tests/modules/reporting/test_base.py
"""Unit tests for _base.py rendering utilities."""
from __future__ import annotations

import csv
import io

import pytest  # noqa: F401 — spec-mandated

from app.modules.reporting._base import render_csv


def test_render_csv_headers_and_rows():
    headers = ["Code", "Name", "Balance"]
    rows = [["1000", "Cash", "5000.00"], ["2000", "Loans", "120000.00"]]
    result = render_csv(headers, rows)

    # BOM prefix
    assert result[:3] == b"\xef\xbb\xbf"

    # Valid CSV
    text = result.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    assert reader[0] == headers
    assert reader[1] == ["1000", "Cash", "5000.00"]
    assert reader[2] == ["2000", "Loans", "120000.00"]


def test_render_csv_none_values_become_empty_string():
    result = render_csv(["A", "B"], [[None, "value"]])
    text = result.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    assert reader[1] == ["", "value"]


def test_render_html_returns_rendered_string():
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from app.modules.reporting._base import render_html

    html = render_html(
        "trial_balance.html",
        {
            "as_of_date": date(2026, 1, 31),
            "generated_at": datetime(2026, 1, 31, 12, 0, tzinfo=UTC),
            "rows": [],
            "total_debits": Decimal("0"),
            "total_credits": Decimal("0"),
        },
    )
    assert isinstance(html, str)
    assert "<html" in html
