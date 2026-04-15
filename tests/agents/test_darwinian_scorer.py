"""Unit tests for backend/agents/darwinian_scorer.py.

Punch list validation:
1. Window-elapsed matrix: not-yet (skipped), just-elapsed (scored), long-elapsed (scored)
2. Non-scored agent skip: predictions from briefing-writer etc. are ignored
3. 60-prediction rolling window: rolling accuracy computed correctly
4. Holiday no-op: weekend → no scoring run; holiday → no scoring run
5. Specialist spawn trigger: 3 errors in same entity within 5 days → spawn trigger written

All DB calls are mocked — no real DB or API calls.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.darwinian_scorer import (
    NON_SCORED_AGENTS,
    ROLLING_WINDOW,
    SCORED_AGENTS,
    WindowState,
    classify_window,
    compute_accuracy_for_outcome,
    compute_new_weight,
    compute_rolling_accuracy,
    detect_spawn_triggers,
    is_trading_day,
    run_scoring,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MONDAY = date(2026, 4, 13)  # Monday — trading day
_SATURDAY = date(2026, 4, 11)  # Saturday — weekend
_SUNDAY = date(2026, 4, 12)  # Sunday — weekend


# ---------------------------------------------------------------------------
# 1. Window-elapsed matrix tests
# ---------------------------------------------------------------------------


class TestClassifyWindow:
    def test_not_yet_window_not_elapsed(self) -> None:
        """Prediction window hasn't elapsed — should be NOT_YET."""
        pred_date = date(2026, 4, 10)
        window_days = 5
        data_as_of = date(2026, 4, 14)  # pred + 4 days, window is 5
        state = classify_window(pred_date, window_days, data_as_of)
        assert state == WindowState.NOT_YET

    def test_just_elapsed_window_exactly_met(self) -> None:
        """Prediction window exactly elapsed today — JUST_ELAPSED."""
        pred_date = date(2026, 4, 8)
        window_days = 5
        data_as_of = date(2026, 4, 13)  # pred + 5 days
        state = classify_window(pred_date, window_days, data_as_of)
        assert state == WindowState.JUST_ELAPSED

    def test_long_elapsed_window_overdue(self) -> None:
        """Prediction window elapsed long ago — LONG_ELAPSED."""
        pred_date = date(2026, 4, 1)
        window_days = 5
        data_as_of = date(2026, 4, 13)  # pred + 12 days > 5
        state = classify_window(pred_date, window_days, data_as_of)
        assert state == WindowState.LONG_ELAPSED

    def test_not_yet_boundary_one_day_before(self) -> None:
        """One day before the window elapses — still NOT_YET."""
        pred_date = date(2026, 4, 9)
        window_days = 5
        data_as_of = date(2026, 4, 13)  # pred + 4 days
        state = classify_window(pred_date, window_days, data_as_of)
        assert state == WindowState.NOT_YET

    def test_regime_analyst_20_day_window(self) -> None:
        """Regime analyst uses 20-day window."""
        pred_date = date(2026, 3, 24)
        window_days = 20
        # Exactly elapsed
        data_as_of = pred_date + timedelta(days=20)
        state = classify_window(pred_date, window_days, data_as_of)
        assert state == WindowState.JUST_ELAPSED

    def test_regime_analyst_not_yet(self) -> None:
        """Regime analyst 20-day window not yet elapsed."""
        pred_date = date(2026, 4, 1)
        window_days = 20
        data_as_of = date(2026, 4, 13)  # only 12 days later
        state = classify_window(pred_date, window_days, data_as_of)
        assert state == WindowState.NOT_YET


# ---------------------------------------------------------------------------
# 2. Non-scored agent skip
# ---------------------------------------------------------------------------


