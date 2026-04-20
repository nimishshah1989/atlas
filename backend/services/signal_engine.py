"""Signal engine — 5 signal types per slice s2-drill-spine.md §3.3.

Pure computation module. No database calls. All financial values Decimal.
Thresholds loaded from backend/config/signal_thresholds.yaml with mtime-based
hot-reload (falls back to last-known-good on parse error).
"""

from __future__ import annotations

import datetime
import os
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog
import yaml
from pydantic import BaseModel

log = structlog.get_logger(__name__)

_YAML_PATH = Path(__file__).parent.parent / "config" / "signal_thresholds.yaml"

# Module-level hot-reload cache: path, mtime, data
_cache: dict[str, Any] = {"path": str(_YAML_PATH), "mtime": 0.0, "data": None}


# ---------------------------------------------------------------------------
# Enums + Models
# ---------------------------------------------------------------------------


class SignalType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REGIME = "REGIME"
    WARN = "WARN"
    CONFIRM = "CONFIRM"


class Lens(str, Enum):
    rs = "rs"
    momentum = "momentum"
    breadth = "breadth"
    volume = "volume"


class Signal(BaseModel):
    type: SignalType
    lens: Optional[Lens] = None
    fired_at: datetime.date
    value: Optional[Decimal] = None
    threshold: Optional[Decimal] = None
    reason: str


# ---------------------------------------------------------------------------
# Threshold loader (hot-reloadable)
# ---------------------------------------------------------------------------


def load_thresholds() -> dict[str, Any]:
    """Load signal_thresholds.yaml with mtime-based hot-reload.

    Never raises. Falls back to last-known-good data on reload error.
    Returns empty dict only on first-ever load failure.
    """
    path = _cache["path"]
    try:
        current_mtime = os.path.getmtime(path)
    except OSError:
        log.warning("load_thresholds: yaml file not found", path=path)
        return _cache["data"] or {}

    if current_mtime == _cache["mtime"] and _cache["data"] is not None:
        return _cache["data"]  # type: ignore[no-any-return]

    try:
        with open(path, "r") as fh:
            parsed: dict[str, Any] = yaml.safe_load(fh)
        _cache["mtime"] = current_mtime
        _cache["data"] = parsed
        log.debug("load_thresholds: reloaded", path=path)
        return parsed
    except Exception as exc:
        log.warning("load_thresholds: reload error, using last-known-good", error=str(exc))
        return _cache["data"] or {}


def _today() -> datetime.date:
    return datetime.date.today()


def _d(v: Any) -> Decimal:
    """Convert any numeric to Decimal."""
    return Decimal(str(v))


# ---------------------------------------------------------------------------
# evaluate_rs
# ---------------------------------------------------------------------------


