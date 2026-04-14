"""Signal adapters for the V3 Simulation Engine — pure computation module.

No DB, no I/O, no async. Each adapter transforms raw time-series data
into a SignalSeries of BUY/SELL/HOLD/REENTRY states for the backtest engine.

Signal sources per spec §8:
  1. BREADTH (pct_above_200dma) — range 0–100
  2. McCLELLAN (mcclellan_oscillator) — range -200 to +200
  3. RS (rs_composite) — instrument-level relative strength
  4. PE (pe_ratio) — P/E ratio of any index
  5. REGIME (regime string → numeric: BULL=100, RECOVERY=75, SIDEWAYS=50, BEAR=0)
  6. SECTOR_RS (rs_composite for sectors)
  7. McCLELLAN_SUMMATION (mcclellan_summation) — longer-term breadth
  8. COMBINED (AND/OR of any two SignalSeries)

All thresholds and values use Decimal — never float.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Iterator, Optional

from backend.models.simulation import CombineLogic, SignalType


class SignalState(str, Enum):
    """Possible states emitted by a signal adapter."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    REENTRY = "REENTRY"


@dataclass(frozen=True)
class SignalPoint:
    """Single resolved signal observation with raw_value for provenance."""

    date: date
    state: SignalState
    raw_value: Decimal


@dataclass
class SignalSeries:
    """Ordered time series of SignalPoints produced by an adapter."""

    points: list[SignalPoint] = field(default_factory=list)
    signal_type: SignalType = SignalType.BREADTH
    metadata: dict[str, object] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.points)

    def __iter__(self) -> Iterator[SignalPoint]:
        return iter(self.points)


# ---------------------------------------------------------------------------
# REGIME string → numeric mapping
# ---------------------------------------------------------------------------

_REGIME_MAP: dict[str, Decimal] = {
    "BULL": Decimal("100"),
    "RECOVERY": Decimal("75"),
    "SIDEWAYS": Decimal("50"),
    "BEAR": Decimal("0"),
}


def _regime_to_numeric(regime_str: str) -> Decimal:
    """Convert REGIME string to numeric Decimal. Raises ValueError if unknown."""
    key = regime_str.strip().upper()
    if key not in _REGIME_MAP:
        raise ValueError(
            f"Unknown regime value '{regime_str}'. Expected one of: {list(_REGIME_MAP.keys())}"
        )
    return _REGIME_MAP[key]


# ---------------------------------------------------------------------------
# Core threshold logic — shared by all 7 adapters
# ---------------------------------------------------------------------------


def _apply_threshold_logic(
    values: list[tuple[date, Decimal]],
    buy_level: Decimal,
    sell_level: Decimal,
    reentry_level: Optional[Decimal],
) -> list[SignalPoint]:
    """Convert (date, Decimal) pairs into SignalPoints via state machine.

    value <= buy_level → BUY; value >= sell_level → SELL;
    reentry_level set AND prev==SELL AND value <= reentry_level → REENTRY;
    else → HOLD.
    """
    points: list[SignalPoint] = []
    prev_state: SignalState = SignalState.HOLD

    for obs_date, value in values:
        if value <= buy_level:
            state = SignalState.BUY
        elif value >= sell_level:
            state = SignalState.SELL
        elif (
            reentry_level is not None and prev_state == SignalState.SELL and value <= reentry_level
        ):
            state = SignalState.REENTRY
        else:
            state = SignalState.HOLD

        points.append(SignalPoint(date=obs_date, state=state, raw_value=value))
        prev_state = state

    return points