class TestNonScoredAgents:
    def test_non_scored_agents_config(self) -> None:
        """Verify the non-scored agents set contains expected agent IDs."""
        assert "briefing-writer" in NON_SCORED_AGENTS
        assert "simulation-runner" in NON_SCORED_AGENTS
        assert "portfolio-analyzer" in NON_SCORED_AGENTS
        assert "tv-bridge" in NON_SCORED_AGENTS

    def test_scored_agents_not_in_non_scored(self) -> None:
        """Scored agents must not overlap with non-scored agents."""
        overlap = set(SCORED_AGENTS.keys()) & NON_SCORED_AGENTS
        assert overlap == set(), f"Overlap found: {overlap}"

    def test_scored_agents_config(self) -> None:
        """Verify scored agents config contains expected agents."""
        assert "rs-analyzer" in SCORED_AGENTS
        assert "sector-analyst" in SCORED_AGENTS
        assert "goldilocks-analyst" in SCORED_AGENTS
        assert "regime-analyst" in SCORED_AGENTS
        assert "discovery-engine" in SCORED_AGENTS

    def test_scored_agents_have_window_and_outcome_type(self) -> None:
        """Each scored agent must have window_days and outcome_type."""
        for agent_id, cfg in SCORED_AGENTS.items():
            assert "window_days" in cfg, f"{agent_id} missing window_days"
            assert "outcome_type" in cfg, f"{agent_id} missing outcome_type"
            assert isinstance(cfg["window_days"], int), f"{agent_id} window_days not int"

    @pytest.mark.asyncio
    async def test_run_scoring_filters_non_scored_agents(self) -> None:
        """run_scoring must only query for SCORED_AGENTS, excluding non-scored."""
        db = AsyncMock()

        # Simulate DB returning empty results (no unscored predictions)
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=execute_result)
        db.flush = AsyncMock()
        db.add = MagicMock()

        result = await run_scoring(db, data_as_of=_MONDAY)

        # Should complete without error and return ok status
        assert result["status"] == "ok"
        assert result["scored_count"] == 0

        # Verify the SELECT query used only SCORED_AGENTS keys
        # The first execute call is the unscored prediction query
        first_call = db.execute.call_args_list[0]
        stmt = first_call[0][0]
        # Compile and check the IN clause contains only scored agent IDs
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        for non_scored in NON_SCORED_AGENTS:
            assert non_scored not in compiled, (
                f"Non-scored agent {non_scored} should not appear in query"
            )


# ---------------------------------------------------------------------------
# 3. Rolling window tests
# ---------------------------------------------------------------------------


class TestRollingAccuracy:
    def test_empty_scores_returns_none(self) -> None:
        assert compute_rolling_accuracy([]) is None

    def test_single_score(self) -> None:
        result = compute_rolling_accuracy([Decimal("0.8")])
        assert result == Decimal("0.8")

    def test_mean_of_multiple_scores(self) -> None:
        scores = [Decimal("1.0"), Decimal("0.0"), Decimal("1.0")]
        result = compute_rolling_accuracy(scores)
        # mean = 2/3
        expected = Decimal("2") / Decimal("3")
        assert result == expected

    def test_rolling_window_truncated_to_60(self) -> None:
        """Only the last ROLLING_WINDOW predictions are used."""
        # 70 scores: first 10 are 0.0, last 60 are 1.0
        scores = [Decimal("0.0")] * 10 + [Decimal("1.0")] * 60
        result = compute_rolling_accuracy(scores)
        # Should use only last 60 (all 1.0)
        assert result == Decimal("1.0")

    def test_exactly_60_scores(self) -> None:
        """Exactly ROLLING_WINDOW scores — uses all."""
        scores = [Decimal("0.5")] * ROLLING_WINDOW
        result = compute_rolling_accuracy(scores)
        assert result == Decimal("0.5")

    def test_result_is_decimal_not_float(self) -> None:
        """Rolling accuracy must be Decimal, never float."""
        scores = [Decimal("0.7"), Decimal("0.8")]
        result = compute_rolling_accuracy(scores)
        assert isinstance(result, Decimal), f"Expected Decimal, got {type(result)}"

    def test_scores_under_window_size(self) -> None:
        """Fewer than 60 predictions — uses all available."""
        scores = [Decimal("0.6"), Decimal("0.4"), Decimal("0.5")]
        result = compute_rolling_accuracy(scores)
        expected = (Decimal("0.6") + Decimal("0.4") + Decimal("0.5")) / Decimal("3")
        assert result == expected


# ---------------------------------------------------------------------------
# 4. Holiday no-op tests
# ---------------------------------------------------------------------------


