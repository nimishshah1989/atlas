"""Tests for backend/services/adjustment_service.py.

Pure computation tests — no DB, no async, no mocks needed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from backend.services.adjustment_service import (
    apply_adjustment,
    compute_adjustment_schedule,
    get_factor_for_date,
)


# ---------------------------------------------------------------------------
# compute_adjustment_schedule
# ---------------------------------------------------------------------------


def test_compute_schedule_empty_actions() -> None:
    """No actions -> empty schedule."""
    result = compute_adjustment_schedule([])
    assert result == []


def test_compute_schedule_single_bonus() -> None:
    """One bonus adj_factor=0.5 -> schedule has one entry with factor=0.5."""
    actions = [{"ex_date": date(2024, 1, 15), "adj_factor": Decimal("0.5")}]
    schedule = compute_adjustment_schedule(actions)
    assert len(schedule) == 1
    assert schedule[0][0] == date(2024, 1, 15)
    assert schedule[0][1] == Decimal("0.5")


def test_compute_schedule_multiple_events() -> None:
    """Two events: suffix products verified.

    Events: 2024-01-01 factor=0.5, 2024-06-01 factor=0.5
    suffix[0] = 0.5 * 0.5 = 0.25
    suffix[1] = 0.5
    """
    actions = [
        {"ex_date": date(2024, 1, 1), "adj_factor": Decimal("0.5")},
        {"ex_date": date(2024, 6, 1), "adj_factor": Decimal("0.5")},
    ]
    schedule = compute_adjustment_schedule(actions)
    assert len(schedule) == 2
    assert schedule[0][0] == date(2024, 1, 1)
    assert schedule[0][1] == Decimal("0.25")  # suffix product of both
    assert schedule[1][0] == date(2024, 6, 1)
    assert schedule[1][1] == Decimal("0.5")  # only last factor


def test_compute_schedule_deduplicates_same_date() -> None:
    """Two events on same date -> single entry with product of factors."""
    actions = [
        {"ex_date": date(2024, 3, 1), "adj_factor": Decimal("0.5")},
        {"ex_date": date(2024, 3, 1), "adj_factor": Decimal("0.5")},
    ]
    schedule = compute_adjustment_schedule(actions)
    assert len(schedule) == 1
    # 0.5 * 0.5 = 0.25
    assert schedule[0][1] == Decimal("0.25")


def test_compute_schedule_skips_null_adj_factor() -> None:
    """Null adj_factor entries are silently ignored."""
    actions = [
        {"ex_date": date(2024, 1, 1), "adj_factor": None},
        {"ex_date": date(2024, 6, 1), "adj_factor": Decimal("0.5")},
    ]
    schedule = compute_adjustment_schedule(actions)
    assert len(schedule) == 1
    assert schedule[0][0] == date(2024, 6, 1)


def test_compute_schedule_skips_zero_adj_factor() -> None:
    """Zero adj_factor entries are silently ignored (prevents zero product)."""
    actions = [
        {"ex_date": date(2024, 1, 1), "adj_factor": Decimal("0")},
        {"ex_date": date(2024, 6, 1), "adj_factor": Decimal("0.5")},
    ]
    schedule = compute_adjustment_schedule(actions)
    assert len(schedule) == 1
    assert schedule[0][0] == date(2024, 6, 1)


def test_compute_schedule_string_adj_factor() -> None:
    """String adj_factor (from DB mapping) is handled via Decimal(str())."""
    actions = [{"ex_date": date(2024, 1, 1), "adj_factor": "0.5"}]
    schedule = compute_adjustment_schedule(actions)
    assert len(schedule) == 1
    assert isinstance(schedule[0][1], Decimal)


# ---------------------------------------------------------------------------
# get_factor_for_date
# ---------------------------------------------------------------------------


def test_get_factor_before_all_events() -> None:
    """Date before first event -> full cumulative factor (suffix[0])."""
    schedule = [
        (date(2024, 3, 1), Decimal("0.25")),
        (date(2024, 9, 1), Decimal("0.5")),
    ]
    factor = get_factor_for_date(schedule, date(2024, 1, 1))
    assert factor == Decimal("0.25")


def test_get_factor_between_events() -> None:
    """Date between two events -> factor from second event."""
    schedule = [
        (date(2024, 3, 1), Decimal("0.25")),
        (date(2024, 9, 1), Decimal("0.5")),
    ]
    factor = get_factor_for_date(schedule, date(2024, 6, 1))
    assert factor == Decimal("0.5")


def test_get_factor_after_all_events() -> None:
    """Date after last event -> Decimal('1') (no future events)."""
    schedule = [
        (date(2024, 3, 1), Decimal("0.25")),
        (date(2024, 9, 1), Decimal("0.5")),
    ]
    factor = get_factor_for_date(schedule, date(2025, 1, 1))
    assert factor == Decimal("1")


def test_get_factor_empty_schedule() -> None:
    """Empty schedule -> always returns Decimal('1')."""
    factor = get_factor_for_date([], date(2024, 6, 1))
    assert factor == Decimal("1")


def test_get_factor_on_ex_date_itself() -> None:
    """Date exactly on ex_date -> ex_date is NOT > row_date, so next factor applies."""
    # ex_date=2024-03-01, row_date=2024-03-01 -> ex_date > row_date is False
    # meaning price on the ex_date itself is NOT adjusted by that event
    schedule = [
        (date(2024, 3, 1), Decimal("0.5")),
    ]
    factor = get_factor_for_date(schedule, date(2024, 3, 1))
    assert factor == Decimal("1")  # price ON the event date is not adjusted


# ---------------------------------------------------------------------------
# apply_adjustment
# ---------------------------------------------------------------------------


def _make_price_row(
    d: date,
    open_: str,
    high: str,
    low: str,
    close: str,
    volume: int = 1000,
) -> dict[str, Any]:
    return {
        "date": d,
        "open": Decimal(open_),
        "high": Decimal(high),
        "low": Decimal(low),
        "close": Decimal(close),
        "volume": volume,
    }


def test_apply_adjustment_no_schedule() -> None:
    """Empty schedule -> prices returned unchanged (passthrough)."""
    prices = [_make_price_row(date(2024, 1, 1), "100", "110", "90", "105")]
    result = apply_adjustment(prices, [])
    assert result is prices  # exact same object returned


def test_apply_adjustment_halves_price_before_bonus() -> None:
    """1:1 bonus adj_factor=0.5 — prices before event are halved."""
    schedule = [(date(2024, 6, 1), Decimal("0.5"))]
    prices = [_make_price_row(date(2024, 1, 1), "100", "110", "90", "105")]
    result = apply_adjustment(prices, schedule)
    assert len(result) == 1
    row = result[0]
    assert row["close"] == Decimal("52.5000")
    assert row["open"] == Decimal("50.0000")
    assert row["high"] == Decimal("55.0000")
    assert row["low"] == Decimal("45.0000")


def test_apply_adjustment_no_change_after_event() -> None:
    """Prices after the last event date are unchanged (factor=1)."""
    schedule = [(date(2024, 6, 1), Decimal("0.5"))]
    # price row AFTER the event — no adjustment
    prices = [_make_price_row(date(2024, 12, 1), "100", "110", "90", "105")]
    result = apply_adjustment(prices, schedule)
    assert result[0]["close"] == Decimal("105.0000")
    assert result[0]["open"] == Decimal("100.0000")


def test_apply_adjustment_volume_not_adjusted() -> None:
    """Volume is NOT adjusted — stays as original value."""
    schedule = [(date(2024, 6, 1), Decimal("0.5"))]
    prices = [_make_price_row(date(2024, 1, 1), "100", "110", "90", "105", volume=500000)]
    result = apply_adjustment(prices, schedule)
    assert result[0]["volume"] == 500000


def test_apply_adjustment_none_values() -> None:
    """None OHLC values remain None after adjustment."""
    schedule = [(date(2024, 6, 1), Decimal("0.5"))]
    prices = [
        {
            "date": date(2024, 1, 1),
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": 1000,
        }
    ]
    result = apply_adjustment(prices, schedule)
    row = result[0]
    assert row["open"] is None
    assert row["high"] is None
    assert row["low"] is None
    assert row["close"] is None


def test_apply_adjustment_does_not_mutate_input() -> None:
    """Input price rows are not mutated — apply_adjustment returns new dicts."""
    schedule = [(date(2024, 6, 1), Decimal("0.5"))]
    original_close = Decimal("100")
    prices = [_make_price_row(date(2024, 1, 1), "100", "110", "90", "100")]
    result = apply_adjustment(prices, schedule)
    # Input unchanged
    assert prices[0]["close"] == original_close
    # Output adjusted
    assert result[0]["close"] == Decimal("50.0000")


def test_no_float_in_output() -> None:
    """Output contains only Decimal/int/date, no float values."""
    schedule = [(date(2024, 6, 1), Decimal("0.5"))]
    prices = [_make_price_row(date(2024, 1, 1), "100.50", "110.75", "90.25", "105.00")]
    result = apply_adjustment(prices, schedule)
    row = result[0]
    for col in ("open", "high", "low", "close"):
        val = row.get(col)
        if val is not None:
            assert isinstance(val, Decimal), f"{col} should be Decimal, got {type(val)}: {val}"
            assert not isinstance(val, float), f"{col} must not be float"
