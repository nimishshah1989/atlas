"""Tests for signal_engine.py — 5 signal types."""

from __future__ import annotations

import datetime
from decimal import Decimal

from backend.services.signal_engine import (
    Lens,
    Signal,
    SignalType,
    evaluate_breadth,
    evaluate_confirm,
    evaluate_momentum,
    evaluate_regime,
    evaluate_rs,
    evaluate_volume,
    load_thresholds,
)

_D = Decimal


def _thresholds() -> dict:
    """Load real thresholds from yaml (covers load_thresholds test too)."""
    return load_thresholds()


# ---------------------------------------------------------------------------
# load_thresholds
# ---------------------------------------------------------------------------


def test_load_thresholds_returns_dict():
    t = load_thresholds()
    assert isinstance(t, dict)
    assert "signals" in t


# ---------------------------------------------------------------------------
# evaluate_rs
# ---------------------------------------------------------------------------


def test_evaluate_rs_entry_fires_when_sustained_3d_above_70():
    t = _thresholds()
    series = [_D("72"), _D("73"), _D("75")]
    sigs = evaluate_rs(_D("75"), series, t)
    entry_sigs = [s for s in sigs if s.type == SignalType.ENTRY]
    assert entry_sigs, "Expected ENTRY signal for RS above 70 for 3 days"


def test_evaluate_rs_entry_not_fired_if_series_too_short():
    t = _thresholds()
    series = [_D("72"), _D("73")]  # only 2 days
    sigs = evaluate_rs(_D("75"), series, t)
    entry_sigs = [s for s in sigs if s.type == SignalType.ENTRY]
    assert not entry_sigs, "Should NOT fire ENTRY with only 2 days of data"


def test_evaluate_rs_exit_fires_when_sustained_3d_below_40():
    t = _thresholds()
    series = [_D("38"), _D("37"), _D("35")]
    sigs = evaluate_rs(_D("35"), series, t)
    exit_sigs = [s for s in sigs if s.type == SignalType.EXIT]
    assert exit_sigs, "Expected EXIT signal for RS below 40 for 3 days"


def test_evaluate_rs_warn_fires_within_proximity_of_entry():
    t = _thresholds()
    # RS at 67 is within 5 points of entry threshold 70
    series = [_D("67")]
    sigs = evaluate_rs(_D("67"), series, t)
    warn_sigs = [s for s in sigs if s.type == SignalType.WARN and s.threshold == _D("70")]
    assert warn_sigs, "Expected WARN near entry threshold 70"


def test_evaluate_rs_warn_fires_within_proximity_of_exit():
    t = _thresholds()
    # RS at 43 is within 5 points of exit threshold 40
    series = [_D("43")]
    sigs = evaluate_rs(_D("43"), series, t)
    warn_sigs = [s for s in sigs if s.type == SignalType.WARN and s.threshold == _D("40")]
    assert warn_sigs, "Expected WARN near exit threshold 40"


# ---------------------------------------------------------------------------
# evaluate_momentum
# ---------------------------------------------------------------------------


def test_evaluate_momentum_entry_fires_positive_momentum_positive_slope():
    t = _thresholds()
    sigs = evaluate_momentum(_D("5"), _D("1"), t)
    entry_sigs = [s for s in sigs if s.type == SignalType.ENTRY]
    assert entry_sigs, "Expected ENTRY for momentum > 0 and slope > 0"


def test_evaluate_momentum_exit_fires_negative_momentum_negative_slope():
    t = _thresholds()
    sigs = evaluate_momentum(_D("-3"), _D("-1"), t)
    exit_sigs = [s for s in sigs if s.type == SignalType.EXIT]
    assert exit_sigs, "Expected EXIT for momentum < 0 and slope < 0"


def test_evaluate_momentum_no_entry_for_negative_momentum():
    t = _thresholds()
    sigs = evaluate_momentum(_D("-1"), _D("0"), t)
    entry_sigs = [s for s in sigs if s.type == SignalType.ENTRY]
    assert not entry_sigs


# ---------------------------------------------------------------------------
# evaluate_breadth
# ---------------------------------------------------------------------------