def _extract_field(
    data: list[dict[str, Any]],
    field_name: str,
    signal_type: SignalType,
    buy_level: Decimal,
    sell_level: Decimal,
    reentry_level: Optional[Decimal],
) -> SignalSeries:
    """Extract field_name from each dict, convert via Decimal(str(v)), apply thresholds.

    Skips rows where the field value is None.
    """
    pairs: list[tuple[date, Decimal]] = []
    for row in data:
        raw = row.get(field_name)
        if raw is None:
            continue
        pairs.append((row["date"], Decimal(str(raw))))

    points = _apply_threshold_logic(pairs, buy_level, sell_level, reentry_level)

    return SignalSeries(
        points=points,
        signal_type=signal_type,
        metadata={
            "field": field_name,
            "buy_level": buy_level,
            "sell_level": sell_level,
            "reentry_level": reentry_level,
        },
    )


# ---------------------------------------------------------------------------
# Public adapter functions — one per signal source
# ---------------------------------------------------------------------------


def adapt_breadth(
    data: list[dict[str, Any]],
    buy_level: Decimal,
    sell_level: Decimal,
    reentry_level: Optional[Decimal] = None,
) -> SignalSeries:
    """BREADTH signal (pct_above_200dma). Range 0–100."""
    return _extract_field(
        data, "pct_above_200dma", SignalType.BREADTH, buy_level, sell_level, reentry_level
    )


def adapt_mcclellan(
    data: list[dict[str, Any]],
    buy_level: Decimal,
    sell_level: Decimal,
    reentry_level: Optional[Decimal] = None,
) -> SignalSeries:
    """McCLELLAN signal (mcclellan_oscillator). Range -200 to +200."""
    return _extract_field(
        data, "mcclellan_oscillator", SignalType.MCCLELLAN, buy_level, sell_level, reentry_level
    )


def adapt_rs(
    data: list[dict[str, Any]],
    buy_level: Decimal,
    sell_level: Decimal,
    reentry_level: Optional[Decimal] = None,
) -> SignalSeries:
    """RS signal (rs_composite) for a specific instrument."""
    return _extract_field(data, "rs_composite", SignalType.RS, buy_level, sell_level, reentry_level)


def adapt_pe(
    data: list[dict[str, Any]],
    buy_level: Decimal,
    sell_level: Decimal,
    reentry_level: Optional[Decimal] = None,
) -> SignalSeries:
    """PE signal (pe_ratio) — mean-reversion on any index."""
    return _extract_field(data, "pe_ratio", SignalType.PE, buy_level, sell_level, reentry_level)


def adapt_regime(
    data: list[dict[str, Any]],
    buy_level: Decimal,
    sell_level: Decimal,
    reentry_level: Optional[Decimal] = None,
) -> SignalSeries:
    """REGIME signal (regime string → numeric). BULL=100, RECOVERY=75, SIDEWAYS=50, BEAR=0."""
    pairs: list[tuple[date, Decimal]] = []
    for row in data:
        raw = row.get("regime")
        if raw is None:
            continue
        numeric = _regime_to_numeric(str(raw))
        pairs.append((row["date"], numeric))

    points = _apply_threshold_logic(pairs, buy_level, sell_level, reentry_level)

    return SignalSeries(
        points=points,
        signal_type=SignalType.REGIME,
        metadata={
            "field": "regime",
            "buy_level": buy_level,
            "sell_level": sell_level,
            "reentry_level": reentry_level,
            "mapping": {k: str(v) for k, v in _REGIME_MAP.items()},
        },
    )


def adapt_sector_rs(
    data: list[dict[str, Any]],
    buy_level: Decimal,
    sell_level: Decimal,
    reentry_level: Optional[Decimal] = None,
) -> SignalSeries:
    """SECTOR_RS signal (rs_composite for sectors) — sector rotation timing."""
    return _extract_field(
        data, "rs_composite", SignalType.SECTOR_RS, buy_level, sell_level, reentry_level
    )


def adapt_mcclellan_summation(
    data: list[dict[str, Any]],
    buy_level: Decimal,
    sell_level: Decimal,
    reentry_level: Optional[Decimal] = None,
) -> SignalSeries:
    """McCLELLAN_SUMMATION signal (mcclellan_summation) — longer-term breadth momentum."""
    return _extract_field(
        data,
        "mcclellan_summation",
        SignalType.MCCLELLAN_SUMMATION,
        buy_level,
        sell_level,
        reentry_level,
    )