def evaluate_rs(
    rs_value: Decimal,
    rs_series: list[Decimal],
    thresholds: dict[str, Any],
) -> list[Signal]:
    """Evaluate RS lens — emit ENTRY/EXIT/WARN signals.

    ENTRY: rs_value crosses above entry threshold sustained_days.
    EXIT: rs_value crosses below exit threshold sustained_days.
    WARN: rs_value within proximity_points of any ENTRY/EXIT band.
    """
    signals: list[Signal] = []
    today = _today()

    entry_cfg = thresholds.get("signals", {}).get("entry", {}).get("rs", {})
    exit_cfg = thresholds.get("signals", {}).get("exit", {}).get("rs", {})

    warn_cfg = thresholds.get("signals", {}).get("warn", {})
    entry_threshold = _d(entry_cfg.get("cross_above", 70))
    entry_days = int(entry_cfg.get("sustained_days", 3))
    exit_threshold = _d(exit_cfg.get("cross_below", 40))
    exit_days = int(exit_cfg.get("sustained_days", 3))
    proximity = _d(warn_cfg.get("proximity_points", 5))

    # Check sustained_days in series (most-recent first or last — treat as chronological)
    tail = rs_series[-entry_days:] if len(rs_series) >= entry_days else rs_series
    # ENTRY: rs_value > entry_threshold AND sustained_days all above threshold
    if (
        rs_value > entry_threshold
        and len(tail) >= entry_days
        and all(v > entry_threshold for v in tail)
    ):
        signals.append(
            Signal(
                type=SignalType.ENTRY,
                lens=Lens.rs,
                fired_at=today,
                value=rs_value,
                threshold=entry_threshold,
                reason=f"RS {rs_value} crossed above {entry_threshold} sustained {entry_days}d",
            )
        )
    # EXIT: rs_value < exit_threshold AND sustained_days all below threshold
    tail_exit = rs_series[-exit_days:] if len(rs_series) >= exit_days else rs_series
    if (
        rs_value < exit_threshold
        and len(tail_exit) >= exit_days
        and all(v < exit_threshold for v in tail_exit)
    ):
        signals.append(
            Signal(
                type=SignalType.EXIT,
                lens=Lens.rs,
                fired_at=today,
                value=rs_value,
                threshold=exit_threshold,
                reason=f"RS {rs_value} crossed below {exit_threshold} sustained {exit_days}d",
            )
        )
    # WARN: within proximity of entry or exit band (but not already ENTRY/EXIT)
    entry_fired = any(s.type == SignalType.ENTRY for s in signals)
    exit_fired = any(s.type == SignalType.EXIT for s in signals)
    if not entry_fired and abs(rs_value - entry_threshold) <= proximity:
        signals.append(
            Signal(
                type=SignalType.WARN,
                lens=Lens.rs,
                fired_at=today,
                value=rs_value,
                threshold=entry_threshold,
                reason=f"RS {rs_value} within {proximity} pts of entry threshold {entry_threshold}",
            )
        )
    if not exit_fired and abs(rs_value - exit_threshold) <= proximity:
        signals.append(
            Signal(
                type=SignalType.WARN,
                lens=Lens.rs,
                fired_at=today,
                value=rs_value,
                threshold=exit_threshold,
                reason=f"RS {rs_value} within {proximity} pts of exit threshold {exit_threshold}",
            )
        )

    return signals


# ---------------------------------------------------------------------------
# evaluate_momentum
# ---------------------------------------------------------------------------


def evaluate_momentum(
    momentum: Decimal,
    slope_5d: Decimal,
    thresholds: dict[str, Any],
) -> list[Signal]:
    """Evaluate momentum lens — ENTRY/EXIT/WARN."""
    signals: list[Signal] = []
    today = _today()

    entry_cfg = thresholds.get("signals", {}).get("entry", {}).get("momentum", {})
    exit_cfg = thresholds.get("signals", {}).get("exit", {}).get("momentum", {})

    warn_cfg = thresholds.get("signals", {}).get("warn", {})
    entry_cross = _d(entry_cfg.get("cross_above", 0))
    entry_slope_min = _d(entry_cfg.get("slope_5d_min", 0))
    exit_cross = _d(exit_cfg.get("cross_below", 0))
    exit_slope_max = _d(exit_cfg.get("slope_5d_max", 0))
    proximity = _d(warn_cfg.get("proximity_points", 5))

    if momentum > entry_cross and slope_5d >= entry_slope_min:
        signals.append(
            Signal(
                type=SignalType.ENTRY,
                lens=Lens.momentum,
                fired_at=today,
                value=momentum,
                threshold=entry_cross,
                reason=(
                    f"Momentum {momentum} > {entry_cross}"
                    f" with slope {slope_5d} >= {entry_slope_min}"
                ),
            )
        )
    if momentum < exit_cross and slope_5d <= exit_slope_max:
        signals.append(
            Signal(
                type=SignalType.EXIT,
                lens=Lens.momentum,
                fired_at=today,
                value=momentum,
                threshold=exit_cross,
                reason=(
                    f"Momentum {momentum} < {exit_cross} with slope {slope_5d} <= {exit_slope_max}"
                ),
            )
        )

    entry_fired = any(s.type == SignalType.ENTRY for s in signals)
    exit_fired = any(s.type == SignalType.EXIT for s in signals)
    if not entry_fired and abs(momentum - entry_cross) <= proximity:
        signals.append(
            Signal(
                type=SignalType.WARN,
                lens=Lens.momentum,
                fired_at=today,
                value=momentum,
                threshold=entry_cross,
                reason=f"Momentum {momentum} near ENTRY ({entry_cross}), within {proximity} pts",
            )
        )
    if not exit_fired and abs(momentum - exit_cross) <= proximity:
        signals.append(
            Signal(
                type=SignalType.WARN,
                lens=Lens.momentum,
                fired_at=today,
                value=momentum,
                threshold=exit_cross,
                reason=f"Momentum {momentum} within {proximity} pts of exit threshold {exit_cross}",
            )
        )

    return signals


