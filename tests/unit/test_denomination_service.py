"""Unit tests for backend.services.denomination_service.apply_denomination.

Pure computation tests — no DB, no mocks, no async.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from backend.services.denomination_service import apply_denomination


# ---------------------------------------------------------------------------
# Helper to build a price row
# ---------------------------------------------------------------------------


def _price_row(
    d: date,
    close: Decimal | None = None,
    open_: Decimal | None = None,
    high: Decimal | None = None,
    low: Decimal | None = None,
    volume: int | None = None,
) -> dict[str, Any]:
    return {
        "date": d,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_basic_gold_denomination_divides_correctly() -> None:
    """close = 1020 / 100 = 10.2000 (4dp)."""
    prices = [_price_row(date(2025, 1, 2), close=Decimal("1020"))]
    denom = [(date(2025, 1, 2), Decimal("100.0000"))]

    result, denom_as_of = apply_denomination(prices, denom)

    assert len(result) == 1
    assert result[0]["close"] == Decimal("10.2000")
    assert denom_as_of == date(2025, 1, 2)


def test_basic_usd_denomination_divides_correctly() -> None:
    """close = 1020 / 84.5 = 12.0710 (quantized 4dp)."""
    prices = [_price_row(date(2025, 1, 2), close=Decimal("1020.0000"))]
    denom = [(date(2025, 1, 2), Decimal("84.5000"))]

    result, denom_as_of = apply_denomination(prices, denom)

    assert len(result) == 1
    expected = (Decimal("1020.0000") / Decimal("84.5000")).quantize(Decimal("0.0001"))
    assert result[0]["close"] == expected


def test_common_intersection_excludes_date_missing_in_denom() -> None:
    """Date present in prices but not in denom_series is excluded from output."""
    prices = [
        _price_row(date(2025, 1, 2), close=Decimal("1000")),
        _price_row(date(2025, 1, 3), close=Decimal("1010")),
    ]
    denom = [(date(2025, 1, 2), Decimal("100"))]  # only first date

    result, _ = apply_denomination(prices, denom)

    assert len(result) == 1
    assert result[0]["date"] == date(2025, 1, 2)


def test_extra_dates_in_denom_not_in_prices_are_ignored() -> None:
    """Extra dates in denom_series that have no corresponding price row are ignored."""
    prices = [_price_row(date(2025, 1, 2), close=Decimal("500"))]
    denom = [
        (date(2025, 1, 2), Decimal("50")),
        (date(2025, 1, 3), Decimal("51")),  # no matching price
        (date(2025, 1, 4), Decimal("52")),  # no matching price
    ]

    result, denom_as_of = apply_denomination(prices, denom)

    assert len(result) == 1
    assert denom_as_of == date(2025, 1, 4)  # max of denom dates


def test_zero_denominator_sets_close_to_none() -> None:
    """When denom_price is 0, close must be None (no division by zero)."""
    prices = [_price_row(date(2025, 1, 2), close=Decimal("1000"))]
    denom = [(date(2025, 1, 2), Decimal("0"))]

    result, _ = apply_denomination(prices, denom)

    assert len(result) == 1
    assert result[0]["close"] is None


def test_none_close_inr_produces_none_in_output() -> None:
    """When close_inr is None, output close is also None."""
    prices = [_price_row(date(2025, 1, 2), close=None)]
    denom = [(date(2025, 1, 2), Decimal("100"))]

    result, _ = apply_denomination(prices, denom)

    assert len(result) == 1
    assert result[0]["close"] is None


def test_empty_denom_series_returns_empty_list_and_none() -> None:
    """Empty denom_series -> ([], None) regardless of prices content."""
    prices = [_price_row(date(2025, 1, 2), close=Decimal("1000"))]

    result, denom_as_of = apply_denomination(prices, [])

    assert result == []
    assert denom_as_of is None


def test_empty_prices_with_nonempty_denom_returns_empty_with_denom_as_of() -> None:
    """prices=[] but denom_series non-empty -> ([], max(denom_dates))."""
    denom = [(date(2025, 1, 2), Decimal("100")), (date(2025, 6, 1), Decimal("120"))]

    result, denom_as_of = apply_denomination([], denom)

    assert result == []
    assert denom_as_of == date(2025, 6, 1)


def test_denom_data_as_of_is_max_date_in_denom_series() -> None:
    """denom_data_as_of is always the maximum date in denom_series."""
    prices = [_price_row(date(2025, 6, 1), close=Decimal("1000"))]
    denom = [
        (date(2025, 1, 2), Decimal("90")),
        (date(2025, 3, 15), Decimal("95")),
        (date(2025, 6, 1), Decimal("100")),
    ]

    _, denom_as_of = apply_denomination(prices, denom)

    assert denom_as_of == date(2025, 6, 1)


def test_ohlv_fields_are_none_and_volume_preserved() -> None:
    """open/high/low are None in output; volume is preserved unchanged."""
    prices = [
        _price_row(
            date(2025, 1, 2),
            close=Decimal("1000"),
            open_=Decimal("990"),
            high=Decimal("1020"),
            low=Decimal("985"),
            volume=500_000,
        )
    ]
    denom = [(date(2025, 1, 2), Decimal("100"))]

    result, _ = apply_denomination(prices, denom)

    assert len(result) == 1
    row = result[0]
    assert row["open"] is None
    assert row["high"] is None
    assert row["low"] is None
    assert row["volume"] == 500_000


def test_multiple_rows_all_computed_correctly() -> None:
    """All rows in the intersection are computed with correct 4dp results."""
    prices = [
        _price_row(date(2025, 1, 2), close=Decimal("1000")),
        _price_row(date(2025, 3, 1), close=Decimal("1200")),
        _price_row(date(2025, 6, 1), close=Decimal("800")),
    ]
    denom = [
        (date(2025, 1, 2), Decimal("50")),
        (date(2025, 3, 1), Decimal("60")),
        (date(2025, 6, 1), Decimal("40")),
    ]

    result, _ = apply_denomination(prices, denom)

    assert len(result) == 3
    assert result[0]["close"] == (Decimal("1000") / Decimal("50")).quantize(Decimal("0.0001"))
    assert result[1]["close"] == (Decimal("1200") / Decimal("60")).quantize(Decimal("0.0001"))
    assert result[2]["close"] == (Decimal("800") / Decimal("40")).quantize(Decimal("0.0001"))


def test_quantization_to_exactly_4_decimal_places() -> None:
    """Output close always has exactly 4 decimal places (quantized)."""
    prices = [_price_row(date(2025, 1, 2), close=Decimal("100"))]
    denom = [(date(2025, 1, 2), Decimal("3"))]

    result, _ = apply_denomination(prices, denom)

    assert len(result) == 1
    close_val = result[0]["close"]
    assert close_val is not None
    # 100/3 = 33.3333... -> quantized to 33.3333
    assert close_val == Decimal("33.3333")
    # Verify it's stored as Decimal, not float
    assert isinstance(close_val, Decimal)
    # Verify exactly 4 decimal places
    assert close_val == close_val.quantize(Decimal("0.0001"))


def test_mixed_none_and_valid_close_in_batch() -> None:
    """Batch with some None close and some valid close handled correctly."""
    prices = [
        _price_row(date(2025, 1, 2), close=None),  # None close
        _price_row(date(2025, 1, 3), close=Decimal("200")),  # valid
        _price_row(date(2025, 1, 4), close=Decimal("0")),  # zero price
    ]
    denom = [
        (date(2025, 1, 2), Decimal("10")),
        (date(2025, 1, 3), Decimal("10")),
        (date(2025, 1, 4), Decimal("10")),
    ]

    result, _ = apply_denomination(prices, denom)

    assert len(result) == 3
    assert result[0]["close"] is None  # None/10 = None
    assert result[1]["close"] == Decimal("20.0000")  # 200/10 = 20.0
    assert result[2]["close"] == Decimal("0.0000")  # 0/10 = 0


def test_no_float_in_output() -> None:
    """Verify no float values appear in the output (only Decimal or None)."""
    prices = [_price_row(date(2025, 1, 2), close=Decimal("1234.5678"), volume=999)]
    denom = [(date(2025, 1, 2), Decimal("7.8901"))]

    result, _ = apply_denomination(prices, denom)

    assert len(result) == 1
    row = result[0]
    for key, val in row.items():
        if val is not None and key != "date" and key != "volume":
            assert isinstance(val, Decimal), f"{key} should be Decimal, got {type(val)}: {val}"
        if isinstance(val, float):
            pytest.fail(f"Float found at key '{key}': {val}")