# ---------------------------------------------------------------------------
# Combined signal adapter
# ---------------------------------------------------------------------------


def combine_signals(
    series_a: SignalSeries,
    series_b: SignalSeries,
    logic: CombineLogic,
) -> SignalSeries:
    """Combine two SignalSeries using AND or OR logic.

    AND: BUY if both BUY/REENTRY, SELL if either SELL, else HOLD.
    OR:  BUY if either BUY/REENTRY, SELL if both SELL, else HOLD.
    Only dates present in BOTH series are included.
    """
    map_a: dict[date, SignalPoint] = {p.date: p for p in series_a.points}
    map_b: dict[date, SignalPoint] = {p.date: p for p in series_b.points}
    common_dates = sorted(map_a.keys() & map_b.keys())

    _buy_states = {SignalState.BUY, SignalState.REENTRY}

    points: list[SignalPoint] = []
    for obs_date in common_dates:
        pt_a = map_a[obs_date]
        pt_b = map_b[obs_date]
        state_a = pt_a.state
        state_b = pt_b.state

        if logic == CombineLogic.AND:
            if state_a in _buy_states and state_b in _buy_states:
                combined_state = SignalState.BUY
            elif state_a == SignalState.SELL or state_b == SignalState.SELL:
                combined_state = SignalState.SELL
            else:
                combined_state = SignalState.HOLD
        else:  # OR
            if state_a in _buy_states or state_b in _buy_states:
                combined_state = SignalState.BUY
            elif state_a == SignalState.SELL and state_b == SignalState.SELL:
                combined_state = SignalState.SELL
            else:
                combined_state = SignalState.HOLD

        combined_raw = (pt_a.raw_value + pt_b.raw_value) / Decimal("2")
        points.append(SignalPoint(date=obs_date, state=combined_state, raw_value=combined_raw))

    return SignalSeries(
        points=points,
        signal_type=SignalType.COMBINED,
        metadata={
            "signal_a": series_a.signal_type.value,
            "signal_b": series_b.signal_type.value,
            "logic": logic.value,
        },
    )


# ---------------------------------------------------------------------------
# Adapter registry / dispatcher
# ---------------------------------------------------------------------------

_ADAPTER_REGISTRY: dict[SignalType, Callable[..., SignalSeries]] = {
    SignalType.BREADTH: adapt_breadth,
    SignalType.MCCLELLAN: adapt_mcclellan,
    SignalType.RS: adapt_rs,
    SignalType.PE: adapt_pe,
    SignalType.REGIME: adapt_regime,
    SignalType.SECTOR_RS: adapt_sector_rs,
    SignalType.MCCLELLAN_SUMMATION: adapt_mcclellan_summation,
}


def get_adapter(signal_type: SignalType) -> Callable[..., SignalSeries]:
    """Return the adapter callable for the given SignalType.

    COMBINED is not dispatchable — use combine_signals() directly.
    """
    if signal_type == SignalType.COMBINED:
        raise ValueError(
            "COMBINED signal is not dispatchable via get_adapter(). "
            "Use combine_signals(series_a, series_b, logic) directly."
        )
    adapter = _ADAPTER_REGISTRY.get(signal_type)
    if adapter is None:
        raise ValueError(f"No adapter registered for signal type: {signal_type!r}")
    return adapter


__all__ = [
    "SignalState",
    "SignalPoint",
    "SignalSeries",
    "adapt_breadth",
    "adapt_mcclellan",
    "adapt_rs",
    "adapt_pe",
    "adapt_regime",
    "adapt_sector_rs",
    "adapt_mcclellan_summation",
    "combine_signals",
    "get_adapter",
    "_regime_to_numeric",
    "_apply_threshold_logic",
]