# ---------------------------------------------------------------------------
# evaluate_breadth
# ---------------------------------------------------------------------------


def evaluate_breadth(
    st: Decimal,
    mt: Decimal,
    lt: Decimal,
    thresholds: dict[str, Any],
) -> list[Signal]:
    """Evaluate breadth lens — ENTRY/EXIT/WARN.

    ENTRY: ST > 60 AND MT > 50.
    EXIT: ST < 40 OR LT < 40.
    """
    signals: list[Signal] = []
    today = _today()

    entry_cfg = thresholds.get("signals", {}).get("entry", {}).get("breadth", {})
    exit_cfg = thresholds.get("signals", {}).get("exit", {}).get("breadth", {})

    warn_cfg = thresholds.get("signals", {}).get("warn", {})
    entry_st_min = _d(entry_cfg.get("st_min", 60))
    entry_mt_min = _d(entry_cfg.get("mt_min", 50))
    exit_st_max = _d(exit_cfg.get("st_max", 40))
    exit_lt_max = _d(exit_cfg.get("lt_max", 40))
    proximity = _d(warn_cfg.get("proximity_points", 5))

    if st > entry_st_min and mt > entry_mt_min:
        signals.append(
            Signal(
                type=SignalType.ENTRY,
                lens=Lens.breadth,
                fired_at=today,
                value=st,
                threshold=entry_st_min,
                reason=f"Breadth ST {st} > {entry_st_min} AND MT {mt} > {entry_mt_min}",
            )
        )
    if st < exit_st_max or lt < exit_lt_max:
        signals.append(
            Signal(
                type=SignalType.EXIT,
                lens=Lens.breadth,
                fired_at=today,
                value=st,
                threshold=exit_st_max,
                reason=f"Breadth ST {st} < {exit_st_max} OR LT {lt} < {exit_lt_max}",
            )
        )

    entry_fired = any(s.type == SignalType.ENTRY for s in signals)
    exit_fired = any(s.type == SignalType.EXIT for s in signals)
    if not entry_fired and (
        abs(st - entry_st_min) <= proximity or abs(mt - entry_mt_min) <= proximity
    ):
        signals.append(
            Signal(
                type=SignalType.WARN,
                lens=Lens.breadth,
                fired_at=today,
                value=st,
                threshold=entry_st_min,
                reason=f"Breadth ST/MT near entry ({entry_st_min}/{entry_mt_min})",
            )
        )
    if not exit_fired and (
        abs(st - exit_st_max) <= proximity or abs(lt - exit_lt_max) <= proximity
    ):
        signals.append(
            Signal(
                type=SignalType.WARN,
                lens=Lens.breadth,
                fired_at=today,
                value=st,
                threshold=exit_st_max,
                reason=f"Breadth ST/LT approaching exit thresholds ({exit_st_max}/{exit_lt_max})",
            )
        )

    return signals


# ---------------------------------------------------------------------------
# evaluate_volume
# ---------------------------------------------------------------------------


