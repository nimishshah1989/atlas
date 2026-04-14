"""Tests for backend/services/mf_compute.py.

Covers:
- compute_rs_momentum_28d with exact Decimal equality on 10 fixture funds
- Returns None when <28 days of RS history (INSUFFICIENT_DATA scenario)
- 50-fund fixture producing quadrants matching hand-computed values
- classify_fund_quadrant boundary behaviour (zero treated as negative)
- enrich_fund_with_computations field passthrough
- compute_universe_metrics batch enrichment
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any, Optional

import pytest

from backend.models.schemas import Quadrant
from backend.services.mf_compute import (
    classify_fund_quadrant,
    compute_rs_momentum_28d,
    compute_universe_metrics,
    enrich_fund_with_computations,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_history(
    start_date: datetime.date,
    values: list[Optional[Decimal]],
    step_days: int = 7,
) -> list[dict[str, Any]]:
    """Build RS history rows starting from start_date, one row per step_days."""
    rows = []
    for i, val in enumerate(values):
        rows.append(
            {
                "date": start_date + datetime.timedelta(days=i * step_days),
                "rs_composite": val,
            }
        )
    return rows


def _make_fund_row(
    mstar_id: str,
    derived_rs_composite: Optional[Decimal] = None,
    manager_alpha: Optional[Decimal] = None,
) -> dict[str, Any]:
    return {
        "mstar_id": mstar_id,
        "derived_rs_composite": derived_rs_composite,
        "manager_alpha": manager_alpha,
        "fund_name": f"Fund {mstar_id}",
    }


# ---------------------------------------------------------------------------
# Fixtures: 10 funds for exact Decimal equality tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def ten_fund_histories() -> list[tuple[str, list[dict[str, Any]], Decimal]]:
    """Ten funds with known RS history and expected rs_momentum_28d values.

    History spans 56 days (8 weekly rows). Latest is row[-1], 28-day-ago row
    is the last row with date <= latest_date - 28 days.

    For 8 weekly rows starting 2026-01-01:
        dates: Jan 1, 8, 15, 22, 29, Feb 5, 12, 19
        latest = Feb 19
        cutoff = Feb 19 - 28 = Jan 22
        past = row at Jan 22 (index 3)
    """
    base = datetime.date(2026, 1, 1)
    # expected momentum = values[-1] - values[3]
    fund_specs = [
        (
            "F001",
            [
                Decimal("1.0"),
                Decimal("1.5"),
                Decimal("2.0"),
                Decimal("2.5"),
                Decimal("3.0"),
                Decimal("3.5"),
                Decimal("4.0"),
                Decimal("4.5"),
            ],
            Decimal("4.5") - Decimal("2.5"),
        ),  # 2.0
        (
            "F002",
            [
                Decimal("-0.5"),
                Decimal("-0.3"),
                Decimal("-0.1"),
                Decimal("0.1"),
                Decimal("0.3"),
                Decimal("0.5"),
                Decimal("0.7"),
                Decimal("0.9"),
            ],
            Decimal("0.9") - Decimal("0.1"),
        ),  # 0.8
        (
            "F003",
            [
                Decimal("5.0"),
                Decimal("4.5"),
                Decimal("4.0"),
                Decimal("3.5"),
                Decimal("3.0"),
                Decimal("2.5"),
                Decimal("2.0"),
                Decimal("1.5"),
            ],
            Decimal("1.5") - Decimal("3.5"),
        ),  # -2.0
        (
            "F004",
            [
                Decimal("-1.0"),
                Decimal("-1.5"),
                Decimal("-2.0"),
                Decimal("-2.5"),
                Decimal("-3.0"),
                Decimal("-3.5"),
                Decimal("-4.0"),
                Decimal("-4.5"),
            ],
            Decimal("-4.5") - Decimal("-2.5"),
        ),  # -2.0
        (
            "F005",
            [
                Decimal("0.0"),
                Decimal("0.1"),
                Decimal("0.2"),
                Decimal("0.3"),
                Decimal("0.4"),
                Decimal("0.5"),
                Decimal("0.6"),
                Decimal("0.7"),
            ],
            Decimal("0.7") - Decimal("0.3"),
        ),  # 0.4
        (
            "F006",
            [
                Decimal("10.0"),
                Decimal("9.0"),
                Decimal("8.0"),
                Decimal("7.0"),
                Decimal("6.0"),
                Decimal("5.0"),
                Decimal("4.0"),
                Decimal("3.0"),
            ],
            Decimal("3.0") - Decimal("7.0"),
        ),  # -4.0
        (
            "F007",
            [
                Decimal("-0.01"),
                Decimal("0.01"),
                Decimal("0.02"),
                Decimal("0.03"),
                Decimal("0.04"),
                Decimal("0.05"),
                Decimal("0.06"),
                Decimal("0.07"),
            ],
            Decimal("0.07") - Decimal("0.03"),
        ),  # 0.04
        (
            "F008",
            [
                Decimal("100.0"),
                Decimal("100.5"),
                Decimal("101.0"),
                Decimal("101.5"),
                Decimal("102.0"),
                Decimal("102.5"),
                Decimal("103.0"),
                Decimal("103.5"),
            ],
            Decimal("103.5") - Decimal("101.5"),
        ),  # 2.0
        (
            "F009",
            [
                Decimal("-50.0"),
                Decimal("-45.0"),
                Decimal("-40.0"),
                Decimal("-35.0"),
                Decimal("-30.0"),
                Decimal("-25.0"),
                Decimal("-20.0"),
                Decimal("-15.0"),
            ],
            Decimal("-15.0") - Decimal("-35.0"),
        ),  # 20.0
        (
            "F010",
            [
                Decimal("0.123"),
                Decimal("0.234"),
                Decimal("0.345"),
                Decimal("0.456"),
                Decimal("0.567"),
                Decimal("0.678"),
                Decimal("0.789"),
                Decimal("0.900"),
            ],
            Decimal("0.900") - Decimal("0.456"),
        ),  # 0.444
    ]
    result = []
    for mstar_id, values, expected in fund_specs:
        history = _make_history(base, values, step_days=7)
        result.append((mstar_id, history, expected))
    return result


# ---------------------------------------------------------------------------
# Tests: compute_rs_momentum_28d
# ---------------------------------------------------------------------------


class TestComputeRsMomentum28d:
    def test_exact_decimal_equality_ten_funds(
        self,
        ten_fund_histories: list[tuple[str, list[dict[str, Any]], Decimal]],
    ) -> None:
        """Exact Decimal equality on 10 fixture funds — no float approximation."""
        for mstar_id, history, expected in ten_fund_histories:
            result = compute_rs_momentum_28d(history)
            assert result is not None, f"Fund {mstar_id}: expected {expected}, got None"
            assert result == expected, f"Fund {mstar_id}: expected {expected!r}, got {result!r}"

    def test_returns_none_when_empty_history(self) -> None:
        """Empty history → None (INSUFFICIENT_DATA)."""
        assert compute_rs_momentum_28d([]) is None

    def test_returns_none_when_single_row(self) -> None:
        """Single row → None: no past data point to compare."""
        history = [{"date": datetime.date(2026, 1, 1), "rs_composite": Decimal("1.0")}]
        assert compute_rs_momentum_28d(history) is None

    def test_returns_none_when_all_within_28_days(self) -> None:
        """<28 days of history → None (INSUFFICIENT_DATA)."""
        base = datetime.date(2026, 1, 1)
        # 4 rows, each 5 days apart = 15 days span (< 28)
        history = _make_history(
            base,
            [Decimal("1.0"), Decimal("2.0"), Decimal("3.0"), Decimal("4.0")],
            step_days=5,
        )
        assert compute_rs_momentum_28d(history) is None

    def test_returns_none_when_latest_rs_composite_is_null(self) -> None:
        """Latest row has NULL rs_composite → None."""
        history = [
            {"date": datetime.date(2026, 1, 1), "rs_composite": Decimal("1.0")},
            {"date": datetime.date(2026, 2, 1), "rs_composite": None},
        ]
        assert compute_rs_momentum_28d(history) is None

    def test_returns_none_when_past_rs_composite_is_null(self) -> None:
        """Past row has NULL rs_composite → None."""
        history = [
            {"date": datetime.date(2026, 1, 1), "rs_composite": None},
            {"date": datetime.date(2026, 2, 1), "rs_composite": Decimal("2.0")},
        ]
        # Only past row is Jan 1 with None; should return None
        assert compute_rs_momentum_28d(history) is None

    def test_uses_most_recent_past_row_before_cutoff(self) -> None:
        """Uses the closest row to the 28-day cutoff (not the oldest)."""
        # Rows: Jan 1, Jan 10, Jan 20 (cutoff for Feb 19 = Jan 22, so Jan 20 is used)
        history = [
            {"date": datetime.date(2026, 1, 1), "rs_composite": Decimal("1.0")},
            {"date": datetime.date(2026, 1, 10), "rs_composite": Decimal("2.0")},
            {"date": datetime.date(2026, 1, 20), "rs_composite": Decimal("3.0")},
            {"date": datetime.date(2026, 2, 19), "rs_composite": Decimal("5.0")},
        ]
        # cutoff = Feb 19 - 28 = Jan 22 → Jan 20 is the closest before cutoff
        result = compute_rs_momentum_28d(history)
        assert result == Decimal("5.0") - Decimal("3.0")  # 2.0

    def test_handles_unsorted_input(self) -> None:
        """Input in random order is sorted correctly by date."""
        history = [
            {"date": datetime.date(2026, 2, 1), "rs_composite": Decimal("4.0")},
            {"date": datetime.date(2026, 1, 1), "rs_composite": Decimal("1.0")},
            {"date": datetime.date(2026, 1, 15), "rs_composite": Decimal("2.5")},
        ]
        # latest = Feb 1, cutoff = Jan 4; past = Jan 1
        result = compute_rs_momentum_28d(history)
        assert result == Decimal("4.0") - Decimal("1.0")

    def test_result_is_decimal_not_float(self) -> None:
        """Result is Decimal type, not float."""
        history = _make_history(
            datetime.date(2026, 1, 1),
            [
                Decimal("1.5"),
                Decimal("2.0"),
                Decimal("2.5"),
                Decimal("3.0"),
                Decimal("3.5"),
                Decimal("4.0"),
                Decimal("4.5"),
                Decimal("5.0"),
            ],
            step_days=7,
        )
        result = compute_rs_momentum_28d(history)
        assert isinstance(result, Decimal), f"Expected Decimal, got {type(result)}"


# ---------------------------------------------------------------------------
# Tests: classify_fund_quadrant
# ---------------------------------------------------------------------------


class TestClassifyFundQuadrant:
    def test_leading_positive_composite_positive_momentum(self) -> None:
        assert classify_fund_quadrant(Decimal("1.0"), Decimal("0.5")) == Quadrant.LEADING

    def test_improving_negative_composite_positive_momentum(self) -> None:
        assert classify_fund_quadrant(Decimal("-1.0"), Decimal("0.5")) == Quadrant.IMPROVING

    def test_weakening_positive_composite_negative_momentum(self) -> None:
        assert classify_fund_quadrant(Decimal("1.0"), Decimal("-0.5")) == Quadrant.WEAKENING

    def test_lagging_negative_composite_negative_momentum(self) -> None:
        assert classify_fund_quadrant(Decimal("-1.0"), Decimal("-0.5")) == Quadrant.LAGGING

    def test_zero_composite_treated_as_negative(self) -> None:
        """Zero boundary: rs_composite=0 → treated as negative (spec §4.2 strict >)."""
        assert classify_fund_quadrant(Decimal("0"), Decimal("1.0")) == Quadrant.IMPROVING

    def test_zero_momentum_treated_as_negative(self) -> None:
        """Zero boundary: rs_momentum=0 → treated as negative (spec §4.2 strict >)."""
        assert classify_fund_quadrant(Decimal("1.0"), Decimal("0")) == Quadrant.WEAKENING

    def test_both_zero_is_lagging(self) -> None:
        """Both zero → LAGGING."""
        assert classify_fund_quadrant(Decimal("0"), Decimal("0")) == Quadrant.LAGGING

    def test_none_composite_returns_none(self) -> None:
        assert classify_fund_quadrant(None, Decimal("1.0")) is None

    def test_none_momentum_returns_none(self) -> None:
        assert classify_fund_quadrant(Decimal("1.0"), None) is None

    def test_both_none_returns_none(self) -> None:
        assert classify_fund_quadrant(None, None) is None

    def test_returns_quadrant_enum(self) -> None:
        """Return value is a Quadrant enum instance, not a raw string."""
        result = classify_fund_quadrant(Decimal("1.0"), Decimal("1.0"))
        assert isinstance(result, Quadrant)


# ---------------------------------------------------------------------------
# Fixture: 50 funds for quadrant matching test
# ---------------------------------------------------------------------------


@pytest.fixture()
def fifty_fund_fixture() -> list[tuple[dict[str, Any], Decimal, Decimal, Quadrant]]:
    """50 funds with known rs_composite, rs_momentum, and expected quadrant.

    Returns list of (fund_row, rs_composite, rs_momentum, expected_quadrant).
    Distribution: 13 LEADING, 12 IMPROVING, 13 WEAKENING, 12 LAGGING.
    """
    cases = []

    # LEADING (composite > 0, momentum > 0): 13 funds
    leading_vals = [
        (Decimal("1.0"), Decimal("0.1")),
        (Decimal("2.5"), Decimal("1.5")),
        (Decimal("0.01"), Decimal("0.01")),
        (Decimal("10.0"), Decimal("5.0")),
        (Decimal("0.5"), Decimal("3.0")),
        (Decimal("3.0"), Decimal("0.5")),
        (Decimal("0.1"), Decimal("0.1")),
        (Decimal("5.0"), Decimal("2.0")),
        (Decimal("0.25"), Decimal("0.75")),
        (Decimal("8.0"), Decimal("1.0")),
        (Decimal("1.1"), Decimal("1.1")),
        (Decimal("0.9"), Decimal("0.9")),
        (Decimal("4.0"), Decimal("0.1")),
    ]
    for rs_c, rs_m in leading_vals:
        cases.append((Decimal(str(rs_c)), Decimal(str(rs_m)), Quadrant.LEADING))

    # IMPROVING (composite < 0, momentum > 0): 12 funds
    improving_vals = [
        (Decimal("-1.0"), Decimal("0.5")),
        (Decimal("-0.5"), Decimal("0.1")),
        (Decimal("-3.0"), Decimal("2.0")),
        (Decimal("-0.1"), Decimal("0.1")),
        (Decimal("-5.0"), Decimal("1.0")),
        (Decimal("-2.0"), Decimal("3.0")),
        (Decimal("-0.01"), Decimal("0.01")),
        (Decimal("-8.0"), Decimal("0.5")),
        (Decimal("-0.9"), Decimal("4.0")),
        (Decimal("-1.5"), Decimal("0.3")),
        (Decimal("-4.0"), Decimal("2.0")),
        (Decimal("-0.3"), Decimal("1.7")),
    ]
    for rs_c, rs_m in improving_vals:
        cases.append((Decimal(str(rs_c)), Decimal(str(rs_m)), Quadrant.IMPROVING))

    # WEAKENING (composite > 0, momentum < 0): 13 funds
    weakening_vals = [
        (Decimal("1.0"), Decimal("-0.5")),
        (Decimal("3.0"), Decimal("-1.0")),
        (Decimal("0.1"), Decimal("-0.1")),
        (Decimal("5.0"), Decimal("-3.0")),
        (Decimal("0.5"), Decimal("-0.5")),
        (Decimal("2.0"), Decimal("-2.0")),
        (Decimal("0.01"), Decimal("-0.01")),
        (Decimal("7.0"), Decimal("-0.5")),
        (Decimal("0.8"), Decimal("-1.2")),
        (Decimal("4.0"), Decimal("-0.1")),
        (Decimal("1.2"), Decimal("-3.0")),
        (Decimal("0.6"), Decimal("-0.4")),
        (Decimal("9.0"), Decimal("-2.0")),
    ]
    for rs_c, rs_m in weakening_vals:
        cases.append((Decimal(str(rs_c)), Decimal(str(rs_m)), Quadrant.WEAKENING))

    # LAGGING (composite < 0, momentum < 0): 12 funds
    lagging_vals = [
        (Decimal("-1.0"), Decimal("-0.5")),
        (Decimal("-3.0"), Decimal("-2.0")),
        (Decimal("-0.1"), Decimal("-0.1")),
        (Decimal("-5.0"), Decimal("-1.0")),
        (Decimal("-0.5"), Decimal("-0.3")),
        (Decimal("-2.0"), Decimal("-0.5")),
        (Decimal("-0.01"), Decimal("-0.01")),
        (Decimal("-8.0"), Decimal("-3.0")),
        (Decimal("-0.9"), Decimal("-0.9")),
        (Decimal("-1.5"), Decimal("-1.5")),
        (Decimal("-4.0"), Decimal("-4.0")),
        (Decimal("-0.3"), Decimal("-0.7")),
    ]
    for rs_c, rs_m in lagging_vals:
        cases.append((Decimal(str(rs_c)), Decimal(str(rs_m)), Quadrant.LAGGING))

    assert len(cases) == 50, f"Expected 50 fixtures, got {len(cases)}"

    result = []
    for i, (rs_c, rs_m, expected_q) in enumerate(cases):
        mstar_id = f"TEST{i:04d}"
        fund_row = _make_fund_row(mstar_id, derived_rs_composite=rs_c)
        result.append((fund_row, rs_c, rs_m, expected_q))
    return result


class TestFiftyFundQuadrants:
    def test_50_funds_match_hand_computed_quadrants(
        self,
        fifty_fund_fixture: list[tuple[dict[str, Any], Decimal, Decimal, Quadrant]],
    ) -> None:
        """50-fund fixture: all quadrants match hand-computed expected values."""
        assert len(fifty_fund_fixture) == 50

        mismatches = []
        for fund_row, rs_composite, rs_momentum, expected_quadrant in fifty_fund_fixture:
            result = classify_fund_quadrant(rs_composite, rs_momentum)
            if result != expected_quadrant:
                mismatches.append(
                    f"{fund_row['mstar_id']}: rs_c={rs_composite}, rs_m={rs_momentum}, "
                    f"expected={expected_quadrant}, got={result}"
                )

        assert not mismatches, "Quadrant mismatches:\n" + "\n".join(mismatches)

    def test_quadrant_distribution_by_sign(self) -> None:
        """Each quadrant defined by sign combination produces correct enum."""
        # Exhaustive coverage of all 4 quadrant sign combinations
        sign_combos = [
            (Decimal("1"), Decimal("1"), Quadrant.LEADING),
            (Decimal("-1"), Decimal("1"), Quadrant.IMPROVING),
            (Decimal("1"), Decimal("-1"), Quadrant.WEAKENING),
            (Decimal("-1"), Decimal("-1"), Quadrant.LAGGING),
        ]
        for rs_c, rs_m, expected in sign_combos:
            assert classify_fund_quadrant(rs_c, rs_m) == expected, (
                f"Sign combo ({rs_c}, {rs_m}) should give {expected}"
            )


# ---------------------------------------------------------------------------
# Tests: enrich_fund_with_computations
# ---------------------------------------------------------------------------


class TestEnrichFundWithComputations:
    def test_enriches_fund_with_momentum_and_quadrant(self) -> None:
        """enrich_fund_with_computations adds rs_momentum_28d and quadrant."""
        fund_row = _make_fund_row(
            "MF001", derived_rs_composite=Decimal("2.0"), manager_alpha=Decimal("0.3")
        )
        history = _make_history(
            datetime.date(2026, 1, 1),
            [
                Decimal("1.0"),
                Decimal("1.5"),
                Decimal("2.0"),
                Decimal("2.5"),
                Decimal("3.0"),
                Decimal("3.5"),
                Decimal("4.0"),
                Decimal("4.5"),
            ],
            step_days=7,
        )
        result = enrich_fund_with_computations(fund_row, history)

        assert result["rs_momentum_28d"] is not None
        assert isinstance(result["rs_momentum_28d"], Decimal)
        assert result["quadrant"] == Quadrant.LEADING  # rs_c>0 from history, rs_m>0
        assert result["manager_alpha"] == Decimal("0.3")

    def test_passthrough_manager_alpha(self) -> None:
        """manager_alpha is passed through from JIP data."""
        alpha = Decimal("1.25")
        fund_row = _make_fund_row("MF002", derived_rs_composite=Decimal("1.0"), manager_alpha=alpha)
        result = enrich_fund_with_computations(fund_row, [])
        assert result["manager_alpha"] == alpha

    def test_none_when_insufficient_history(self) -> None:
        """Fund with no RS history → None momentum and quadrant."""
        fund_row = _make_fund_row("MF003", derived_rs_composite=Decimal("1.0"))
        result = enrich_fund_with_computations(fund_row, [])
        assert result["rs_momentum_28d"] is None
        assert result["quadrant"] is None

    def test_does_not_mutate_original_fund_row(self) -> None:
        """enrich_fund_with_computations returns a new dict, does not mutate input."""
        fund_row = {"mstar_id": "MF004", "derived_rs_composite": Decimal("1.0")}
        original_keys = set(fund_row.keys())
        enrich_fund_with_computations(fund_row, [])
        assert set(fund_row.keys()) == original_keys, "Input dict was mutated"

    def test_handles_rs_composite_key_alias(self) -> None:
        """Handles both 'derived_rs_composite' and 'rs_composite' keys."""
        fund_row_derived = {"mstar_id": "MF005", "derived_rs_composite": Decimal("2.0")}
        fund_row_plain = {"mstar_id": "MF006", "rs_composite": Decimal("2.0")}
        history = _make_history(
            datetime.date(2026, 1, 1),
            [
                Decimal("1.0"),
                Decimal("1.5"),
                Decimal("2.0"),
                Decimal("2.5"),
                Decimal("3.0"),
                Decimal("3.5"),
                Decimal("4.0"),
                Decimal("4.5"),
            ],
            step_days=7,
        )
        r1 = enrich_fund_with_computations(fund_row_derived, history)
        r2 = enrich_fund_with_computations(fund_row_plain, history)
        assert r1["rs_composite"] == Decimal("2.0")
        assert r2["rs_composite"] == Decimal("2.0")


# ---------------------------------------------------------------------------
# Tests: compute_universe_metrics
# ---------------------------------------------------------------------------


class TestComputeUniverseMetrics:
    def test_empty_universe_returns_empty(self) -> None:
        result = compute_universe_metrics([], {})
        assert result == []

    def test_enriches_all_funds_in_batch(self) -> None:
        """All universe funds receive rs_momentum_28d and quadrant fields."""
        history = _make_history(
            datetime.date(2026, 1, 1),
            [
                Decimal("1.0"),
                Decimal("1.5"),
                Decimal("2.0"),
                Decimal("2.5"),
                Decimal("3.0"),
                Decimal("3.5"),
                Decimal("4.0"),
                Decimal("4.5"),
            ],
            step_days=7,
        )
        universe = [
            _make_fund_row("A001", Decimal("2.0")),
            _make_fund_row("A002", Decimal("-1.0")),
            _make_fund_row("A003", Decimal("1.5")),
        ]
        rs_histories = {"A001": history, "A002": history, "A003": history}
        results = compute_universe_metrics(universe, rs_histories)

        assert len(results) == 3
        for r in results:
            assert "rs_momentum_28d" in r
            assert "quadrant" in r

    def test_fund_with_no_history_gets_none(self) -> None:
        """Fund not in rs_histories dict → None momentum and quadrant."""
        universe = [_make_fund_row("B001", Decimal("2.0"))]
        results = compute_universe_metrics(universe, {})
        assert results[0]["rs_momentum_28d"] is None
        assert results[0]["quadrant"] is None

    def test_preserves_row_count(self) -> None:
        """Output count equals input count."""
        universe = [_make_fund_row(f"C{i:03d}", Decimal("1.0")) for i in range(20)]
        results = compute_universe_metrics(universe, {})
        assert len(results) == 20
