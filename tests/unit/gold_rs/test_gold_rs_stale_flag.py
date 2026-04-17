"""Test STALE signal when gold data is missing and age > 2 days."""

from decimal import Decimal

from backend.services.gold_rs_service import GoldRSService


def test_gold_rs_stale_when_missing_and_old() -> None:
    """gold_missing=True AND yesterday_age_days=3 → STALE."""
    svc = GoldRSService()
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("1.0"),
        rs_gold=None,
        gold_missing=True,
        yesterday_age_days=3,
    )
    assert result == "STALE", f"Expected STALE when gold missing >2 days, got {result!r}"


def test_gold_rs_not_stale_when_recent() -> None:
    """gold_missing=True BUT age_days=2 (not > 2) → not STALE → FRAGILE.

    The STALE condition is strict: yesterday_age_days > 2.
    Age of exactly 2 days is NOT stale → falls through to FRAGILE
    (rs_gold is None so can't classify AMPLIFIES_* or NEUTRAL).
    """
    svc = GoldRSService()
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("1.0"),
        rs_gold=None,
        gold_missing=True,
        yesterday_age_days=2,
    )
    assert result == "FRAGILE", f"Expected FRAGILE when gold age=2 (not >2), got {result!r}"


def test_gold_rs_stale_boundary_exactly_two() -> None:
    """gold_missing + age=2 → still not STALE (boundary is exclusive)."""
    svc = GoldRSService()
    result = svc.compute_gold_rs_signal(
        rs_benchmark=None,
        rs_gold=None,
        gold_missing=True,
        yesterday_age_days=2,
    )
    # age=2 is not > 2, not STALE
    assert result != "STALE"
    # Both bench and gold are None → FRAGILE
    assert result == "FRAGILE"


def test_gold_rs_stale_overrides_all_other_signals() -> None:
    """STALE fires first even when bench/gold values are positive."""
    svc = GoldRSService()
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("5.0"),  # positive
        rs_gold=Decimal("3.0"),  # positive
        gold_missing=True,
        yesterday_age_days=5,  # >2
    )
    # STALE takes priority over the AMPLIFIES_BULL condition
    assert result == "STALE", (
        f"Expected STALE to override AMPLIFIES_BULL when gold missing >2 days, got {result!r}"
    )


def test_gold_rs_not_stale_when_gold_not_missing() -> None:
    """gold_missing=False → STALE condition never fires regardless of age."""
    svc = GoldRSService()
    result = svc.compute_gold_rs_signal(
        rs_benchmark=Decimal("1.0"),
        rs_gold=Decimal("2.0"),
        gold_missing=False,
        yesterday_age_days=10,  # very old, but gold_missing=False
    )
    # STALE requires gold_missing=True — False means no STALE
    assert result != "STALE"
    # With both positive → AMPLIFIES_BULL
    assert result == "AMPLIFIES_BULL"