def evaluate_volume(
    rel_vol: Decimal,
    thresholds: dict[str, Any],
) -> list[Signal]:
    """Evaluate volume lens — confirm high-participation days."""
    signals: list[Signal] = []
    today = _today()

    entry_cfg = thresholds.get("signals", {}).get("entry", {}).get("volume", {})

    rel_vol_min = _d(entry_cfg.get("rel_vol_min", 1.5))

    if rel_vol >= rel_vol_min:
        signals.append(
            Signal(
                type=SignalType.ENTRY,
                lens=Lens.volume,
                fired_at=today,
                value=rel_vol,
                threshold=rel_vol_min,
                reason=f"Relative volume {rel_vol} >= {rel_vol_min} (high participation)",
            )
        )
    # WARN: within proximity fraction (proximity/100 of threshold for volume, e.g. 0.1x)
    elif abs(rel_vol - rel_vol_min) <= _d("0.2"):
        signals.append(
            Signal(
                type=SignalType.WARN,
                lens=Lens.volume,
                fired_at=today,
                value=rel_vol,
                threshold=rel_vol_min,
                reason=f"Relative volume {rel_vol} approaching threshold {rel_vol_min}",
            )
        )

    return signals


# ---------------------------------------------------------------------------
# evaluate_confirm
# ---------------------------------------------------------------------------


def evaluate_confirm(
    signals_by_lens: dict[Lens, list[Signal]],
    thresholds: dict[str, Any],
) -> list[Signal]:
    """Emit CONFIRM when >= min_lenses ENTRY in same direction within N days.

    Checks the signals_by_lens dict: counts distinct lenses with at least one
    ENTRY signal. If count >= min_lenses, fires CONFIRM.
    """
    confirm_cfg = thresholds.get("signals", {}).get("confirm", {})
    min_lenses = int(confirm_cfg.get("min_lenses", 3))
    today = _today()

    entry_lenses = [
        lens
        for lens, sigs in signals_by_lens.items()
        if any(s.type == SignalType.ENTRY for s in sigs)
    ]

    if len(entry_lenses) >= min_lenses:
        return [
            Signal(
                type=SignalType.CONFIRM,
                lens=None,
                fired_at=today,
                value=_d(len(entry_lenses)),
                threshold=_d(min_lenses),
                reason=(
                    f"CONFIRM: {len(entry_lenses)} lenses aligned ENTRY"
                    f" ({', '.join(lns.value for lns in entry_lenses)})"
                ),
            )
        ]
    return []


# ---------------------------------------------------------------------------
# evaluate_regime
# ---------------------------------------------------------------------------


def evaluate_regime(
    composite_breadth: Decimal,
    drawdown_pct: Decimal,
    thresholds: dict[str, Any],
) -> Signal:
    """Return REGIME signal based on composite breadth + drawdown pct.

    Tiers: BULL / CAUTIOUS / CORRECTION / BEAR.
    drawdown_pct is positive (e.g. 8.0 means 8% below peak).
    """
    today = _today()
    regime_cfg = thresholds.get("signals", {}).get("regime", {})

    bull_cfg = regime_cfg.get("bull", {})
    cautious_cfg = regime_cfg.get("cautious", {})
    correction_cfg = regime_cfg.get("correction", {})

    bull_breadth_min = _d(bull_cfg.get("breadth_min", 65))
    bull_dd_max = _d(bull_cfg.get("drawdown_max_pct", 5))
    cautious_breadth_min = _d(cautious_cfg.get("breadth_min", 45))
    cautious_dd_max = _d(cautious_cfg.get("drawdown_max_pct", 10))
    correction_breadth_min = _d(correction_cfg.get("breadth_min", 25))
    correction_dd_max = _d(correction_cfg.get("drawdown_max_pct", 20))

    if composite_breadth >= bull_breadth_min and drawdown_pct <= bull_dd_max:
        tier = "BULL"
    elif composite_breadth >= cautious_breadth_min and drawdown_pct <= cautious_dd_max:
        tier = "CAUTIOUS"
    elif composite_breadth >= correction_breadth_min and drawdown_pct <= correction_dd_max:
        tier = "CORRECTION"
    else:
        tier = "BEAR"

    return Signal(
        type=SignalType.REGIME,
        lens=None,
        fired_at=today,
        value=composite_breadth,
        threshold=bull_breadth_min,
        reason=f"Regime={tier}: breadth={composite_breadth}, drawdown={drawdown_pct}%",
    )
