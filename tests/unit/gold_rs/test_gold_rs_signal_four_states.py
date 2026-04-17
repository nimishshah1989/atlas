"""Test compute_gold_rs_signal four signal states.

Tests the AMPLIFIES_BULL / AMPLIFIES_BEAR / NEUTRAL_BENCH_ONLY / FRAGILE
classification matrix, plus edge cases (zero-boundary, None inputs).
"""

from decimal import Decimal

import pytest

from backend.services.gold_rs_service import GoldRSService

svc = GoldRSService()


@pytest.mark.parametrize(
    "bench,gold,expected",
    [
        (Decimal("1.0"), Decimal("2.0"), "AMPLIFIES_BULL"),
        (Decimal("-1.0"), Decimal("-2.0"), "AMPLIFIES_BEAR"),
        (Decimal("1.0"), Decimal("-2.0"), "NEUTRAL_BENCH_ONLY"),
        (Decimal("-1.0"), Decimal("2.0"), "FRAGILE"),
    ],
)
def test_gold_rs_signal_four_states(bench: Decimal, gold: Decimal, expected: str) -> None:
    """Parametrized test covering all four primary signal states."""
    result = svc.compute_gold_rs_signal(
        rs_benchmark=bench,
        rs_gold=gold,
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == expected, f"bench={bench}, gold={gold}: expected {expected!r}, got {result!r}"


def test_gold_rs_signal_zero_bench_is_fragile() -> None:
    """Exact zero bench → FRAGILE (strict > not >=)."""
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("0"),
        rs_gold=Decimal("1.0"),
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "FRAGILE", f"Zero bench should be FRAGILE, got {result!r}"


def test_gold_rs_signal_zero_gold_is_fragile() -> None:
    """Exact zero gold RS → FRAGILE (strict > not >=)."""
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("1.0"),
        rs_gold=Decimal("0"),
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "FRAGILE", f"Zero gold should be FRAGILE, got {result!r}"


def test_gold_rs_signal_both_zero_is_fragile() -> None:
    """Both zero → FRAGILE."""
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("0"),
        rs_gold=Decimal("0"),
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "FRAGILE"


def test_gold_rs_signal_none_bench_is_fragile() -> None:
    """None benchmark → FRAGILE (can't classify without both inputs)."""
    result = svc.compute_gold_rs_signal(
        rs_benchmark=None,
        rs_gold=Decimal("2.0"),
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "FRAGILE"


def test_gold_rs_signal_none_gold_rs_is_fragile() -> None:
    """None gold RS → FRAGILE (can't classify without both inputs)."""
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("2.0"),
        rs_gold=None,
        gold_missing=False,
        yesterday_age_days=0,
    )
    assert result == "FRAGILE"