def test_evaluate_breadth_entry_fires_st_above_60_mt_above_50():
    t = _thresholds()
    sigs = evaluate_breadth(_D("65"), _D("55"), _D("50"), t)
    entry_sigs = [s for s in sigs if s.type == SignalType.ENTRY]
    assert entry_sigs, "Expected ENTRY for ST > 60 AND MT > 50"


def test_evaluate_breadth_exit_fires_when_st_below_40():
    t = _thresholds()
    sigs = evaluate_breadth(_D("35"), _D("55"), _D("50"), t)
    exit_sigs = [s for s in sigs if s.type == SignalType.EXIT]
    assert exit_sigs, "Expected EXIT when ST < 40"


def test_evaluate_breadth_exit_fires_when_lt_below_40():
    t = _thresholds()
    sigs = evaluate_breadth(_D("55"), _D("55"), _D("35"), t)
    exit_sigs = [s for s in sigs if s.type == SignalType.EXIT]
    assert exit_sigs, "Expected EXIT when LT < 40"


# ---------------------------------------------------------------------------
# evaluate_volume
# ---------------------------------------------------------------------------


def test_evaluate_volume_entry_fires_when_rel_vol_above_1_5():
    t = _thresholds()
    sigs = evaluate_volume(_D("2.0"), t)
    entry_sigs = [s for s in sigs if s.type == SignalType.ENTRY]
    assert entry_sigs, "Expected ENTRY for rel_vol >= 1.5"


def test_evaluate_volume_no_entry_for_low_rel_vol():
    t = _thresholds()
    sigs = evaluate_volume(_D("1.0"), t)
    entry_sigs = [s for s in sigs if s.type == SignalType.ENTRY]
    assert not entry_sigs


# ---------------------------------------------------------------------------
# evaluate_confirm
# ---------------------------------------------------------------------------


def _make_entry_sigs(lens: Lens) -> list[Signal]:
    return [
        Signal(
            type=SignalType.ENTRY,
            lens=lens,
            fired_at=datetime.date.today(),
            value=_D("75"),
            threshold=_D("70"),
            reason="test entry",
        )
    ]


def test_evaluate_confirm_fires_when_3_or_more_lenses_entry():
    t = _thresholds()
    signals_map = {
        Lens.rs: _make_entry_sigs(Lens.rs),
        Lens.momentum: _make_entry_sigs(Lens.momentum),
        Lens.breadth: _make_entry_sigs(Lens.breadth),
        Lens.volume: [],
    }
    confirms = evaluate_confirm(signals_map, t)
    assert confirms, "Expected CONFIRM when 3 lenses ENTRY"
    assert confirms[0].type == SignalType.CONFIRM


def test_evaluate_confirm_does_not_fire_for_2_lenses():
    t = _thresholds()
    signals_map = {
        Lens.rs: _make_entry_sigs(Lens.rs),
        Lens.momentum: _make_entry_sigs(Lens.momentum),
        Lens.breadth: [],
        Lens.volume: [],
    }
    confirms = evaluate_confirm(signals_map, t)
    assert not confirms, "Should NOT confirm with only 2 lenses"


# ---------------------------------------------------------------------------
# evaluate_regime
# ---------------------------------------------------------------------------


def test_evaluate_regime_returns_bull():
    t = _thresholds()
    sig = evaluate_regime(_D("70"), _D("3"), t)
    assert "BULL" in sig.reason


def test_evaluate_regime_returns_cautious():
    t = _thresholds()
    sig = evaluate_regime(_D("50"), _D("8"), t)
    assert "CAUTIOUS" in sig.reason


def test_evaluate_regime_returns_correction():
    t = _thresholds()
    sig = evaluate_regime(_D("30"), _D("15"), t)
    assert "CORRECTION" in sig.reason


def test_evaluate_regime_returns_bear():
    t = _thresholds()
    sig = evaluate_regime(_D("20"), _D("25"), t)
    assert "BEAR" in sig.reason


def test_evaluate_regime_returns_signal_type_regime():
    t = _thresholds()
    sig = evaluate_regime(_D("70"), _D("3"), t)
    assert sig.type == SignalType.REGIME
