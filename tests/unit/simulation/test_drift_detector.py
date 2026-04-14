"""Tests for the drift detector module.

Verifies:
- No alerts when delta is below threshold
- HIGH severity when delta_pct >5%
- CRITICAL severity when delta_pct >20%
- Multiple metrics drifting simultaneously
- Missing metrics handled gracefully (no KeyError)
- All values remain Decimal — no float in production code (AST scan)
"""

from __future__ import annotations

import ast
import os
from decimal import Decimal
from typing import Any

from backend.models.simulation import DriftThresholds
from backend.services.simulation.drift_detector import detect_drift, _safe_pct


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PREV_SUMMARY: dict[str, Any] = {
    "xirr": "0.10",
    "cagr": "0.09",
    "max_drawdown": "-0.15",
    "sharpe": "1.2",
    "final_value": "130000",
}


# ---------------------------------------------------------------------------
# Core drift detection tests
# ---------------------------------------------------------------------------


def test_drift_detector_no_drift_below_threshold() -> None:
    """No alerts when all deltas are within thresholds."""
    # XIRR delta of 0.002 on base 0.10 = 2% — below 5% threshold
    summary_delta = {"xirr": "0.002", "cagr": "0.001"}
    alerts = detect_drift(summary_delta, _PREV_SUMMARY)
    assert alerts == []


def test_drift_detector_high_severity_above_5pct() -> None:
    """HIGH alert when XIRR delta > 5% threshold."""
    # 0.10 baseline, delta 0.008 = 8% change → HIGH
    summary_delta = {"xirr": "0.008"}
    alerts = detect_drift(summary_delta, _PREV_SUMMARY)

    assert len(alerts) == 1
    assert alerts[0].metric == "xirr"
    assert alerts[0].severity == "HIGH"
    assert isinstance(alerts[0].delta, Decimal)
    assert isinstance(alerts[0].delta_pct, Decimal)
    assert isinstance(alerts[0].previous_value, Decimal)
    assert isinstance(alerts[0].current_value, Decimal)


def test_drift_detector_critical_severity_above_20pct() -> None:
    """CRITICAL alert when XIRR delta > 20% threshold (4x the 5% HIGH threshold)."""
    # 0.10 baseline, delta 0.025 = 25% change → CRITICAL
    summary_delta = {"xirr": "0.025"}
    alerts = detect_drift(summary_delta, _PREV_SUMMARY)

    assert len(alerts) == 1
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].delta_pct > Decimal("20")


def test_drift_detector_multiple_metrics_drift() -> None:
    """Multiple metrics can drift simultaneously."""
    # XIRR: 8% drift (HIGH), CAGR: 7% drift (HIGH)
    # xirr base=0.10, delta=0.008 → 8%
    # cagr base=0.09, delta=0.007 → ~7.7%
    summary_delta = {"xirr": "0.008", "cagr": "0.007"}
    alerts = detect_drift(summary_delta, _PREV_SUMMARY)

    assert len(alerts) == 2
    metrics = {a.metric for a in alerts}
    assert "xirr" in metrics
    assert "cagr" in metrics


def test_drift_detector_handles_missing_metrics_gracefully() -> None:
    """Missing metrics in summary_delta or prev_summary are skipped without error."""
    # Only max_drawdown in delta, sharpe is in delta but not in prev_summary key
    summary_delta = {
        "nonexistent_metric": "0.99",
        "xirr": "0.002",  # below threshold — no alert
    }
    # Should not raise KeyError
    alerts = detect_drift(summary_delta, _PREV_SUMMARY)
    assert isinstance(alerts, list)


def test_drift_detector_handles_missing_prev_value_gracefully() -> None:
    """If metric is in delta but not in previous_summary, it's skipped."""
    summary_delta = {"max_drawdown": "0.05"}
    # previous_summary without max_drawdown
    prev_without_drawdown = {k: v for k, v in _PREV_SUMMARY.items() if k != "max_drawdown"}
    alerts = detect_drift(summary_delta, prev_without_drawdown)
    # No alert because prev_val is None
    assert all(a.metric != "max_drawdown" for a in alerts)