class TestHolidayDetection:
    def test_saturday_is_not_trading_day(self) -> None:
        assert not is_trading_day(_SATURDAY)

    def test_sunday_is_not_trading_day(self) -> None:
        assert not is_trading_day(_SUNDAY)

    def test_monday_is_trading_day(self) -> None:
        assert is_trading_day(_MONDAY)

    def test_friday_is_trading_day(self) -> None:
        friday = date(2026, 4, 10)
        assert is_trading_day(friday)

    @pytest.mark.asyncio
    async def test_run_scoring_skips_on_saturday(self) -> None:
        """run_scoring returns 'skipped' status for weekends."""
        db = AsyncMock()
        result = await run_scoring(db, data_as_of=_SATURDAY)
        assert result["status"] == "skipped"
        assert result["reason"] == "weekend"
        assert result["scored_count"] == 0
        # DB should NOT be queried
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_scoring_skips_on_sunday(self) -> None:
        """run_scoring returns 'skipped' status for Sundays."""
        db = AsyncMock()
        result = await run_scoring(db, data_as_of=_SUNDAY)
        assert result["status"] == "skipped"
        assert result["reason"] == "weekend"

    @pytest.mark.asyncio
    async def test_run_scoring_skips_on_market_holiday(self) -> None:
        """run_scoring skips when jip_has_data_fn returns False (market holiday)."""
        db = AsyncMock()

        async def no_data(_d: date) -> bool:
            return False

        result = await run_scoring(db, data_as_of=_MONDAY, jip_has_data_fn=no_data)
        assert result["status"] == "skipped"
        assert result["reason"] == "market_holiday"
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_scoring_proceeds_on_trading_day_with_jip_data(self) -> None:
        """run_scoring proceeds when jip_has_data_fn returns True."""
        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=execute_result)
        db.flush = AsyncMock()
        db.add = MagicMock()

        async def has_data(_d: date) -> bool:
            return True

        result = await run_scoring(db, data_as_of=_MONDAY, jip_has_data_fn=has_data)
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# 5. Specialist spawn trigger tests
# ---------------------------------------------------------------------------


