"""Drift alert detector for simulation auto-loop re-runs.

Pure computation module — no DB, no async, no I/O.
Compares new KPI summary values against previous values and raises
DriftAlert when deviation exceeds configured thresholds.

Severity levels:
  HIGH     — deviation >5% (default threshold, configurable)
  CRITICAL — deviation >20%
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog

from backend.models.simulation import DriftAlert, DriftThresholds

log = structlog.get_logger()

_CRITICAL_MULTIPLIER = Decimal("4")  # 4x the HIGH threshold = CRITICAL


def detect_drift(
    summary_delta: dict[str, str],
    previous_summary: dict[str, Any],
    thresholds: DriftThresholds | None = None,
) -> list[DriftAlert]:
    """Detect KPI drift between new and previous simulation run.

    Args:
        summary_delta: Dict of KPI name → delta str (Decimal-as-str differences).
                       Keys: xirr, cagr, max_drawdown, final_value, sharpe, etc.
        previous_summary: The previous result_summary dict (raw JSONB from DB).
        thresholds: Configurable thresholds. Defaults to DriftThresholds().

    Returns:
        List of DriftAlert objects for each metric exceeding threshold.
        Empty list if no drift detected.
    """
    if thresholds is None:
        thresholds = DriftThresholds()

    alerts: list[DriftAlert] = []

    # Map metric name → (delta str, threshold, is_absolute comparison)
    # is_absolute=True: compare abs(delta) to threshold directly (e.g. sharpe ratio points)
    # is_absolute=False: compare pct deviation against threshold
    metric_config: dict[str, tuple[Decimal, bool]] = {
        "xirr": (thresholds.xirr_pct, False),
        "cagr": (thresholds.cagr_pct, False),
        "max_drawdown": (thresholds.max_drawdown_pct, False),
        "sharpe": (thresholds.sharpe_abs, True),
    }

    for metric, (threshold, is_absolute) in metric_config.items():
        delta_str = summary_delta.get(metric)
        if delta_str is None:
            continue

        try:
            delta = Decimal(str(delta_str))
        except (ValueError, TypeError, ArithmeticError):
            log.warning("drift_detector_invalid_delta", metric=metric, delta_str=delta_str)
            continue

        prev_raw = previous_summary.get(metric)
        if prev_raw is None:
            continue

        try:
            prev_val = Decimal(str(prev_raw))
        except (ValueError, TypeError, ArithmeticError):
            log.warning("drift_detector_invalid_prev", metric=metric, prev_raw=prev_raw)
            continue

        current_val = prev_val + delta

        if is_absolute:
            # Absolute deviation comparison (e.g. sharpe ratio in units)
            deviation = abs(delta)
            delta_pct = _safe_pct(delta, prev_val)
            exceeded = deviation > threshold
            critical_exceeded = deviation > threshold * _CRITICAL_MULTIPLIER
        else:
            # Percentage deviation comparison
            if prev_val == Decimal("0"):
                # Cannot compute % from zero — check absolute
                if abs(delta) == Decimal("0"):
                    continue
                # Non-zero delta from zero baseline → always HIGH
                deviation = abs(delta)
                delta_pct = Decimal("100")  # Treat as 100% change
                exceeded = True
                critical_exceeded = False
            else:
                delta_pct = (abs(delta) / abs(prev_val)) * Decimal("100")
                exceeded = delta_pct > threshold
                critical_exceeded = delta_pct > threshold * _CRITICAL_MULTIPLIER

        if not exceeded:
            continue

        severity = "CRITICAL" if critical_exceeded else "HIGH"
        alert = DriftAlert(
            metric=metric,
            previous_value=prev_val,
            current_value=current_val,
            delta=delta,
            delta_pct=delta_pct if not is_absolute else _safe_pct(delta, prev_val),
            severity=severity,
        )
        alerts.append(alert)
        log.info(
            "drift_alert_raised",
            metric=metric,
            severity=severity,
            delta=str(delta),
            delta_pct=str(alert.delta_pct),
        )

    return alerts


def _safe_pct(delta: Decimal, prev_val: Decimal) -> Decimal:
    """Compute (delta / prev_val) * 100 safely. Returns 0 if prev_val is zero."""
    if prev_val == Decimal("0"):
        return Decimal("0")
    return (abs(delta) / abs(prev_val)) * Decimal("100")