def test_drift_detector_sharpe_absolute_threshold() -> None:
    """Sharpe uses absolute deviation, not percentage."""
    thresholds = DriftThresholds(sharpe_abs=Decimal("0.5"))
    prev = {"sharpe": "1.2"}
    # Delta of 0.7 > 0.5 threshold → HIGH
    summary_delta = {"sharpe": "0.7"}
    alerts = detect_drift(summary_delta, prev, thresholds)
    assert len(alerts) == 1
    assert alerts[0].metric == "sharpe"
    assert alerts[0].severity == "HIGH"


def test_drift_detector_sharpe_below_threshold_no_alert() -> None:
    """Sharpe delta below absolute threshold produces no alert."""
    thresholds = DriftThresholds(sharpe_abs=Decimal("0.5"))
    prev = {"sharpe": "1.2"}
    # Delta of 0.3 < 0.5 threshold → no alert
    summary_delta = {"sharpe": "0.3"}
    alerts = detect_drift(summary_delta, prev, thresholds)
    assert alerts == []


def test_drift_detector_custom_thresholds() -> None:
    """Custom thresholds change when alerts are raised."""
    # With 50% threshold, a 10% move should NOT trigger
    thresholds = DriftThresholds(
        xirr_pct=Decimal("50"),
        cagr_pct=Decimal("50"),
        max_drawdown_pct=Decimal("50"),
        sharpe_abs=Decimal("10"),
    )
    summary_delta = {"xirr": "0.008"}  # 8% — below 50% threshold
    alerts = detect_drift(summary_delta, _PREV_SUMMARY, thresholds)
    assert alerts == []


def test_drift_detector_zero_prev_value_no_crash() -> None:
    """If previous value is zero, detect_drift handles gracefully."""
    prev = {"xirr": "0"}
    # Non-zero delta from zero baseline
    summary_delta = {"xirr": "0.05"}
    alerts = detect_drift(summary_delta, prev)
    # Should not crash — alerts may or may not be raised
    assert isinstance(alerts, list)


def test_drift_detector_negative_delta_still_detected() -> None:
    """Negative deltas (decline) are caught as absolute deviation."""
    # xirr went from 0.10 to 0.09 — delta = -0.01 = 10% decline → HIGH
    summary_delta = {"xirr": "-0.01"}
    alerts = detect_drift(summary_delta, _PREV_SUMMARY)
    assert len(alerts) == 1
    assert alerts[0].metric == "xirr"
    assert alerts[0].severity == "HIGH"
    assert alerts[0].delta < Decimal("0")  # negative delta preserved


def test_drift_detector_returns_decimal_types() -> None:
    """All numeric fields on DriftAlert are Decimal, never float."""
    summary_delta = {"xirr": "0.008"}
    alerts = detect_drift(summary_delta, _PREV_SUMMARY)
    assert len(alerts) == 1
    a = alerts[0]
    assert type(a.previous_value) is Decimal
    assert type(a.current_value) is Decimal
    assert type(a.delta) is Decimal
    assert type(a.delta_pct) is Decimal


def test_drift_detector_all_decimal_no_float() -> None:
    """AST scan: drift_detector.py must not contain float() calls in production."""
    module_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "backend",
        "services",
        "simulation",
        "drift_detector.py",
    )
    module_path = os.path.normpath(module_path)
    with open(module_path) as f:
        source = f.read()

    tree = ast.parse(source)
    float_calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "float":
                float_calls.append(f"float() at line {node.lineno}")

    assert float_calls == [], f"float() calls found in drift_detector.py: {float_calls}"


# ---------------------------------------------------------------------------
# _safe_pct helper
# ---------------------------------------------------------------------------


def test_safe_pct_normal() -> None:
    """_safe_pct computes (|delta| / |prev|) * 100."""
    result = _safe_pct(Decimal("0.01"), Decimal("0.10"))
    assert result == Decimal("10")


def test_safe_pct_zero_prev_returns_zero() -> None:
    """_safe_pct returns 0 when prev is zero to avoid division by zero."""
    result = _safe_pct(Decimal("0.05"), Decimal("0"))
    assert result == Decimal("0")


def test_safe_pct_negative_delta() -> None:
    """_safe_pct uses absolute value of delta."""
    result = _safe_pct(Decimal("-0.01"), Decimal("0.10"))
    assert result == Decimal("10")
