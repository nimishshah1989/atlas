"""Denomination conversion service — pure computation, no DB/IO.

Converts an INR price series to alternative denominations (gold, USD)
by dividing close prices by a reference series at common dates.
All arithmetic Decimal. Never float.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional


def apply_denomination(
    prices: list[dict[str, Any]],
    denom_series: list[tuple[date, Decimal]],
) -> tuple[list[dict[str, Any]], Optional[date]]:
    """Convert close prices to an alternative denomination.

    Args:
        prices: List of dicts with 'date' (date), 'close' (Decimal|None), etc.
            OHLCV rows from JIPEquityService.get_chart_data().
        denom_series: List of (date, Decimal) for the reference asset.
            e.g. GOLDBEES close prices or USDINR=X close prices.

    Returns:
        (converted, denom_data_as_of)
        converted: subset of prices restricted to dates in BOTH series.
            For each common date: close = close_inr / denom_close, quantize 4dp.
            open/high/low set to None (not available in alternative denominations).
            volume preserved unchanged.
        denom_data_as_of: max date in denom_series, or None if empty.

    Invariants:
        - Output dates are a subset of input price dates (common intersection only).
        - close is None when close_inr is None OR denom_price == 0.
        - All Decimal operations quantize(Decimal("0.0001")).
    """
    if not denom_series:
        return [], None

    denom_map: dict[date, Decimal] = {d: p for d, p in denom_series}
    denom_data_as_of: Optional[date] = max(denom_map.keys())

    converted: list[dict[str, Any]] = []
    for row in prices:
        row_date: date = row["date"]
        denom_price = denom_map.get(row_date)
        if denom_price is None:
            continue  # Not in denominator series — exclude (common intersection)

        new_row: dict[str, Any] = {
            "date": row_date,
            "volume": row.get("volume"),
            "open": None,
            "high": None,
            "low": None,
            "close": None,
        }
        close_inr = row.get("close")
        if close_inr is not None and denom_price != Decimal("0"):
            new_row["close"] = (Decimal(str(close_inr)) / denom_price).quantize(Decimal("0.0001"))

        converted.append(new_row)

    return converted, denom_data_as_of
