"""Tests for backend/services/simulation/signal_adapters.py.

All financial comparisons use exact Decimal equality (never pytest.approx).
Spec §8: 7 signal adapters + combined AND/OR logic.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.models.simulation import CombineLogic, SignalType
import ast

from backend.services.simulation.signal_adapters import (
    SignalPoint,
    SignalSeries,
    SignalState,
    _regime_to_numeric,
    adapt_breadth,
    adapt_mcclellan,
    adapt_mcclellan_summation,
    adapt_pe,
    adapt_regime,
    adapt_rs,
    adapt_sector_rs,
    combine_signals,
    get_adapter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _date(day: int) -> date:
    """Shorthand: date(2020, 1, day)."""
    return date(2020, 1, day)


def _d(value: str) -> Decimal:
    return Decimal(value)


def _has_float_annotation(source_path: str) -> bool:
    with open(source_path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            if isinstance(node.annotation, ast.Name) and node.annotation.id == "float":
                return True
        if isinstance(node, ast.FunctionDef) and node.returns is not None:
            if isinstance(node.returns, ast.Name) and node.returns.id == "float":
                return True
        if isinstance(node, ast.AnnAssign) and node.annotation is not None:
            if isinstance(node.annotation, ast.Name) and node.annotation.id == "float":
                return True
    return False


def _has_print_call(source_path: str) -> bool:
    with open(source_path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                return True
    return False


def _make_data(field: str, rows: list[tuple[date, str | None]]) -> list[dict]:
    """Build a minimal data list with 'date' and one signal field."""
    return [{"date": d, field: v} for d, v in rows]


# ---------------------------------------------------------------------------
# 1. BREADTH adapter — basic BUY / SELL / HOLD states
# ---------------------------------------------------------------------------


class TestAdaptBreadth:
    def test_buy_at_buy_level(self) -> None:
        data = _make_data("pct_above_200dma", [(_date(1), "50")])
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        assert len(series) == 1
        assert series.points[0].state == SignalState.BUY

    def test_below_buy_level_is_buy(self) -> None:
        data = _make_data("pct_above_200dma", [(_date(1), "30")])
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        assert series.points[0].state == SignalState.BUY

    def test_sell_at_sell_level(self) -> None:
        data = _make_data("pct_above_200dma", [(_date(1), "75")])
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        assert series.points[0].state == SignalState.SELL

    def test_above_sell_level_is_sell(self) -> None:
        data = _make_data("pct_above_200dma", [(_date(1), "80")])
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        assert series.points[0].state == SignalState.SELL

    def test_between_levels_is_hold(self) -> None:
        data = _make_data("pct_above_200dma", [(_date(1), "60")])
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        assert series.points[0].state == SignalState.HOLD

    def test_raw_value_is_decimal(self) -> None:
        data = _make_data("pct_above_200dma", [(_date(1), "45")])
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        assert isinstance(series.points[0].raw_value, Decimal)
        assert series.points[0].raw_value == _d("45")

    def test_signal_type_tagged(self) -> None:
        data = _make_data("pct_above_200dma", [(_date(1), "60")])
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        assert series.signal_type == SignalType.BREADTH

    def test_empty_data_returns_empty_series(self) -> None:
        series = adapt_breadth([], buy_level=_d("50"), sell_level=_d("75"))
        assert len(series) == 0
        assert series.signal_type == SignalType.BREADTH

    def test_none_value_skipped(self) -> None:
        data = [{"date": _date(1), "pct_above_200dma": None}]
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        assert len(series) == 0

    def test_multiple_points_ordered(self) -> None:
        data = _make_data(
            "pct_above_200dma",
            [(_date(1), "40"), (_date(2), "80"), (_date(3), "60")],
        )
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        states = [p.state for p in series.points]
        assert states == [SignalState.BUY, SignalState.SELL, SignalState.HOLD]


# ---------------------------------------------------------------------------
# 2. McCLELLAN adapter
# ---------------------------------------------------------------------------


class TestAdaptMcclellan:
    def test_buy_below_minus_100(self) -> None:
        data = _make_data("mcclellan_oscillator", [(_date(1), "-150")])
        series = adapt_mcclellan(data, buy_level=_d("-100"), sell_level=_d("100"))
        assert series.points[0].state == SignalState.BUY

    def test_sell_above_100(self) -> None:
        data = _make_data("mcclellan_oscillator", [(_date(1), "120")])
        series = adapt_mcclellan(data, buy_level=_d("-100"), sell_level=_d("100"))
        assert series.points[0].state == SignalState.SELL

    def test_hold_between_levels(self) -> None:
        data = _make_data("mcclellan_oscillator", [(_date(1), "0")])
        series = adapt_mcclellan(data, buy_level=_d("-100"), sell_level=_d("100"))
        assert series.points[0].state == SignalState.HOLD

    def test_signal_type_tagged(self) -> None:
        data = _make_data("mcclellan_oscillator", [(_date(1), "0")])
        series = adapt_mcclellan(data, buy_level=_d("-100"), sell_level=_d("100"))
        assert series.signal_type == SignalType.MCCLELLAN

    def test_empty_returns_empty(self) -> None:
        series = adapt_mcclellan([], buy_level=_d("-100"), sell_level=_d("100"))
        assert len(series) == 0


# ---------------------------------------------------------------------------
# 3. RS adapter
# ---------------------------------------------------------------------------


class TestAdaptRS:
    def test_buy_below_minus_5(self) -> None:
        data = _make_data("rs_composite", [(_date(1), "-10")])
        series = adapt_rs(data, buy_level=_d("-5"), sell_level=_d("15"))
        assert series.points[0].state == SignalState.BUY

    def test_sell_above_15(self) -> None:
        data = _make_data("rs_composite", [(_date(1), "20")])
        series = adapt_rs(data, buy_level=_d("-5"), sell_level=_d("15"))
        assert series.points[0].state == SignalState.SELL

    def test_signal_type_tagged(self) -> None:
        data = _make_data("rs_composite", [(_date(1), "0")])
        series = adapt_rs(data, buy_level=_d("-5"), sell_level=_d("15"))
        assert series.signal_type == SignalType.RS

    def test_empty_returns_empty(self) -> None:
        series = adapt_rs([], buy_level=_d("-5"), sell_level=_d("15"))
        assert len(series) == 0


# ---------------------------------------------------------------------------
# 4. PE adapter
# ---------------------------------------------------------------------------


class TestAdaptPE:
    def test_buy_below_18(self) -> None:
        data = _make_data("pe_ratio", [(_date(1), "15")])
        series = adapt_pe(data, buy_level=_d("18"), sell_level=_d("24"))
        assert series.points[0].state == SignalState.BUY

    def test_sell_above_24(self) -> None:
        data = _make_data("pe_ratio", [(_date(1), "28")])
        series = adapt_pe(data, buy_level=_d("18"), sell_level=_d("24"))
        assert series.points[0].state == SignalState.SELL

    def test_signal_type_tagged(self) -> None:
        data = _make_data("pe_ratio", [(_date(1), "20")])
        series = adapt_pe(data, buy_level=_d("18"), sell_level=_d("24"))
        assert series.signal_type == SignalType.PE

    def test_empty_returns_empty(self) -> None:
        series = adapt_pe([], buy_level=_d("18"), sell_level=_d("24"))
        assert len(series) == 0


# ---------------------------------------------------------------------------
# 5. REGIME adapter — string → numeric mapping
# ---------------------------------------------------------------------------


class TestAdaptRegime:
    def test_bear_maps_to_0_triggers_buy(self) -> None:
        data = [{"date": _date(1), "regime": "BEAR"}]
        series = adapt_regime(data, buy_level=_d("40"), sell_level=_d("80"))
        assert series.points[0].state == SignalState.BUY
        assert series.points[0].raw_value == _d("0")

    def test_bull_maps_to_100_triggers_sell(self) -> None:
        data = [{"date": _date(1), "regime": "BULL"}]
        series = adapt_regime(data, buy_level=_d("40"), sell_level=_d("80"))
        assert series.points[0].state == SignalState.SELL
        assert series.points[0].raw_value == _d("100")

    def test_recovery_maps_to_75(self) -> None:
        data = [{"date": _date(1), "regime": "RECOVERY"}]
        series = adapt_regime(data, buy_level=_d("40"), sell_level=_d("80"))
        assert series.points[0].raw_value == _d("75")
        assert series.points[0].state == SignalState.HOLD

    def test_sideways_maps_to_50(self) -> None:
        data = [{"date": _date(1), "regime": "SIDEWAYS"}]
        series = adapt_regime(data, buy_level=_d("40"), sell_level=_d("80"))
        assert series.points[0].raw_value == _d("50")
        assert series.points[0].state == SignalState.HOLD

    def test_unknown_regime_raises(self) -> None:
        data = [{"date": _date(1), "regime": "UNKNOWN"}]
        with pytest.raises(ValueError, match="Unknown regime value"):
            adapt_regime(data, buy_level=_d("40"), sell_level=_d("80"))

    def test_none_regime_skipped(self) -> None:
        data = [{"date": _date(1), "regime": None}]
        series = adapt_regime(data, buy_level=_d("40"), sell_level=_d("80"))
        assert len(series) == 0

    def test_signal_type_tagged(self) -> None:
        data = [{"date": _date(1), "regime": "SIDEWAYS"}]
        series = adapt_regime(data, buy_level=_d("40"), sell_level=_d("80"))
        assert series.signal_type == SignalType.REGIME

    def test_empty_returns_empty(self) -> None:
        series = adapt_regime([], buy_level=_d("40"), sell_level=_d("80"))
        assert len(series) == 0


# ---------------------------------------------------------------------------
# 6. SECTOR_RS adapter
# ---------------------------------------------------------------------------


class TestAdaptSectorRS:
    def test_buy_underperforming_sector(self) -> None:
        data = _make_data("rs_composite", [(_date(1), "-8")])
        series = adapt_sector_rs(data, buy_level=_d("-5"), sell_level=_d("15"))
        assert series.points[0].state == SignalState.BUY

    def test_signal_type_tagged(self) -> None:
        data = _make_data("rs_composite", [(_date(1), "0")])
        series = adapt_sector_rs(data, buy_level=_d("-5"), sell_level=_d("15"))
        assert series.signal_type == SignalType.SECTOR_RS

    def test_empty_returns_empty(self) -> None:
        series = adapt_sector_rs([], buy_level=_d("-5"), sell_level=_d("15"))
        assert len(series) == 0


# ---------------------------------------------------------------------------
# 7. McCLELLAN_SUMMATION adapter
# ---------------------------------------------------------------------------


class TestAdaptMcclellanSummation:
    def test_buy_below_threshold(self) -> None:
        data = _make_data("mcclellan_summation", [(_date(1), "-600")])
        series = adapt_mcclellan_summation(data, buy_level=_d("-500"), sell_level=_d("500"))
        assert series.points[0].state == SignalState.BUY

    def test_sell_above_threshold(self) -> None:
        data = _make_data("mcclellan_summation", [(_date(1), "700")])
        series = adapt_mcclellan_summation(data, buy_level=_d("-500"), sell_level=_d("500"))
        assert series.points[0].state == SignalState.SELL

    def test_signal_type_tagged(self) -> None:
        data = _make_data("mcclellan_summation", [(_date(1), "0")])
        series = adapt_mcclellan_summation(data, buy_level=_d("-500"), sell_level=_d("500"))
        assert series.signal_type == SignalType.MCCLELLAN_SUMMATION

    def test_empty_returns_empty(self) -> None:
        series = adapt_mcclellan_summation([], buy_level=_d("-500"), sell_level=_d("500"))
        assert len(series) == 0


# ---------------------------------------------------------------------------
# 8. Reentry logic
# ---------------------------------------------------------------------------


class TestReentryLogic:
    """After a SELL, crossing back below reentry_level triggers REENTRY."""

    def test_reentry_after_sell(self) -> None:
        """Sequence: BUY → SELL → REENTRY when value crosses reentry_level."""
        # buy_level=50, sell_level=75, reentry_level=65
        # Day1: value=40 → BUY
        # Day2: value=80 → SELL
        # Day3: value=65 → REENTRY (prev=SELL, value <= reentry_level)
        data = _make_data(
            "pct_above_200dma",
            [(_date(1), "40"), (_date(2), "80"), (_date(3), "65")],
        )
        series = adapt_breadth(
            data, buy_level=_d("50"), sell_level=_d("75"), reentry_level=_d("65")
        )
        states = [p.state for p in series.points]
        assert states == [SignalState.BUY, SignalState.SELL, SignalState.REENTRY]

    def test_no_reentry_without_prior_sell(self) -> None:
        """Reentry does not fire if previous state was not SELL."""
        # Day1: value=60 → HOLD (not SELL), Day2: value=65 → HOLD (prev was HOLD)
        data = _make_data(
            "pct_above_200dma",
            [(_date(1), "60"), (_date(2), "65")],
        )
        series = adapt_breadth(
            data, buy_level=_d("50"), sell_level=_d("75"), reentry_level=_d("65")
        )
        assert series.points[1].state == SignalState.HOLD

    def test_reentry_not_emitted_when_reentry_level_is_none(self) -> None:
        """Without reentry_level, the state should be HOLD, not REENTRY."""
        data = _make_data(
            "pct_above_200dma",
            [(_date(1), "40"), (_date(2), "80"), (_date(3), "65")],
        )
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        assert series.points[2].state == SignalState.HOLD

    def test_above_reentry_level_after_sell_is_hold(self) -> None:
        """After SELL, value above reentry_level but below sell_level → HOLD."""
        # Day1: BUY, Day2: SELL, Day3: value=70 > reentry_level=65 → HOLD
        data = _make_data(
            "pct_above_200dma",
            [(_date(1), "40"), (_date(2), "80"), (_date(3), "70")],
        )
        series = adapt_breadth(
            data, buy_level=_d("50"), sell_level=_d("75"), reentry_level=_d("65")
        )
        assert series.points[2].state == SignalState.HOLD


# ---------------------------------------------------------------------------
# 9. Combined signal — AND logic
# ---------------------------------------------------------------------------


class TestCombineSignalsAND:
    def _make_series(
        self,
        sig_type: SignalType,
        states: list[SignalState],
    ) -> SignalSeries:
        """Build a minimal SignalSeries from a list of states."""
        points = [
            SignalPoint(date=_date(i + 1), state=s, raw_value=_d("50"))
            for i, s in enumerate(states)
        ]
        return SignalSeries(points=points, signal_type=sig_type)

    def test_both_buy_gives_buy(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.BUY])
        b = self._make_series(SignalType.PE, [SignalState.BUY])
        result = combine_signals(a, b, CombineLogic.AND)
        assert result.points[0].state == SignalState.BUY

    def test_one_sell_gives_sell(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.BUY])
        b = self._make_series(SignalType.PE, [SignalState.SELL])
        result = combine_signals(a, b, CombineLogic.AND)
        assert result.points[0].state == SignalState.SELL

    def test_both_sell_gives_sell(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.SELL])
        b = self._make_series(SignalType.PE, [SignalState.SELL])
        result = combine_signals(a, b, CombineLogic.AND)
        assert result.points[0].state == SignalState.SELL

    def test_buy_and_hold_gives_hold(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.BUY])
        b = self._make_series(SignalType.PE, [SignalState.HOLD])
        result = combine_signals(a, b, CombineLogic.AND)
        assert result.points[0].state == SignalState.HOLD

    def test_reentry_both_gives_buy(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.REENTRY])
        b = self._make_series(SignalType.PE, [SignalState.REENTRY])
        result = combine_signals(a, b, CombineLogic.AND)
        assert result.points[0].state == SignalState.BUY

    def test_reentry_and_sell_gives_sell(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.REENTRY])
        b = self._make_series(SignalType.PE, [SignalState.SELL])
        result = combine_signals(a, b, CombineLogic.AND)
        assert result.points[0].state == SignalState.SELL

    def test_empty_series_gives_empty(self) -> None:
        a = SignalSeries(points=[], signal_type=SignalType.BREADTH)
        b = SignalSeries(points=[], signal_type=SignalType.PE)
        result = combine_signals(a, b, CombineLogic.AND)
        assert len(result) == 0
        assert result.signal_type == SignalType.COMBINED

    def test_metadata_records_both_signals_and_logic(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.BUY])
        b = self._make_series(SignalType.PE, [SignalState.BUY])
        result = combine_signals(a, b, CombineLogic.AND)
        assert result.metadata["signal_a"] == "breadth"
        assert result.metadata["signal_b"] == "pe"
        assert result.metadata["logic"] == "AND"


# ---------------------------------------------------------------------------
# 10. Combined signal — OR logic
# ---------------------------------------------------------------------------


class TestCombineSignalsOR:
    def _make_series(
        self,
        sig_type: SignalType,
        states: list[SignalState],
    ) -> SignalSeries:
        points = [
            SignalPoint(date=_date(i + 1), state=s, raw_value=_d("50"))
            for i, s in enumerate(states)
        ]
        return SignalSeries(points=points, signal_type=sig_type)

    def test_one_buy_gives_buy(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.BUY])
        b = self._make_series(SignalType.PE, [SignalState.HOLD])
        result = combine_signals(a, b, CombineLogic.OR)
        assert result.points[0].state == SignalState.BUY

    def test_both_sell_gives_sell(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.SELL])
        b = self._make_series(SignalType.PE, [SignalState.SELL])
        result = combine_signals(a, b, CombineLogic.OR)
        assert result.points[0].state == SignalState.SELL

    def test_one_sell_one_hold_gives_hold(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.SELL])
        b = self._make_series(SignalType.PE, [SignalState.HOLD])
        result = combine_signals(a, b, CombineLogic.OR)
        assert result.points[0].state == SignalState.HOLD

    def test_reentry_one_gives_buy(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.REENTRY])
        b = self._make_series(SignalType.PE, [SignalState.HOLD])
        result = combine_signals(a, b, CombineLogic.OR)
        assert result.points[0].state == SignalState.BUY

    def test_both_hold_gives_hold(self) -> None:
        a = self._make_series(SignalType.BREADTH, [SignalState.HOLD])
        b = self._make_series(SignalType.PE, [SignalState.HOLD])
        result = combine_signals(a, b, CombineLogic.OR)
        assert result.points[0].state == SignalState.HOLD


# ---------------------------------------------------------------------------
# 11. Regime string mapping unit tests
# ---------------------------------------------------------------------------


class TestRegimeToNumeric:
    def test_bull_is_100(self) -> None:
        assert _regime_to_numeric("BULL") == _d("100")

    def test_recovery_is_75(self) -> None:
        assert _regime_to_numeric("RECOVERY") == _d("75")

    def test_sideways_is_50(self) -> None:
        assert _regime_to_numeric("SIDEWAYS") == _d("50")

    def test_bear_is_0(self) -> None:
        assert _regime_to_numeric("BEAR") == _d("0")

    def test_lowercase_accepted(self) -> None:
        assert _regime_to_numeric("bull") == _d("100")

    def test_mixed_case_accepted(self) -> None:
        assert _regime_to_numeric("Bull") == _d("100")

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown regime value"):
            _regime_to_numeric("CRASH")


# ---------------------------------------------------------------------------
# 12. get_adapter dispatcher
# ---------------------------------------------------------------------------


class TestGetAdapter:
    @pytest.mark.parametrize(
        "signal_type,expected_fn_name",
        [
            (SignalType.BREADTH, "adapt_breadth"),
            (SignalType.MCCLELLAN, "adapt_mcclellan"),
            (SignalType.RS, "adapt_rs"),
            (SignalType.PE, "adapt_pe"),
            (SignalType.REGIME, "adapt_regime"),
            (SignalType.SECTOR_RS, "adapt_sector_rs"),
            (SignalType.MCCLELLAN_SUMMATION, "adapt_mcclellan_summation"),
        ],
    )
    def test_dispatches_correctly(self, signal_type: SignalType, expected_fn_name: str) -> None:
        adapter = get_adapter(signal_type)
        assert adapter.__name__ == expected_fn_name

    def test_combined_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="COMBINED signal is not dispatchable"):
            get_adapter(SignalType.COMBINED)


# ---------------------------------------------------------------------------
# 13. Decimal / no-float invariants (AST scan)
# ---------------------------------------------------------------------------


class TestNoFloat:
    def _source_path(self) -> str:
        import backend.services.simulation.signal_adapters as mod

        return mod.__file__  # type: ignore[return-value]

    def test_no_float_annotations_in_source(self) -> None:
        path = self._source_path()
        assert not _has_float_annotation(path), (
            f"Float annotation found in {path}. Use Decimal everywhere."
        )

    def test_no_print_statements_in_source(self) -> None:
        path = self._source_path()
        assert not _has_print_call(path), (
            f"print() call found in {path}. Use structlog in production."
        )


# ---------------------------------------------------------------------------
# 14. SignalPoint carries Decimal raw_value (provenance check)
# ---------------------------------------------------------------------------


class TestSignalPointDecimal:
    def test_raw_value_is_decimal_not_float(self) -> None:
        data = _make_data("rs_composite", [(_date(1), "12.34")])
        series = adapt_rs(data, buy_level=_d("-5"), sell_level=_d("15"))
        pt = series.points[0]
        assert isinstance(pt.raw_value, Decimal)
        assert pt.raw_value == Decimal("12.34")

    def test_raw_value_preserved_from_string_conversion(self) -> None:
        """Verifies Decimal(str(v)) path — no float intermediary."""
        # Integer from data dict
        data = [{"date": _date(1), "pe_ratio": 20}]
        series = adapt_pe(data, buy_level=_d("18"), sell_level=_d("24"))
        assert series.points[0].raw_value == Decimal("20")

    def test_float_input_converted_to_decimal_via_str(self) -> None:
        """Even if caller passes a float, we convert via str() to avoid imprecision."""
        data = [{"date": _date(1), "pct_above_200dma": 45.0}]
        series = adapt_breadth(data, buy_level=_d("50"), sell_level=_d("75"))
        pt = series.points[0]
        assert isinstance(pt.raw_value, Decimal)


# ---------------------------------------------------------------------------
# 15. Combined date alignment — non-overlapping dates dropped
# ---------------------------------------------------------------------------


class TestCombineDateAlignment:
    def test_non_overlapping_dates_excluded(self) -> None:
        a_points = [
            SignalPoint(date=_date(1), state=SignalState.BUY, raw_value=_d("40")),
            SignalPoint(date=_date(2), state=SignalState.SELL, raw_value=_d("80")),
        ]
        b_points = [
            SignalPoint(date=_date(2), state=SignalState.BUY, raw_value=_d("15")),
            SignalPoint(date=_date(3), state=SignalState.BUY, raw_value=_d("10")),
        ]
        a = SignalSeries(points=a_points, signal_type=SignalType.BREADTH)
        b = SignalSeries(points=b_points, signal_type=SignalType.PE)
        result = combine_signals(a, b, CombineLogic.AND)
        # Only date 2 is in both; date 1 (A only) and date 3 (B only) are dropped
        assert len(result) == 1
        assert result.points[0].date == _date(2)
