"""Test compute_rs_vs_gold basic arithmetic.

Instrument 5% return, gold 3% return over 21 days → rs_1m = Decimal("2.00").
With only 22 data points, 3m/6m/12m should be None (insufficient data).
"""

from datetime import date
from decimal import Decimal

from backend.services.gold_rs_service import GoldRSService


def _build_linear_series(
    start_price: Decimal,
    total_return_pct: Decimal,
    n_points: int,
    start_date: date,
) -> list[tuple[date, Decimal]]:
    """Build a linearly-interpolated price series.

    Args:
        start_price: Price at day 0.
        total_return_pct: Total return as percentage (e.g. Decimal("5") = 5%).
        n_points: Number of data points (n_days = n_points - 1).
        start_date: Date of first data point.

    Returns:
        List of (date, Decimal(price)) with dates incremented by 1 calendar day.
    """
    end_price = start_price * (Decimal("1") + total_return_pct / Decimal("100"))
    series = []
    for i in range(n_points):
        d = date(start_date.year, start_date.month, start_date.day)
        # Increment date by i days
        import datetime as dt_mod

        d = start_date + dt_mod.timedelta(days=i)
        price = start_price + (end_price - start_price) * Decimal(i) / Decimal(n_points - 1)
        series.append((d, price))
    return series


def test_compute_rs_vs_gold_basic() -> None:
    """Instrument 5% return, gold 3% return over 21 days → rs_1m ≈ Decimal('2.00').

    With only 22 aligned points, periods requiring >22 points (63, 126, 252) → None.
    """
    svc = GoldRSService()

    # 22 data points = 21-day return window (n+1 points for n-day window)
    instrument = [
        (date(2026, 1, i + 1), Decimal("100") + Decimal("5") * Decimal(i) / Decimal(21))
        for i in range(22)
    ]
    gold = [
        (date(2026, 1, i + 1), Decimal("100") + Decimal("3") * Decimal(i) / Decimal(21))
        for i in range(22)
    ]

    periods = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
    result = svc.compute_rs_vs_gold(instrument, gold, periods)

    # rs_1m = instrument_return_pct - gold_return_pct = 5.00 - 3.00 = 2.00
    assert result["1m"] is not None, "rs_1m should not be None with 22 aligned points"
    assert isinstance(result["1m"], Decimal), "rs_1m must be Decimal, not float"
    assert abs(result["1m"] - Decimal("2.00")) < Decimal("0.01"), (
        f"Expected rs_1m ≈ 2.00, got {result['1m']}"
    )

    # With only 22 points, 63/126/252-day windows are impossible → None
    assert result["3m"] is None, "rs_3m should be None (insufficient data)"
    assert result["6m"] is None, "rs_6m should be None (insufficient data)"
    assert result["12m"] is None, "rs_12m should be None (insufficient data)"


def test_compute_rs_vs_gold_all_periods() -> None:
    """With 253 aligned points, all four periods should populate."""
    svc = GoldRSService()

    # Build 253-point series (covers 252-day window)
    import datetime as dt_mod

    start = date(2025, 1, 1)
    instrument = [
        (start + dt_mod.timedelta(days=i), Decimal("100") + Decimal(i) * Decimal("0.05"))
        for i in range(253)
    ]
    gold = [
        (start + dt_mod.timedelta(days=i), Decimal("200") + Decimal(i) * Decimal("0.02"))
        for i in range(253)
    ]

    periods = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
    result = svc.compute_rs_vs_gold(instrument, gold, periods)

    # All periods should have non-None Decimal results
    for key in ("1m", "3m", "6m", "12m"):
        assert result[key] is not None, f"rs_{key} should not be None with 253 points"
        assert isinstance(result[key], Decimal), f"rs_{key} must be Decimal, not float"


def test_compute_rs_vs_gold_no_float_in_result() -> None:
    """Result dict must contain no float values — only Decimal or None."""
    svc = GoldRSService()

    instrument = [(date(2026, 1, i + 1), Decimal("100") + Decimal(i)) for i in range(22)]
    gold = [(date(2026, 1, i + 1), Decimal("200") + Decimal(i)) for i in range(22)]

    result = svc.compute_rs_vs_gold(instrument, gold, {"1m": 21})
    for key, val in result.items():
        assert val is None or isinstance(val, Decimal), (
            f"Period {key!r} has float value {val!r} — must be Decimal or None"
        )
