"""Test verdict derivation for four benchmark RS values.

Tests signal classification logic using compute_gold_rs_signal,
covering the primary use cases: all-positive, mixed, None-gold, stale.
"""

from decimal import Decimal

from backend.services.gold_rs_service import GoldRSService

svc = GoldRSService()


def test_strong_buy_all_positive() -> None:
    """All inputs positive → AMPLIFIES_BULL.

    bench=1.0, gold_rs=2.0 → both positive → AMPLIFIES_BULL.
    """
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("1.0"),
        rs_gold=Decimal("2.0"),
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "AMPLIFIES_BULL"


def test_buy_mixed_periods() -> None:
    """bench > 0 but gold_1m < 0 → NEUTRAL_BENCH_ONLY.

    The instrument outperforms the market benchmark but underperforms gold.
    This is a partial strength signal — benchmark only.
    """
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("1.0"),
        rs_gold=Decimal("-1.0"),
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "NEUTRAL_BENCH_ONLY"


def test_caution_insufficient_gold() -> None:
    """rs_gold=None (insufficient data) → FRAGILE.

    When gold RS can't be computed (None), classification is impossible.
    Returns FRAGILE regardless of benchmark sign.
    """
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("1.0"),
        rs_gold=None,
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "FRAGILE"


def test_all_negative_amplifies_bear() -> None:
    """bench < 0 AND gold_rs < 0 → AMPLIFIES_BEAR.

    Both benchmark and gold underperformance → bearish amplification.
    """
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("-2.0"),
        rs_gold=Decimal("-1.5"),
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "AMPLIFIES_BEAR"


def test_bear_outperforms_gold_is_fragile() -> None:
    """bench < 0 but gold_rs > 0 → FRAGILE.

    Instrument underperforms benchmark but outperforms gold.
    Mixed signal that doesn't fit the three named categories.
    """
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("-1.0"),
        rs_gold=Decimal("2.0"),
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "FRAGILE"


def test_stale_overrides_positive_signals() -> None:
    """STALE fires first when gold_missing=True AND age_days > 2."""
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("3.0"),
        rs_gold=Decimal("4.0"),
        gold_missing=True,
        yesterday_age_days=3,
    )
    assert result == "STALE"


def test_all_none_inputs_is_fragile() -> None:
    """Both bench and gold None → FRAGILE (not error, not STALE)."""
    result = svc.compute_gold_rs_signal(
        rs_benchmark=None,
        rs_gold=None,
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "FRAGILE"


def test_large_positive_values() -> None:
    """Large Decimal values should still produce correct classification."""
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("123.456789"),
        rs_gold=Decimal("0.000001"),  # tiny positive
        gold_missing=False,
        yesterday_age_days=0,
    )
    # Both positive → AMPLIFIES_BULL
    assert result == "AMPLIFIES_BULL"
