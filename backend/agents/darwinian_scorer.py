"""Darwinian Nightly Accuracy Scoring Service — spec §7.

Scores agent predictions against actual outcomes, updates rolling accuracy,
adjusts Darwinian weights, and detects specialist spawn triggers.

This module is a pure computation service — zero LLM calls. Every numeric
value is Decimal, never float. Idempotent: re-running on the same
data_as_of produces the same result.

Holiday detection:
  - Saturday or Sunday → always no-op
  - Weekday where JIP has no fresh data → treat as market holiday, no-op
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.darwinian_accuracy import compute_accuracy_for_outcome
from backend.db.models import AtlasAgentMemory, AtlasAgentScore, AtlasAgentWeight

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCORED_AGENTS: dict[str, dict[str, Any]] = {
    "rs-analyzer": {"window_days": 5, "outcome_type": "sector_return"},
    "sector-analyst": {"window_days": 5, "outcome_type": "sector_return"},
    "goldilocks-analyst": {"window_days": 5, "outcome_type": "alignment_accuracy"},
    "regime-analyst": {"window_days": 20, "outcome_type": "regime_transition"},
    "discovery-engine": {"window_days": 5, "outcome_type": "opportunity_conversion"},
}

NON_SCORED_AGENTS: set[str] = {
    "briefing-writer",
    "simulation-runner",
    "portfolio-analyzer",
    "tv-bridge",
}

# Rolling window for accuracy computation
ROLLING_WINDOW = 60

# Error threshold for specialist spawn
SPAWN_ERROR_THRESHOLD = 3
SPAWN_LOOKBACK_DAYS = 5

# Accuracy threshold — below this is an "error"
ERROR_ACCURACY_THRESHOLD = Decimal("0.5")

# Weight adjustment factors (spec §7 Darwinian Weights)
WEIGHT_TOP_QUARTILE_FACTOR = Decimal("1.05")
WEIGHT_BOTTOM_QUARTILE_FACTOR = Decimal("0.95")
WEIGHT_CAP = Decimal("2.5")
WEIGHT_FLOOR = Decimal("0.3")

_ZERO = Decimal("0")
_ONE = Decimal("1")


# ---------------------------------------------------------------------------
# Holiday / trading day detection
# ---------------------------------------------------------------------------


def is_trading_day(check_date: date) -> bool:
    """Return True if check_date is likely a trading day.

    Simple heuristic: weekdays only. Exchange-specific holidays are
    checked separately via has_fresh_jip_data().
    """
    # Monday=0 … Friday=4, Saturday=5, Sunday=6
    return check_date.weekday() < 5


# ---------------------------------------------------------------------------
# Window-elapsed classification
# ---------------------------------------------------------------------------


class WindowState:
    NOT_YET = "not_yet"
    JUST_ELAPSED = "just_elapsed"
    LONG_ELAPSED = "long_elapsed"


def classify_window(
    prediction_date: date,
    window_days: int,
    data_as_of: date,
) -> str:
    """Classify where we are in the prediction evaluation window.

    Args:
        prediction_date: Date the prediction was made.
        window_days: Number of trading days in the evaluation window.
        data_as_of: The reference date (today or scoring date).

    Returns:
        One of WindowState.NOT_YET, WindowState.JUST_ELAPSED, WindowState.LONG_ELAPSED.
    """
    eval_date = prediction_date + timedelta(days=window_days)
    if eval_date > data_as_of:
        return WindowState.NOT_YET
    if eval_date == data_as_of:
        return WindowState.JUST_ELAPSED
    return WindowState.LONG_ELAPSED


# ---------------------------------------------------------------------------
# Rolling accuracy
# ---------------------------------------------------------------------------


def compute_rolling_accuracy(scores: list[Decimal]) -> Decimal | None:
    """Compute mean accuracy over the rolling window (up to ROLLING_WINDOW predictions).

    Returns None if the scores list is empty.
    All arithmetic in Decimal.
    """
    if not scores:
        return None
    window = scores[-ROLLING_WINDOW:]
    total = sum(window, _ZERO)
    return total / Decimal(str(len(window)))


# ---------------------------------------------------------------------------
# Darwinian weight adjustment
# ---------------------------------------------------------------------------


def compute_new_weight(
    current_weight: Decimal,
    rolling_accuracy: Decimal | None,
    all_accuracies: list[Decimal],
) -> Decimal:
    """Adjust weight based on quartile position.

    Top quartile (>= 75th percentile) → × 1.05, capped at 2.5.
    Bottom quartile (<= 25th percentile) → × 0.95, floored at 0.3.
    Middle → unchanged.
    """
    if rolling_accuracy is None or not all_accuracies:
        return current_weight

    sorted_acc = sorted(all_accuracies)
    n = len(sorted_acc)
    p25 = sorted_acc[max(0, n // 4 - 1)]
    p75 = sorted_acc[min(n - 1, (3 * n) // 4)]

    # Even distribution tie-break: when all accuracies are equal (or nearly so),
    # no quartile-based adjustment — return weight unchanged.
    if p25 == p75:
        return current_weight

    if rolling_accuracy >= p75:
        new_weight = current_weight * WEIGHT_TOP_QUARTILE_FACTOR
    elif rolling_accuracy <= p25:
        new_weight = current_weight * WEIGHT_BOTTOM_QUARTILE_FACTOR
    else:
        return current_weight

    # Clamp to [WEIGHT_FLOOR, WEIGHT_CAP]
    new_weight = max(WEIGHT_FLOOR, min(WEIGHT_CAP, new_weight))
    return new_weight


# ---------------------------------------------------------------------------
# Specialist spawn detection
# ---------------------------------------------------------------------------


def detect_spawn_triggers(
    recent_errors: list[dict[str, Any]],
    lookback_days: int = SPAWN_LOOKBACK_DAYS,
    threshold: int = SPAWN_ERROR_THRESHOLD,
    reference_date: date | None = None,
) -> list[dict[str, Any]]:
    """Detect entities with repeated prediction errors.

    Args:
        recent_errors: List of dicts with keys: entity, prediction_date, agent_id.
            Each represents a scored prediction with accuracy_score < threshold.
        lookback_days: Number of calendar days to look back.
        threshold: Minimum number of errors per entity to trigger spawn.
        reference_date: Reference date for lookback window (defaults to today).

    Returns:
        List of spawn trigger dicts, one per entity exceeding the threshold.
    """
    if reference_date is None:
        from datetime import datetime, timezone

        reference_date = datetime.now(tz=timezone.utc).date()

    cutoff = reference_date - timedelta(days=lookback_days)

    # Group errors by entity
    entity_errors: dict[str, list[dict[str, Any]]] = {}
    for err in recent_errors:
        pred_date = err.get("prediction_date")
        if pred_date is None:
            continue
        if isinstance(pred_date, str):
            from datetime import datetime

            pred_date = datetime.strptime(pred_date, "%Y-%m-%d").date()
        if pred_date < cutoff:
            continue
        entity = err.get("entity") or "unknown"
        entity_errors.setdefault(entity, []).append(err)

    triggers = []
    for entity, errors in entity_errors.items():
        if len(errors) >= threshold:
            agent_ids = list({e.get("agent_id", "unknown") for e in errors})
            triggers.append(
                {
                    "entity": entity,
                    "error_count": len(errors),
                    "agent_ids": agent_ids,
                    "trigger_date": reference_date.isoformat(),
                }
            )

    return triggers


# ---------------------------------------------------------------------------
# Main scoring service
# ---------------------------------------------------------------------------


def _skipped_result(reason: str, data_as_of: date) -> dict[str, Any]:
    """Build a skip-result dict for weekend/holiday no-ops."""
    return {
        "status": "skipped",
        "reason": reason,
        "data_as_of": str(data_as_of),
        "scored_count": 0,
        "skipped_count": 0,
        "spawn_triggers": [],
    }


async def _load_unscored(db: AsyncSession) -> list[AtlasAgentScore]:
    """Load unscored predictions for scored agents only."""
    stmt = select(AtlasAgentScore).where(
        AtlasAgentScore.accuracy_score.is_(None),
        AtlasAgentScore.is_deleted.is_(False),
        AtlasAgentScore.agent_id.in_(list(SCORED_AGENTS.keys())),
    )
    query_result = await db.execute(stmt)
    return list(query_result.scalars().all())


def _score_single_prediction(
    row: AtlasAgentScore,
    data_as_of: date,
) -> tuple[str, Decimal | None]:
    """Score one prediction row. Returns (window_state, accuracy_or_none)."""
    agent_cfg = SCORED_AGENTS.get(row.agent_id)
    if agent_cfg is None:
        return WindowState.NOT_YET, None

    state = classify_window(row.prediction_date, agent_cfg["window_days"], data_as_of)
    if state == WindowState.NOT_YET:
        return state, None

    accuracy = compute_accuracy_for_outcome(
        row.prediction, row.actual_outcome, agent_cfg["outcome_type"]
    )
    return state, accuracy


async def _update_agent_weights(
    db: AsyncSession,
    agent_rolling: dict[str, Decimal | None],
    data_as_of: date,
) -> None:
    """Update rolling accuracy and Darwinian weights for each scored agent."""
    logger = log.bind(data_as_of=str(data_as_of))
    for agent_id, rolling_acc in agent_rolling.items():
        if rolling_acc is None:
            continue
        weight_stmt = select(AtlasAgentWeight).where(AtlasAgentWeight.agent_id == agent_id)
        weight_result = await db.execute(weight_stmt)
        weight_row: AtlasAgentWeight | None = weight_result.scalar_one_or_none()
        if weight_row is None:
            continue
        weight_row.rolling_accuracy = rolling_acc
        all_accuracies = [v for v in agent_rolling.values() if v is not None]
        new_weight = compute_new_weight(weight_row.weight, rolling_acc, all_accuracies)
        if new_weight != weight_row.weight:
            logger.info(
                "darwinian_scorer.weight_adjusted",
                agent_id=agent_id,
                old_weight=str(weight_row.weight),
                new_weight=str(new_weight),
            )
            weight_row.weight = new_weight
            weight_row.mutation_count = (weight_row.mutation_count or 0) + 1
            weight_row.last_mutation_date = data_as_of


async def _persist_spawn_triggers(
    db: AsyncSession,
    spawn_triggers: list[dict[str, Any]],
) -> None:
    """Write spawn trigger records to atlas_agent_memory."""
    for trigger in spawn_triggers:
        memory_content = json.dumps(
            {
                "trigger": "specialist_spawn",
                "entity": trigger["entity"],
                "error_count": trigger["error_count"],
                "agent_ids": trigger["agent_ids"],
                "trigger_date": trigger["trigger_date"],
                "lookback_days": SPAWN_LOOKBACK_DAYS,
            }
        )
        db.add(
            AtlasAgentMemory(
                agent_id="darwinian-scorer",
                memory_type="spawn_trigger",
                content=memory_content,
            )
        )
        log.info(
            "darwinian_scorer.spawn_trigger",
            entity=trigger["entity"],
            error_count=trigger["error_count"],
        )


async def _fetch_rolling_scores(
    db: AsyncSession,
) -> dict[str, Decimal | None]:
    """Fetch rolling accuracy for each scored agent from recent scores."""
    agent_rolling: dict[str, Decimal | None] = {}
    for agent_id in SCORED_AGENTS:
        rolling_stmt = (
            select(AtlasAgentScore.accuracy_score)
            .where(
                AtlasAgentScore.agent_id == agent_id,
                AtlasAgentScore.accuracy_score.is_not(None),
                AtlasAgentScore.is_deleted.is_(False),
            )
            .order_by(AtlasAgentScore.id.desc())
            .limit(ROLLING_WINDOW)
        )
        rolling_result = await db.execute(rolling_stmt)
        scores = [Decimal(str(s)) for s in rolling_result.scalars().all() if s is not None]
        agent_rolling[agent_id] = compute_rolling_accuracy(scores)
    return agent_rolling


async def run_scoring(
    db: AsyncSession,
    data_as_of: date,
    jip_has_data_fn: Any = None,
) -> dict[str, Any]:
    """Execute the nightly accuracy scoring run.

    Args:
        db: SQLAlchemy AsyncSession.
        data_as_of: The date to score against (typically today's trading date).
        jip_has_data_fn: Optional async callable(date) → bool for holiday detection.

    Returns:
        Summary dict with scored_count, skipped_count, spawn_triggers.
    """
    logger = log.bind(data_as_of=str(data_as_of))

    if not is_trading_day(data_as_of):
        logger.info("darwinian_scorer.weekend_skip", weekday=data_as_of.weekday())
        return _skipped_result("weekend", data_as_of)

    if jip_has_data_fn is not None and not await jip_has_data_fn(data_as_of):
        logger.info("darwinian_scorer.holiday_skip")
        return _skipped_result("market_holiday", data_as_of)

    unscored = await _load_unscored(db)
    logger.info("darwinian_scorer.unscored_loaded", count=len(unscored))

    scored_count = 0
    skipped_count = 0
    error_rows: list[dict[str, Any]] = []

    for row in unscored:
        state, accuracy = _score_single_prediction(row, data_as_of)
        if state == WindowState.NOT_YET or accuracy is None:
            skipped_count += 1
            continue
        row.accuracy_score = accuracy
        if row.actual_outcome is None:
            row.actual_outcome = json.dumps({"status": "evaluated", "window": state})
        scored_count += 1
        if accuracy < ERROR_ACCURACY_THRESHOLD:
            error_rows.append(
                {
                    "entity": row.entity,
                    "prediction_date": row.prediction_date,
                    "agent_id": row.agent_id,
                }
            )

    await db.flush()

    agent_rolling = await _fetch_rolling_scores(db)
    await _update_agent_weights(db, agent_rolling, data_as_of)

    spawn_triggers = detect_spawn_triggers(error_rows, reference_date=data_as_of)
    await _persist_spawn_triggers(db, spawn_triggers)
    await db.flush()

    logger.info(
        "darwinian_scorer.complete",
        scored_count=scored_count,
        spawn_trigger_count=len(spawn_triggers),
    )
    return {
        "status": "ok",
        "data_as_of": str(data_as_of),
        "scored_count": scored_count,
        "skipped_count": skipped_count,
        "spawn_triggers": spawn_triggers,
        "agent_rolling_accuracy": {
            k: str(v) if v is not None else None for k, v in agent_rolling.items()
        },
    }
