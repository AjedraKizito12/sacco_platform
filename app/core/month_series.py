"""Pure helpers for building dashboard month-series from grouped aggregates.

Services compute a ``{"YYYY-MM": value}`` dict of monthly movements with one
grouped SQL query; these helpers turn that sparse dict into a dense, ordered
series (filling gaps with zero) for the portal's trend charts. Kept free of the
ORM so the date maths is unit-tested directly.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal


def month_keys(n: int, *, today: date) -> list[str]:
    """Return the last ``n`` month keys (``YYYY-MM``), oldest first.

    The newest key is ``today``'s month.
    """
    year, month = today.year, today.month
    keys: list[str] = []
    for _ in range(n):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(keys))


def as_flow(
    movements: dict[str, Decimal], n: int, *, today: date
) -> list[tuple[str, Decimal]]:
    """Dense per-month flow series over the last ``n`` months (gaps → 0)."""
    return [(key, movements.get(key, Decimal("0"))) for key in month_keys(n, today=today)]


def as_cumulative(
    movements: dict[str, Decimal],
    n: int,
    *,
    today: date,
    current_total: Decimal,
) -> list[tuple[str, Decimal]]:
    """Dense month-end cumulative balance series over the last ``n`` months.

    ``current_total`` is the balance now (the sum of every movement ever, not
    just the window). The latest month-end equals it; earlier month-ends are
    derived by walking backwards and subtracting each month's movement.
    """
    keys = month_keys(n, today=today)
    balances: list[tuple[str, Decimal]] = []
    running = current_total
    for key in reversed(keys):
        balances.append((key, running))
        running -= movements.get(key, Decimal("0"))
    return list(reversed(balances))
