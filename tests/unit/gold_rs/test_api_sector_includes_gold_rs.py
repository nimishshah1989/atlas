"""Test that GoldRSResult model can be composed into sector RRG payloads.

Validates the Pydantic model compiles, field types are correct,
and None periods are handled gracefully — tests the additive gold_rs block
pattern for the sector RRG route (V7-1 will wire the actual route).
"""

from datetime import date
from decimal import Decimal

from backend.models.gold_rs import GoldRSCacheEntry, GoldRSPeriods, GoldRSResult


def test_gold_rs_result_model() -> None:
    """GoldRSResult model compiles and has expected fields."""
    result = GoldRSResult(
        entity_type="sector",
        entity_id="NIFTY_IT",
        date=date(2026, 4, 17),
        periods=GoldRSPeriods(
            rs_vs_gold_1m=Decimal("2.50"),
            rs_vs_gold_3m=Decimal("1.20"),
            rs_vs_gold_6m=None,
            rs_vs_gold_12m=Decimal("-0.80"),
        ),
        gold_rs_signal="AMPLIFIES_BULL",
        gold_series="GLD",
        is_stale=False,
    )
    assert result.gold_rs_signal == "AMPLIFIES_BULL"
    assert result.periods.rs_vs_gold_1m == Decimal("2.50")
    assert result.periods.rs_vs_gold_6m is None
    assert result.entity_type == "sector"
    assert result.entity_id == "NIFTY_IT"
    assert not result.is_stale


def test_gold_rs_periods_all_none() -> None:
    """Periods with all None values is valid (insufficient data state)."""
    periods = GoldRSPeriods()
    assert periods.rs_vs_gold_1m is None
    assert periods.rs_vs_gold_3m is None
    assert periods.rs_vs_gold_6m is None
    assert periods.rs_vs_gold_12m is None


def test_gold_rs_result_stale_model() -> None:
    """GoldRSResult with STALE signal and is_stale=True is valid."""
    result = GoldRSResult(
        entity_type="equity",
        entity_id="RELIANCE",
        date=date(2026, 4, 17),
        periods=GoldRSPeriods(),  # all None
        gold_rs_signal="STALE",
        gold_series="GLD",
        is_stale=True,
    )
    assert result.gold_rs_signal == "STALE"
    assert result.is_stale is True
    assert result.periods.rs_vs_gold_1m is None


def test_gold_rs_cache_entry_from_result() -> None:
    """GoldRSCacheEntry.from_result() mirrors GoldRSResult fields."""
    result = GoldRSResult(
        entity_type="etf",
        entity_id="NIFTYBEES",
        date=date(2026, 4, 17),
        periods=GoldRSPeriods(
            rs_vs_gold_1m=Decimal("1.50"),
            rs_vs_gold_3m=None,
            rs_vs_gold_6m=Decimal("-0.30"),
            rs_vs_gold_12m=Decimal("2.10"),
        ),
        gold_rs_signal="AMPLIFIES_BULL",
        gold_series="GOLDBEES",
        is_stale=False,
    )
    entry = GoldRSCacheEntry.from_result(result)
    assert entry.entity_type == "etf"
    assert entry.entity_id == "NIFTYBEES"
    assert entry.rs_vs_gold_1m == Decimal("1.50")
    assert entry.rs_vs_gold_3m is None
    assert entry.gold_rs_signal == "AMPLIFIES_BULL"
    assert entry.gold_series == "GOLDBEES"


def test_gold_rs_result_all_signal_types_valid() -> None:
    """All five valid signal types pass model validation."""
    signals = ["AMPLIFIES_BULL", "AMPLIFIES_BEAR", "NEUTRAL_BENCH_ONLY", "FRAGILE", "STALE"]
    for signal in signals:
        result = GoldRSResult(
            entity_type="equity",
            entity_id=f"TEST_{signal}",
            date=date(2026, 4, 17),
            periods=GoldRSPeriods(),
            gold_rs_signal=signal,  # type: ignore[arg-type]
            gold_series="GLD",
        )
        assert result.gold_rs_signal == signal
