"""Test rs_1m=None when gold series has insufficient aligned data.

When gold data is sparse (e.g. missing days 10-15), the intersection of
instrument and gold dates may have fewer points than the period window.
In that case, the result must be None — never 0, never NaN.
"""

from datetime import date
from decimal import Decimal

from backend.services.gold_rs_service import GoldRSService


def test_gold_rs_null_on_missing_price() -> None:
    """Gold with only 5 data points → not enough for 21-day window → None.

    Instrument has 22 days (days 1-22).
    Gold only has 5 data points (days 1-5).
    Intersection = 5 points.
    Need 22 points for 21-day window → None.
    """
    svc = GoldRSService()

    # Instrument has full 22 days
    instrument = [(date(2026, 1, i + 1), Decimal("100") + Decimal(i)) for i in range(22)]
    # Gold only has 5 points (days 1-5) — insufficient for any window
    gold = [(date(2026, 1, i + 1), Decimal("200") + Decimal(i)) for i in range(5)]

    periods = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
    result = svc.compute_rs_vs_gold(instrument, gold, periods)

    # Only 5 aligned points — not enough for 21-day period → None
    assert result["1m"] is None, (
        f"Expected None for rs_1m with sparse gold data, got {result['1m']!r}"
    )
    # Must not be 0 (zero would be a sentinel, not 'no data')
    assert result["1m"] != Decimal("0"), "None result must not be 0"
    # Must not be NaN (None is the correct sentinel for missing data)
    assert result["1m"] is not float("nan"), "None result must not be NaN"

    # All other periods also None
    assert result["3m"] is None
    assert result["6m"] is None
    assert result["12m"] is None


def test_gold_rs_null_on_no_overlap() -> None:
    """When gold and instrument series have zero date overlap → all None."""
    svc = GoldRSService()

    # Instrument: Jan 2026
    instrument = [(date(2026, 1, i + 1), Decimal("100") + Decimal(i)) for i in range(22)]
    # Gold: Feb 2026 — no overlap
    gold = [(date(2026, 2, i + 1), Decimal("200") + Decimal(i)) for i in range(22)]

    result = svc.compute_rs_vs_gold(instrument, gold, {"1m": 21})
    assert result["1m"] is None, "Zero-overlap series must produce None, not error"


def test_gold_rs_null_never_raises_on_short_series() -> None:
    """compute_rs_vs_gold with 1-point series must return None, not raise."""
    svc = GoldRSService()

    instrument = [(date(2026, 1, 1), Decimal("100"))]
    gold = [(date(2026, 1, 1), Decimal("200"))]

    # Should not raise
    result = svc.compute_rs_vs_gold(instrument, gold, {"1m": 21, "3m": 63})
    assert result["1m"] is None
    assert result["3m"] is None
