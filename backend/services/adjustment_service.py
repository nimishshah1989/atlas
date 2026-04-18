"""Adjustment factor service — back-adjusted price computation.

All arithmetic is Decimal. No float. No DB calls. Pure computation only.
Standard back-adjustment: historical prices multiplied by product of
adj_factors for all corporate events that occurred AFTER that date.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any


def compute_adjustment_schedule(
    actions: list[dict[str, Any]],
) -> list[tuple[date, Decimal]]:
    """Build sorted list of (event_date, cumulative_factor_for_prices_before_event).

    Suffix product approach: schedule[i] = (ex_date[i], product(adj_factors[i..N-1]))
    For a price on date D: find first schedule entry where ex_date > D, apply its factor.
    If no such entry exists, apply Decimal("1") (no future events, no adjustment needed).

    Args:
        actions: list of dicts with 'ex_date' (date) and 'adj_factor' (Decimal|None|str).
            Only entries with non-None, non-zero adj_factor are used.

    Returns:
        List of (ex_date, cum_factor) sorted ASC by ex_date.
    """
    valid: list[tuple[date, Decimal]] = []
    for a in actions:
        raw = a.get("adj_factor")
        if raw is None:
            continue
        factor = Decimal(str(raw))
        if factor == Decimal("0"):
            continue
        valid.append((a["ex_date"], factor))

    if not valid:
        return []

    # Sort by ex_date ASC
    valid.sort(key=lambda x: x[0])

    # Deduplicate by ex_date: multiply factors on same date
    deduped: list[list[Any]] = []
    for ex_date, factor in valid:
        if deduped and deduped[-1][0] == ex_date:
            deduped[-1][1] = deduped[-1][1] * factor
        else:
            deduped.append([ex_date, factor])

    # Build suffix products (right to left)
    n = len(deduped)
    suffix: list[Decimal] = [Decimal("1")] * n
    suffix[n - 1] = deduped[n - 1][1]
    for i in range(n - 2, -1, -1):
        suffix[i] = deduped[i][1] * suffix[i + 1]

    return [(deduped[i][0], suffix[i]) for i in range(n)]


def get_factor_for_date(
    schedule: list[tuple[date, Decimal]],
    row_date: date,
) -> Decimal:
    """Return the cumulative adjustment factor for a price row on row_date.

    Returns Decimal("1") if no corporate events occurred after row_date.
    """
    for ex_date, cum_factor in schedule:
        if ex_date > row_date:
            return cum_factor
    return Decimal("1")


def apply_adjustment(
    prices: list[dict[str, Any]],
    schedule: list[tuple[date, Decimal]],
) -> list[dict[str, Any]]:
    """Apply back-adjustment to a list of OHLCV price rows.

    Multiplies open/high/low/close by the cumulative factor for each row's date.
    Volume is NOT adjusted. Returns new dicts — input rows are not mutated.

    Args:
        prices: List of dicts with 'date' (date), 'open', 'high', 'low', 'close'
            (Decimal|None).
        schedule: Output of compute_adjustment_schedule().

    Returns:
        List of dicts with adjusted OHLC values (Decimal, 4 decimal places).
    """
    if not schedule:
        return prices

    adjusted_rows: list[dict[str, Any]] = []
    for row in prices:
        row_date: date = row["date"]
        factor = get_factor_for_date(schedule, row_date)
        adjusted = dict(row)
        for col in ("open", "high", "low", "close"):
            raw_price = row.get(col)
            if raw_price is not None:
                adjusted[col] = (Decimal(str(raw_price)) * factor).quantize(Decimal("0.0001"))
        adjusted_rows.append(adjusted)
    return adjusted_rows
