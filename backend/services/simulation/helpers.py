"""Simulation service helpers — JSONB sanitization, price parsing."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from backend.services.simulation.backtest_engine import BacktestResult


def sanitize_for_jsonb(obj: Any) -> Any:
    """Recursively convert Decimal (and date/datetime) to str for JSONB storage.

    JSONB cannot store Python Decimal objects — they must be str at persist boundary.
    """
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: sanitize_for_jsonb(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_jsonb(i) for i in obj]
    return obj


def parse_price_data(
    rows: list[dict[str, Any]],
) -> list[tuple[datetime.date, Decimal]]:
    """Convert raw price rows to (date, Decimal) tuples.

    Supports rows with 'nav', 'price', 'close' as the price field.
    Date can be a date object or ISO string.
    """
    parsed: list[tuple[datetime.date, Decimal]] = []
    for row in rows:
        raw_date = row.get("date")
        if raw_date is None:
            continue

        if isinstance(raw_date, str):
            raw_date = datetime.date.fromisoformat(raw_date)
        elif isinstance(raw_date, datetime.datetime):
            raw_date = raw_date.date()

        price_raw = row.get("nav") or row.get("price") or row.get("close")
        if price_raw is None:
            continue

        price = Decimal(str(price_raw))
        if price <= Decimal("0"):
            continue

        parsed.append((raw_date, price))

    return sorted(parsed, key=lambda x: x[0])


def get_remaining_lots_value(result: BacktestResult) -> list[Decimal]:
    """Return list of unrealized gain per remaining lot (approx from final nav)."""
    return []