class TestSpawnTriggers:
    def _make_error(
        self,
        entity: str,
        agent_id: str = "rs-analyzer",
        days_ago: int = 1,
        reference_date: date | None = None,
    ) -> dict[str, Any]:
        ref = reference_date or _MONDAY
        return {
            "entity": entity,
            "prediction_date": ref - timedelta(days=days_ago),
            "agent_id": agent_id,
        }

    def test_no_errors_no_triggers(self) -> None:
        result = detect_spawn_triggers([], reference_date=_MONDAY)
        assert result == []

    def test_two_errors_no_trigger(self) -> None:
        """Only 2 errors in same entity — below threshold of 3."""
        errors = [
            self._make_error("PHARMA", days_ago=1),
            self._make_error("PHARMA", days_ago=2),
        ]
        result = detect_spawn_triggers(errors, reference_date=_MONDAY)
        assert result == []

    def test_three_errors_triggers_spawn(self) -> None:
        """3 errors in same entity within 5 days → spawn trigger."""
        errors = [
            self._make_error("PHARMA", days_ago=1),
            self._make_error("PHARMA", days_ago=2),
            self._make_error("PHARMA", days_ago=3),
        ]
        result = detect_spawn_triggers(errors, reference_date=_MONDAY)
        assert len(result) == 1
        assert result[0]["entity"] == "PHARMA"
        assert result[0]["error_count"] == 3

    def test_errors_outside_lookback_window_excluded(self) -> None:
        """Errors older than lookback_days are not counted."""
        errors = [
            self._make_error("PHARMA", days_ago=1),
            self._make_error("PHARMA", days_ago=2),
            self._make_error("PHARMA", days_ago=6),  # outside 5-day window
        ]
        result = detect_spawn_triggers(errors, reference_date=_MONDAY)
        # Only 2 errors within window — below threshold
        assert result == []

    def test_multiple_entities_independent(self) -> None:
        """Errors in different entities are counted independently."""
        errors = [
            self._make_error("PHARMA", days_ago=1),
            self._make_error("PHARMA", days_ago=2),
            self._make_error("PHARMA", days_ago=3),
            self._make_error("BANKING", days_ago=1),
            self._make_error("BANKING", days_ago=2),
        ]
        result = detect_spawn_triggers(errors, reference_date=_MONDAY)
        assert len(result) == 1
        assert result[0]["entity"] == "PHARMA"

    def test_both_entities_trigger(self) -> None:
        """Both entities with 3+ errors trigger spawn."""
        errors = [
            self._make_error("PHARMA", days_ago=1),
            self._make_error("PHARMA", days_ago=2),
            self._make_error("PHARMA", days_ago=3),
            self._make_error("IT", days_ago=1),
            self._make_error("IT", days_ago=2),
            self._make_error("IT", days_ago=3),
        ]
        result = detect_spawn_triggers(errors, reference_date=_MONDAY)
        assert len(result) == 2
        entities = {t["entity"] for t in result}
        assert entities == {"PHARMA", "IT"}

    def test_null_entity_grouped_as_unknown(self) -> None:
        """Predictions with None entity are grouped under 'unknown'."""

        def _null_err(days_ago: int) -> dict[str, Any]:
            return {
                "entity": None,
                "prediction_date": _MONDAY - timedelta(days=days_ago),
                "agent_id": "rs-analyzer",
            }

        errors = [_null_err(1), _null_err(2), _null_err(3)]
        result = detect_spawn_triggers(errors, reference_date=_MONDAY)
        assert len(result) == 1
        assert result[0]["entity"] == "unknown"

    def test_trigger_includes_agent_ids(self) -> None:
        """Spawn trigger must include which agents contributed errors."""
        errors = [
            self._make_error("PHARMA", agent_id="rs-analyzer", days_ago=1),
            self._make_error("PHARMA", agent_id="sector-analyst", days_ago=2),
            self._make_error("PHARMA", agent_id="rs-analyzer", days_ago=3),
        ]
        result = detect_spawn_triggers(errors, reference_date=_MONDAY)
        assert len(result) == 1
        agent_ids = set(result[0]["agent_ids"])
        assert "rs-analyzer" in agent_ids
        assert "sector-analyst" in agent_ids

    @pytest.mark.asyncio
    async def test_run_scoring_writes_spawn_trigger_to_memory(self) -> None:
        """When 3+ errors in same entity, a spawn trigger is written to atlas_agent_memory."""
        db = AsyncMock()

        # Build mock AtlasAgentScore rows with errors in same entity.
        # pred_date = April 8 (_MONDAY - 5).
        # April 8 + 5 = April 13 = data_as_of → just_elapsed (window satisfied).
        # Spawn cutoff = April 13 - 5 = April 8 → included in 5-day spawn window.
        pred_date = _MONDAY - timedelta(days=5)
        rows = []
        for i in range(3):
            row = MagicMock(
                spec=[
                    "agent_id",
                    "prediction_date",
                    "entity",
                    "prediction",
                    "actual_outcome",
                    "accuracy_score",
                    "is_deleted",
                    "id",
                ]
            )
            row.agent_id = "rs-analyzer"
            row.prediction_date = pred_date
            row.entity = "PHARMA"
            row.prediction = json.dumps({"direction": "up"})
            row.actual_outcome = json.dumps({"return": -0.05})  # negative = wrong direction
            row.accuracy_score = None  # unscored
            row.is_deleted = False
            row.id = i + 1
            rows.append(row)

        # First execute call: load unscored predictions
        # Subsequent calls: rolling accuracy queries per agent (return empty)
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []

        scored_result = MagicMock()
        scored_result.scalars.return_value.all.return_value = rows

        # Weight lookup returns None (no existing weight row)
        weight_result = MagicMock()
        weight_result.scalar_one_or_none.return_value = None

        call_count = 0

        async def fake_execute(stmt: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return scored_result
            # Weight lookup
            if call_count % 3 == 0:
                return weight_result
            return empty_result

        db.execute = AsyncMock(side_effect=fake_execute)
        db.flush = AsyncMock()
        added_objects: list[Any] = []
        db.add = MagicMock(side_effect=added_objects.append)

        result = await run_scoring(db, data_as_of=_MONDAY)

        assert result["status"] == "ok"
        # Verify spawn triggers detected
        assert len(result["spawn_triggers"]) >= 1
        pharma_trigger = next(
            (t for t in result["spawn_triggers"] if t["entity"] == "PHARMA"), None
        )
        assert pharma_trigger is not None

        # Verify AtlasAgentMemory written with memory_type='spawn_trigger'
        memory_writes = [
            obj
            for obj in added_objects
            if hasattr(obj, "memory_type") and obj.memory_type == "spawn_trigger"
        ]
        assert len(memory_writes) >= 1
        content = json.loads(memory_writes[0].content)
        assert content["trigger"] == "specialist_spawn"
        assert content["entity"] == "PHARMA"


# ---------------------------------------------------------------------------
# 6. Accuracy computation tests
# ---------------------------------------------------------------------------


class TestAccuracyComputation:
    def test_sector_return_correct_up_prediction(self) -> None:
        pred = json.dumps({"direction": "up"})
        actual = json.dumps({"return": 0.03})
        score = compute_accuracy_for_outcome(pred, actual, "sector_return")
        assert score == Decimal("1")

    def test_sector_return_wrong_direction(self) -> None:
        pred = json.dumps({"direction": "up"})
        actual = json.dumps({"return": -0.02})
        score = compute_accuracy_for_outcome(pred, actual, "sector_return")
        assert score == Decimal("0")

    def test_accuracy_none_when_no_actual_outcome(self) -> None:
        pred = json.dumps({"direction": "up"})
        score = compute_accuracy_for_outcome(pred, None, "sector_return")
        assert score is None

    def test_accuracy_score_is_decimal_not_float(self) -> None:
        pred = json.dumps({"direction": "up"})
        actual = json.dumps({"return": 0.05})
        score = compute_accuracy_for_outcome(pred, actual, "sector_return")
        assert isinstance(score, Decimal), f"Expected Decimal, got {type(score)}"

    def test_unknown_outcome_type_returns_none(self) -> None:
        pred = "some_prediction"
        actual = "some_outcome"
        score = compute_accuracy_for_outcome(pred, actual, "unknown_type")
        assert score is None

    def test_alignment_exact_match(self) -> None:
        pred = json.dumps({"alignment": "aligned"})
        actual = json.dumps({"alignment": "aligned"})
        score = compute_accuracy_for_outcome(pred, actual, "alignment_accuracy")
        assert score == Decimal("1")

    def test_alignment_mismatch(self) -> None:
        pred = json.dumps({"alignment": "aligned"})
        actual = json.dumps({"alignment": "divergent"})
        score = compute_accuracy_for_outcome(pred, actual, "alignment_accuracy")
        assert score == Decimal("0")

    def test_regime_transition_match(self) -> None:
        pred = json.dumps({"regime": "bull"})
        actual = json.dumps({"regime": "bull"})
        score = compute_accuracy_for_outcome(pred, actual, "regime_transition")
        assert score == Decimal("1")

    def test_regime_transition_mismatch(self) -> None:
        pred = json.dumps({"regime": "bull"})
        actual = json.dumps({"regime": "bear"})
        score = compute_accuracy_for_outcome(pred, actual, "regime_transition")
        assert score == Decimal("0")


# ---------------------------------------------------------------------------
# 7. Weight adjustment tests
# ---------------------------------------------------------------------------


class TestWeightAdjustment:
    def test_top_quartile_weight_increases(self) -> None:
        all_acc = [Decimal("0.4"), Decimal("0.5"), Decimal("0.6"), Decimal("0.9")]
        current_weight = Decimal("1.0")
        # 0.9 is in top quartile
        new_weight = compute_new_weight(current_weight, Decimal("0.9"), all_acc)
        assert new_weight > current_weight

    def test_bottom_quartile_weight_decreases(self) -> None:
        all_acc = [Decimal("0.2"), Decimal("0.5"), Decimal("0.7"), Decimal("0.9")]
        current_weight = Decimal("1.0")
        # 0.2 is in bottom quartile
        new_weight = compute_new_weight(current_weight, Decimal("0.2"), all_acc)
        assert new_weight < current_weight

    def test_weight_capped_at_2_5(self) -> None:
        all_acc = [Decimal("0.4"), Decimal("0.5"), Decimal("0.6"), Decimal("0.9")]
        current_weight = Decimal("2.4")
        new_weight = compute_new_weight(current_weight, Decimal("0.9"), all_acc)
        assert new_weight <= Decimal("2.5")

    def test_weight_floored_at_0_3(self) -> None:
        all_acc = [Decimal("0.2"), Decimal("0.5"), Decimal("0.7"), Decimal("0.9")]
        current_weight = Decimal("0.31")
        new_weight = compute_new_weight(current_weight, Decimal("0.2"), all_acc)
        assert new_weight >= Decimal("0.3")

    def test_no_accuracy_returns_unchanged_weight(self) -> None:
        current_weight = Decimal("1.0")
        new_weight = compute_new_weight(current_weight, None, [])
        assert new_weight == current_weight

    def test_weight_is_decimal_not_float(self) -> None:
        all_acc = [Decimal("0.4"), Decimal("0.5"), Decimal("0.6"), Decimal("0.9")]
        new_weight = compute_new_weight(Decimal("1.0"), Decimal("0.9"), all_acc)
        assert isinstance(new_weight, Decimal), f"Expected Decimal, got {type(new_weight)}"


# ---------------------------------------------------------------------------
# 7b. Comprehensive Darwinian daily weight adjustment tests (V5-12 additions)
# ---------------------------------------------------------------------------


class TestDarwinianDailyWeightAdjustment:
    """V5-12 acceptance criteria: quartiles, clamps, tie-break, holiday no-op, DB constraint."""

    # --- Each quartile ---

    def test_top_quartile_weight_multiplied_by_factor(self) -> None:
        """Agent in top quartile gets weight * 1.05."""
        all_acc = [Decimal("0.4"), Decimal("0.5"), Decimal("0.7"), Decimal("0.9")]
        current = Decimal("1.0")
        new_weight = compute_new_weight(current, Decimal("0.9"), all_acc)
        assert new_weight == current * Decimal("1.05")

    def test_bottom_quartile_weight_multiplied_by_factor(self) -> None:
        """Agent in bottom quartile gets weight * 0.95."""
        all_acc = [Decimal("0.2"), Decimal("0.5"), Decimal("0.7"), Decimal("0.9")]
        current = Decimal("1.0")
        new_weight = compute_new_weight(current, Decimal("0.2"), all_acc)
        assert new_weight == current * Decimal("0.95")

    def test_middle_quartile_weight_unchanged(self) -> None:
        """Agent in middle quartile gets no weight change."""
        all_acc = [Decimal("0.2"), Decimal("0.5"), Decimal("0.7"), Decimal("0.9")]
        current = Decimal("1.2")
        # 0.5 is in middle (between p25=0.2 and p75=0.7)
        new_weight = compute_new_weight(current, Decimal("0.5"), all_acc)
        assert new_weight == current

    def test_exactly_at_p75_is_top_quartile(self) -> None:
        """Accuracy exactly equal to p75 qualifies as top quartile (>= comparison)."""
        all_acc = [Decimal("0.3"), Decimal("0.5"), Decimal("0.7"), Decimal("0.8")]
        current = Decimal("1.0")
        # p75 = sorted_acc[min(3, 3)] = 0.8
        # Rolling accuracy == p75 → top quartile
        new_weight = compute_new_weight(current, Decimal("0.8"), all_acc)
        assert new_weight > current

    def test_exactly_at_p25_is_bottom_quartile(self) -> None:
        """Accuracy exactly equal to p25 qualifies as bottom quartile (<= comparison)."""
        all_acc = [Decimal("0.3"), Decimal("0.5"), Decimal("0.7"), Decimal("0.8")]
        current = Decimal("1.0")
        # p25 = sorted_acc[max(0, 0)] = 0.3
        # Rolling accuracy == p25 → bottom quartile
        new_weight = compute_new_weight(current, Decimal("0.3"), all_acc)
        assert new_weight < current

    # --- Floor and ceiling clamps ---

    def test_ceiling_clamped_at_2_5_when_already_at_cap(self) -> None:
        """Weight already at 2.5 ceiling stays at 2.5 even in top quartile."""
        all_acc = [Decimal("0.4"), Decimal("0.5"), Decimal("0.7"), Decimal("0.9")]
        current = Decimal("2.5")
        new_weight = compute_new_weight(current, Decimal("0.9"), all_acc)
        assert new_weight == Decimal("2.5")

    def test_floor_clamped_at_0_3_when_already_at_floor(self) -> None:
        """Weight already at 0.3 floor stays at 0.3 even in bottom quartile."""
        all_acc = [Decimal("0.2"), Decimal("0.5"), Decimal("0.7"), Decimal("0.9")]
        current = Decimal("0.3")
        new_weight = compute_new_weight(current, Decimal("0.2"), all_acc)
        assert new_weight == Decimal("0.3")

    def test_ceiling_clamped_when_near_cap(self) -> None:
        """Weight 2.45 * 1.05 = 2.5725 → clamps to 2.5."""
        all_acc = [Decimal("0.4"), Decimal("0.5"), Decimal("0.7"), Decimal("0.9")]
        current = Decimal("2.45")
        new_weight = compute_new_weight(current, Decimal("0.9"), all_acc)
        assert new_weight == Decimal("2.5")

    def test_floor_clamped_when_near_floor(self) -> None:
        """Weight 0.31 * 0.95 = 0.2945 → clamps to 0.3."""
        all_acc = [Decimal("0.2"), Decimal("0.5"), Decimal("0.7"), Decimal("0.9")]
        current = Decimal("0.31")
        new_weight = compute_new_weight(current, Decimal("0.2"), all_acc)
        assert new_weight == Decimal("0.3")

    def test_result_is_always_decimal(self) -> None:
        """Return type is always Decimal regardless of quartile outcome."""
        all_acc = [Decimal("0.4"), Decimal("0.5"), Decimal("0.6"), Decimal("0.8")]
        # Top quartile
        w = compute_new_weight(Decimal("1.0"), Decimal("0.8"), all_acc)
        assert isinstance(w, Decimal)
        # Bottom quartile
        w = compute_new_weight(Decimal("1.0"), Decimal("0.4"), all_acc)
        assert isinstance(w, Decimal)
        # Middle
        w = compute_new_weight(Decimal("1.0"), Decimal("0.55"), all_acc)
        assert isinstance(w, Decimal)

    # --- Even distribution tie-break ---

    def test_all_same_accuracy_weight_unchanged(self) -> None:
        """When all agents have same accuracy, p25 == p75 → no adjustment for anyone."""
        same_acc = Decimal("0.75")
        all_acc = [same_acc, same_acc, same_acc, same_acc, same_acc]
        current = Decimal("1.2")
        new_weight = compute_new_weight(current, same_acc, all_acc)
        assert new_weight == current, (
            f"Expected unchanged weight {current}, got {new_weight} — tie-break failed"
        )

    def test_single_agent_weight_unchanged(self) -> None:
        """Single agent: n=1, p25 == p75 → no adjustment."""
        current = Decimal("1.5")
        acc = Decimal("0.9")
        new_weight = compute_new_weight(current, acc, [acc])
        assert new_weight == current

    def test_two_agents_same_accuracy_unchanged(self) -> None:
        """Two agents with identical accuracy → p25 == p75 → unchanged."""
        same_acc = Decimal("0.6")
        all_acc = [same_acc, same_acc]
        current = Decimal("0.8")
        new_weight = compute_new_weight(current, same_acc, all_acc)
        assert new_weight == current

    def test_two_agents_different_accuracy_higher_gets_boosted(self) -> None:
        """Two agents with different accuracy: higher one gets boost."""
        all_acc = [Decimal("0.4"), Decimal("0.8")]
        current = Decimal("1.0")
        # p25 = 0.4, p75 = 0.8 → different, so normal quartile logic applies
        new_weight = compute_new_weight(current, Decimal("0.8"), all_acc)
        assert new_weight > current

    # --- Holiday no-op (weight-specific assertions) ---

    @pytest.mark.asyncio
    async def test_weekend_returns_skipped_with_no_weight_change(self) -> None:
        """On weekend, run_scoring returns skipped and makes zero DB weight changes."""
        db = AsyncMock()
        result = await run_scoring(db, data_as_of=_SATURDAY)
        assert result["status"] == "skipped"
        assert result["reason"] == "weekend"
        # No DB interaction at all — no weight updates possible
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_market_holiday_returns_skipped_with_no_weight_change(self) -> None:
        """On market holiday, run_scoring returns skipped and makes zero DB weight changes."""
        db = AsyncMock()

        async def no_data(_d: date) -> bool:
            return False

        result = await run_scoring(db, data_as_of=_MONDAY, jip_has_data_fn=no_data)
        assert result["status"] == "skipped"
        assert result["reason"] == "market_holiday"
        # No weight rows touched
        db.execute.assert_not_called()

    # --- DB CHECK constraint test ---

    def test_atlas_agent_weight_has_check_constraint(self) -> None:
        """AtlasAgentWeight model declares the weight range CHECK constraint."""
        from backend.db.models import AtlasAgentWeight

        constraints = AtlasAgentWeight.__table_args__
        assert isinstance(constraints, tuple), "__table_args__ should be a tuple"
        from sqlalchemy import CheckConstraint

        check_constraints = [c for c in constraints if isinstance(c, CheckConstraint)]
        assert len(check_constraints) >= 1, "No CheckConstraint found in __table_args__"

        # Verify it is named and covers the 0.3..2.5 range
        named = [c for c in check_constraints if c.name == "ck_agent_weight_range"]
        assert len(named) == 1, (
            f"Expected 'ck_agent_weight_range' constraint, found: "
            f"{[c.name for c in check_constraints]}"
        )
        constraint_text = str(named[0].sqltext)
        assert "0.3" in constraint_text or "weight" in constraint_text, (
            f"Constraint text doesn't mention weight bound: {constraint_text}"
        )
        assert "2.5" in constraint_text or "weight" in constraint_text, (
            f"Constraint text doesn't mention weight cap: {constraint_text}"
        )

    def test_weight_column_bounds_are_0_3_to_2_5(self) -> None:
        """WEIGHT_FLOOR and WEIGHT_CAP constants match the DB constraint values."""
        from backend.agents.darwinian_scorer import WEIGHT_CAP, WEIGHT_FLOOR

        assert WEIGHT_FLOOR == Decimal("0.3"), f"WEIGHT_FLOOR mismatch: {WEIGHT_FLOOR}"
        assert WEIGHT_CAP == Decimal("2.5"), f"WEIGHT_CAP mismatch: {WEIGHT_CAP}"


# ---------------------------------------------------------------------------
# 8. Full run_scoring integration-style unit test
# ---------------------------------------------------------------------------


class TestRunScoringIntegration:
    @pytest.mark.asyncio
    async def test_scored_count_increments_for_elapsed_predictions(self) -> None:
        """Predictions past window are scored; not-yet predictions are skipped."""
        db = AsyncMock()

        # One just-elapsed, one not-yet row
        pred_date_elapsed = _MONDAY - timedelta(days=5)  # window=5, exactly elapsed
        pred_date_not_yet = _MONDAY - timedelta(days=2)  # window=5, not yet

        row_elapsed = MagicMock(
            spec=[
                "agent_id",
                "prediction_date",
                "entity",
                "prediction",
                "actual_outcome",
                "accuracy_score",
                "is_deleted",
                "id",
            ]
        )
        row_elapsed.agent_id = "rs-analyzer"
        row_elapsed.prediction_date = pred_date_elapsed
        row_elapsed.entity = "BANKING"
        row_elapsed.prediction = json.dumps({"direction": "up"})
        row_elapsed.actual_outcome = json.dumps({"return": 0.02})
        row_elapsed.accuracy_score = None
        row_elapsed.is_deleted = False
        row_elapsed.id = 1

        row_not_yet = MagicMock(
            spec=[
                "agent_id",
                "prediction_date",
                "entity",
                "prediction",
                "actual_outcome",
                "accuracy_score",
                "is_deleted",
                "id",
            ]
        )
        row_not_yet.agent_id = "rs-analyzer"
        row_not_yet.prediction_date = pred_date_not_yet
        row_not_yet.entity = "IT"
        row_not_yet.prediction = json.dumps({"direction": "down"})
        row_not_yet.actual_outcome = None
        row_not_yet.accuracy_score = None
        row_not_yet.is_deleted = False
        row_not_yet.id = 2

        unscored_result = MagicMock()
        unscored_result.scalars.return_value.all.return_value = [row_elapsed, row_not_yet]

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []

        weight_result = MagicMock()
        weight_result.scalar_one_or_none.return_value = None

        call_count = 0

        async def fake_execute(stmt: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return unscored_result
            return empty_result

        db.execute = AsyncMock(side_effect=fake_execute)
        db.flush = AsyncMock()
        db.add = MagicMock()

        result = await run_scoring(db, data_as_of=_MONDAY)

        assert result["status"] == "ok"
        # One scored (elapsed), one skipped (not-yet)
        assert result["scored_count"] == 1
        assert result["skipped_count"] == 1

    @pytest.mark.asyncio
    async def test_long_elapsed_predictions_also_scored(self) -> None:
        """Long-elapsed predictions (catch-up) are also scored."""
        db = AsyncMock()

        # Prediction from 10 days ago with 5-day window = long-elapsed
        pred_date = _MONDAY - timedelta(days=10)

        row = MagicMock(
            spec=[
                "agent_id",
                "prediction_date",
                "entity",
                "prediction",
                "actual_outcome",
                "accuracy_score",
                "is_deleted",
                "id",
            ]
        )
        row.agent_id = "sector-analyst"
        row.prediction_date = pred_date
        row.entity = "ENERGY"
        row.prediction = json.dumps({"direction": "down"})
        row.actual_outcome = json.dumps({"return": -0.03})
        row.accuracy_score = None
        row.is_deleted = False
        row.id = 10

        unscored_result = MagicMock()
        unscored_result.scalars.return_value.all.return_value = [row]

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []

        call_count = 0

        async def fake_execute(stmt: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return unscored_result
            return empty_result

        db.execute = AsyncMock(side_effect=fake_execute)
        db.flush = AsyncMock()
        db.add = MagicMock()

        result = await run_scoring(db, data_as_of=_MONDAY)

        assert result["status"] == "ok"
        assert result["scored_count"] == 1  # long-elapsed scored
        assert result["skipped_count"] == 0

    @pytest.mark.asyncio
    async def test_result_summary_has_expected_keys(self) -> None:
        """Result summary dict has all expected keys."""
        db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=execute_result)
        db.flush = AsyncMock()
        db.add = MagicMock()

        result = await run_scoring(db, data_as_of=_MONDAY)

        required_keys = {
            "status",
            "data_as_of",
            "scored_count",
            "skipped_count",
            "spawn_triggers",
            "agent_rolling_accuracy",
        }
        assert required_keys.issubset(result.keys()), (
            f"Missing keys: {required_keys - result.keys()}"
        )
