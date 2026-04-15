"""Accuracy scoring functions for Darwinian evolution — spec §7.

Dispatches to outcome-type-specific scorers. Each scorer compares a
prediction against an actual outcome and returns a Decimal in [0, 1].

All values are Decimal, never float. Pure functions — zero I/O.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")


def compute_accuracy_for_outcome(
    prediction: str,
    actual_outcome: str | None,
    outcome_type: str,
) -> Decimal | None:
    """Compute accuracy score (0.0-1.0) given a prediction and its actual outcome.

    Returns None when actual_outcome is None (data not yet available).
    All returned values are Decimal, never float.
    """
    if actual_outcome is None:
        return None

    try:
        actual_data = json.loads(actual_outcome)
    except (json.JSONDecodeError, TypeError):
        actual_data = actual_outcome

    try:
        pred_data = json.loads(prediction)
    except (json.JSONDecodeError, TypeError):
        pred_data = prediction

    if outcome_type == "sector_return":
        return _score_sector_return(pred_data, actual_data)
    if outcome_type == "alignment_accuracy":
        return _score_alignment(pred_data, actual_data)
    if outcome_type == "regime_transition":
        return _score_regime_transition(pred_data, actual_data)
    if outcome_type == "opportunity_conversion":
        return _score_opportunity_conversion(pred_data, actual_data)

    log.warning(
        "darwinian_scorer.unknown_outcome_type",
        outcome_type=outcome_type,
    )
    return None


def _score_sector_return(prediction: Any, actual: Any) -> Decimal:
    """Score a sector return prediction.

    Prediction direction (up/down) matched against actual sign.
    Correct direction = 1.0, wrong = 0.0.
    """
    if isinstance(prediction, dict):
        direction = str(prediction.get("direction", "")).lower()
    else:
        direction = str(prediction).lower()

    if isinstance(actual, dict):
        raw_return = actual.get("return", actual.get("value", 0))
    else:
        raw_return = actual

    try:
        actual_dec = Decimal(str(raw_return))
    except (ValueError, TypeError, ArithmeticError):
        actual_dec = _ZERO

    if direction in ("up", "positive", "bullish"):
        return _ONE if actual_dec > _ZERO else _ZERO
    if direction in ("down", "negative", "bearish"):
        return _ONE if actual_dec < _ZERO else _ZERO
    return Decimal("0.5")


def _score_alignment(prediction: Any, actual: Any) -> Decimal:
    """Score a Goldilocks alignment prediction.

    Exact match = 1.0, partial (neutral involved) = 0.5, wrong = 0.0.
    """
    if isinstance(prediction, dict):
        pred_label = str(prediction.get("alignment", prediction.get("signal", ""))).lower()
    else:
        pred_label = str(prediction).lower()

    if isinstance(actual, dict):
        act_label = str(actual.get("alignment", actual.get("signal", ""))).lower()
    else:
        act_label = str(actual).lower()

    if pred_label == act_label:
        return _ONE
    if "neutral" in (pred_label, act_label):
        return Decimal("0.5")
    return _ZERO


def _score_regime_transition(prediction: Any, actual: Any) -> Decimal:
    """Score a regime transition prediction (20-day forward).

    1.0 if predicted regime matches actual regime, 0.0 otherwise.
    """
    if isinstance(prediction, dict):
        pred_regime = str(prediction.get("regime", "")).lower()
    else:
        pred_regime = str(prediction).lower()

    if isinstance(actual, dict):
        act_regime = str(actual.get("regime", "")).lower()
    else:
        act_regime = str(actual).lower()

    return _ONE if pred_regime and pred_regime == act_regime else _ZERO


def _score_opportunity_conversion(prediction: Any, actual: Any) -> Decimal:
    """Score an opportunity conversion prediction.

    1.0 if predicted opportunity converted (actual confirms), 0.0 otherwise.
    """
    if isinstance(prediction, dict):
        pred_converted = str(prediction.get("converted", "false")).lower() in ("true", "1", "yes")
    else:
        pred_converted = str(prediction).lower() in ("true", "1", "yes", "converted")

    if isinstance(actual, dict):
        act_converted = str(actual.get("converted", "false")).lower() in ("true", "1", "yes")
    else:
        act_converted = str(actual).lower() in ("true", "1", "yes", "converted")

    return _ONE if pred_converted == act_converted else _ZERO
