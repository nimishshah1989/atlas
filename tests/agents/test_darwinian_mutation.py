"""Unit tests for backend/agents/darwinian_mutation.py.

Punch list validation:
1. Full merge path: weight < 0.5 → mutation starts → shadow period runs → Sharpe improves → merge
2. Full revert path: weight < 0.5 → mutation starts → shadow runs → Sharpe degrades → revert
3. Advisory lock: second concurrent cycle attempt on same agent is rejected
4. Mutation history persistence: after merge/revert, mutation record has correct fields
5. Guardrails: max 3/month, only 1 active experiment at a time
6. Holiday no-op: weekend → skip

All DB calls are mocked — no real DB or API calls.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.darwinian_mutation import (
    MAX_MUTATIONS_PER_MONTH,
    MUTATION_TRIGGER_WEIGHT,
    SHADOW_TRADING_DAYS,
    _check_mutation_eligible,
    _count_trading_days_between,
    _evaluate_shadow,
    _merge_mutation,
    _revert_mutation,
    _start_mutation,
    acquire_advisory_lock,
    run_mutation_cycle,
)
from backend.db.models import AtlasAgentMutation, AtlasAgentWeight

# ---------------------------------------------------------------------------
# Test fixtures / constants
# ---------------------------------------------------------------------------

_MONDAY = date(2026, 4, 13)  # Monday — trading day
_SATURDAY = date(2026, 4, 11)  # Saturday — weekend
_FRIDAY = date(2026, 4, 10)  # Friday — trading day


def _make_weight(
    agent_id: str = "rs-analyzer",
    weight: str = "0.4",
    rolling_accuracy: str | None = "0.45",
) -> MagicMock:
    """Build a mock AtlasAgentWeight with the required attributes."""
    w = MagicMock(spec=AtlasAgentWeight)
    w.agent_id = agent_id
    w.weight = Decimal(weight)
    w.rolling_accuracy = Decimal(rolling_accuracy) if rolling_accuracy is not None else None
    w.mutation_count = 0
    w.last_mutation_date = None
    w.is_deleted = False
    return w


def _make_mutation(
    agent_id: str = "rs-analyzer",
    version: int = 1,
    status: str = "shadow",
    shadow_start_date: date = _MONDAY,
    original_sharpe: str | None = "0.45",
    mutated_sharpe: str | None = None,
    mutation_id: int = 1,
) -> MagicMock:
    """Build a mock AtlasAgentMutation with the required attributes."""
    m = MagicMock(spec=AtlasAgentMutation)
    m.id = mutation_id
    m.agent_id = agent_id
    m.version = version
    m.status = status
    m.mutation_type = "prompt_modification"
    m.description = "test mutation"
    m.shadow_start_date = shadow_start_date
    m.shadow_end_date = None
    m.original_sharpe = Decimal(original_sharpe) if original_sharpe is not None else None
    m.mutated_sharpe = Decimal(mutated_sharpe) if mutated_sharpe is not None else None
    m.outcome = None
    m.outcome_reason = None
    m.is_deleted = False
    return m


def _make_db(
    execute_results: list[Any] | None = None,
    lock_result: bool = True,
) -> AsyncMock:
    """Build a mock AsyncSession with configurable execute() return values."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    if execute_results is not None:
        db.execute = AsyncMock(side_effect=execute_results)
    else:
        # Default: lock acquired, scalar returns 0
        lock_row = MagicMock()
        lock_row.__getitem__ = MagicMock(return_value=lock_result)
        lock_result_mock = MagicMock()
        lock_result_mock.fetchone.return_value = lock_row

        default_result = MagicMock()
        default_result.scalar.return_value = 0
        default_result.scalar_one_or_none.return_value = None
        default_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(return_value=default_result)
    return db


# ---------------------------------------------------------------------------
# 1. _count_trading_days_between
# ---------------------------------------------------------------------------


class TestCountTradingDays:
    def test_same_day_trading(self) -> None:
        """Monday to Monday — 1 trading day."""
        assert _count_trading_days_between(_MONDAY, _MONDAY) == 1

    def test_same_day_weekend(self) -> None:
        """Saturday to Saturday — 0 trading days."""
        assert _count_trading_days_between(_SATURDAY, _SATURDAY) == 0

    def test_end_before_start(self) -> None:
        """End before start — 0 trading days."""
        assert _count_trading_days_between(_MONDAY, _FRIDAY) == 0

    def test_week_of_trading_days(self) -> None:
        """Monday to Friday — 5 trading days."""
        friday = _MONDAY + timedelta(days=4)
        assert _count_trading_days_between(_MONDAY, friday) == 5

    def test_spans_weekend(self) -> None:
        """Monday to next Monday — 6 trading days (Mon–Fri + next Mon)."""
        next_monday = _MONDAY + timedelta(days=7)
        assert _count_trading_days_between(_MONDAY, next_monday) == 6


# ---------------------------------------------------------------------------
# 2. Advisory lock
# ---------------------------------------------------------------------------


class TestAdvisoryLock:
    @pytest.mark.asyncio
    async def test_lock_acquired_returns_true(self) -> None:
        """When pg_try_advisory_xact_lock returns true → acquire_advisory_lock returns True."""
        db = AsyncMock()
        row = MagicMock()
        row.__getitem__ = MagicMock(return_value=True)
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute = AsyncMock(return_value=result)

        acquired = await acquire_advisory_lock(db, "rs-analyzer")
        assert acquired is True

    @pytest.mark.asyncio
    async def test_lock_not_acquired_returns_false(self) -> None:
        """When pg_try_advisory_xact_lock returns false → acquire_advisory_lock returns False."""
        db = AsyncMock()
        row = MagicMock()
        row.__getitem__ = MagicMock(return_value=False)
        result = MagicMock()
        result.fetchone.return_value = row
        db.execute = AsyncMock(return_value=result)

        acquired = await acquire_advisory_lock(db, "rs-analyzer")
        assert acquired is False

    @pytest.mark.asyncio
    async def test_concurrent_cycle_rejected_when_lock_unavailable(self) -> None:
        """run_mutation_cycle skips agent when advisory lock cannot be acquired."""
        # First execute: lock acquisition returns False (lock held by another process)
        lock_row = MagicMock()
        lock_row.__getitem__ = MagicMock(return_value=False)
        lock_result = MagicMock()
        lock_result.fetchone.return_value = lock_row

        db = AsyncMock()
        db.execute = AsyncMock(return_value=lock_result)
        db.flush = AsyncMock()
        db.add = MagicMock()

        result = await run_mutation_cycle(
            db, data_as_of=_MONDAY, candidate_agent_ids=["rs-analyzer"]
        )

        assert result["status"] == "ok"
        # No mutations started or evaluated — lock was blocked
        assert result["started"] == []
        assert result["evaluated"] == []


# ---------------------------------------------------------------------------
# 3. Holiday no-op
# ---------------------------------------------------------------------------


class TestHolidayNoOp:
    @pytest.mark.asyncio
    async def test_weekend_skipped(self) -> None:
        """run_mutation_cycle returns 'skipped' for weekends."""
        db = AsyncMock()
        result = await run_mutation_cycle(db, data_as_of=_SATURDAY)
        assert result["status"] == "skipped"
        assert result["reason"] == "weekend"
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_sunday_skipped(self) -> None:
        """run_mutation_cycle returns 'skipped' for Sunday."""
        sunday = date(2026, 4, 12)
        db = AsyncMock()
        result = await run_mutation_cycle(db, data_as_of=sunday)
        assert result["status"] == "skipped"
        assert result["reason"] == "weekend"


# ---------------------------------------------------------------------------
# 4. Eligibility guardrails
# ---------------------------------------------------------------------------


class TestMutationEligibility:
    @pytest.mark.asyncio
    async def test_weight_above_threshold_not_eligible(self) -> None:
        """Agent with weight >= 0.5 should not be eligible for mutation."""
        db = AsyncMock()
        weight_row = _make_weight(weight="0.6")
        eligible, reason = await _check_mutation_eligible(db, "rs-analyzer", _MONDAY, weight_row)
        assert not eligible
        assert "threshold" in reason

    @pytest.mark.asyncio
    async def test_active_shadow_blocks_new_mutation(self) -> None:
        """Agent with existing active shadow mutation is not eligible."""
        db = AsyncMock()

        existing_mutation = _make_mutation(status="shadow")

        # _get_active_shadow_mutation returns existing
        shadow_result = MagicMock()
        shadow_result.scalar_one_or_none.return_value = existing_mutation
        db.execute = AsyncMock(return_value=shadow_result)

        weight_row = _make_weight(weight="0.3")  # below threshold
        eligible, reason = await _check_mutation_eligible(db, "rs-analyzer", _MONDAY, weight_row)
        assert not eligible
        assert "active shadow" in reason

    @pytest.mark.asyncio
    async def test_monthly_limit_blocks_mutation(self) -> None:
        """When 3 mutations this month → not eligible."""
        db = AsyncMock()

        # First call: _get_active_shadow_mutation → None
        # Second call: _count_mutations_this_month → MAX_MUTATIONS_PER_MONTH
        no_shadow = MagicMock()
        no_shadow.scalar_one_or_none.return_value = None

        count_result = MagicMock()
        count_result.scalar.return_value = MAX_MUTATIONS_PER_MONTH

        db.execute = AsyncMock(side_effect=[no_shadow, count_result])

        weight_row = _make_weight(weight="0.3")
        eligible, reason = await _check_mutation_eligible(db, "rs-analyzer", _MONDAY, weight_row)
        assert not eligible
        assert "monthly mutation limit" in reason

    @pytest.mark.asyncio
    async def test_active_global_shadow_blocks_new_agent(self) -> None:
        """Only 1 concurrent shadow experiment allowed globally."""
        db = AsyncMock()

        no_shadow = MagicMock()
        no_shadow.scalar_one_or_none.return_value = None

        zero_month = MagicMock()
        zero_month.scalar.return_value = 0

        active_global = MagicMock()
        active_global.scalar.return_value = 1  # another agent in shadow

        db.execute = AsyncMock(side_effect=[no_shadow, zero_month, active_global])

        weight_row = _make_weight(weight="0.3")
        eligible, reason = await _check_mutation_eligible(db, "rs-analyzer", _MONDAY, weight_row)
        assert not eligible
        assert "another agent" in reason


# ---------------------------------------------------------------------------
# 5. _start_mutation
# ---------------------------------------------------------------------------


class TestStartMutation:
    @pytest.mark.asyncio
    async def test_start_mutation_creates_shadow_record(self) -> None:
        """_start_mutation creates a mutation in 'shadow' status with correct fields."""
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        # _get_next_version → max_version = 0 → next = 1
        version_result = MagicMock()
        version_result.scalar.return_value = 0
        db.execute = AsyncMock(return_value=version_result)

        weight_row = _make_weight(weight="0.4", rolling_accuracy="0.42")
        mutation = await _start_mutation(db, "rs-analyzer", _MONDAY, weight_row)

        assert mutation.agent_id == "rs-analyzer"
        assert mutation.version == 1
        assert mutation.status == "shadow"
        assert mutation.shadow_start_date == _MONDAY
        assert mutation.original_sharpe == Decimal("0.42")
        assert mutation.mutated_sharpe is None
        db.add.assert_called_once_with(mutation)
        db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_start_mutation_null_rolling_accuracy(self) -> None:
        """_start_mutation handles NULL rolling_accuracy gracefully."""
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        version_result = MagicMock()
        version_result.scalar.return_value = 2
        db.execute = AsyncMock(return_value=version_result)

        weight_row = _make_weight(weight="0.35", rolling_accuracy=None)
        mutation = await _start_mutation(db, "sector-analyst", _MONDAY, weight_row)

        assert mutation.original_sharpe is None
        assert mutation.version == 3  # next after max=2


# ---------------------------------------------------------------------------
# 6. _evaluate_shadow
# ---------------------------------------------------------------------------


class TestEvaluateShadow:
    @pytest.mark.asyncio
    async def test_shadow_pending_before_5_days(self) -> None:
        """Shadow evaluation returns 'pending' before 5 trading days elapsed."""
        db = AsyncMock()
        mutation = _make_mutation(shadow_start_date=_MONDAY)
        # data_as_of is 3 trading days after start (Mon, Tue, Wed)
        data_as_of = _MONDAY + timedelta(days=2)  # Wednesday
        weight_row = _make_weight(rolling_accuracy="0.55")

        result = await _evaluate_shadow(db, mutation, data_as_of, weight_row)
        assert result == "pending"

    @pytest.mark.asyncio
    async def test_shadow_merged_after_5_days_improved_sharpe(self) -> None:
        """Shadow evaluation returns 'merged' when Sharpe improved after 5+ trading days."""
        db = AsyncMock()
        # Shadow started on Monday, data_as_of is 5 trading days later (Friday)
        start = _MONDAY
        data_as_of = _MONDAY + timedelta(days=4)  # Friday (Mon+4 = 5 days incl)

        mutation = _make_mutation(shadow_start_date=start, original_sharpe="0.42")
        weight_row = _make_weight(rolling_accuracy="0.60")  # improved

        result = await _evaluate_shadow(db, mutation, data_as_of, weight_row)
        assert result == "merged"
        assert mutation.mutated_sharpe == Decimal("0.60")

    @pytest.mark.asyncio
    async def test_shadow_merged_when_sharpe_equal(self) -> None:
        """Shadow evaluation returns 'merged' when Sharpe is unchanged (>= original)."""
        db = AsyncMock()
        start = _MONDAY
        data_as_of = _MONDAY + timedelta(days=4)

        mutation = _make_mutation(shadow_start_date=start, original_sharpe="0.50")
        weight_row = _make_weight(rolling_accuracy="0.50")  # same

        result = await _evaluate_shadow(db, mutation, data_as_of, weight_row)
        assert result == "merged"

    @pytest.mark.asyncio
    async def test_shadow_reverted_after_5_days_degraded_sharpe(self) -> None:
        """Shadow evaluation returns 'reverted' when Sharpe degraded after 5+ trading days."""
        db = AsyncMock()
        start = _MONDAY
        data_as_of = _MONDAY + timedelta(days=4)

        mutation = _make_mutation(shadow_start_date=start, original_sharpe="0.60")
        weight_row = _make_weight(rolling_accuracy="0.40")  # degraded

        result = await _evaluate_shadow(db, mutation, data_as_of, weight_row)
        assert result == "reverted"
        assert mutation.mutated_sharpe == Decimal("0.40")

    @pytest.mark.asyncio
    async def test_shadow_reverted_when_current_sharpe_null(self) -> None:
        """Shadow evaluation returns 'reverted' when current rolling_accuracy is NULL."""
        db = AsyncMock()
        start = _MONDAY
        data_as_of = _MONDAY + timedelta(days=4)

        mutation = _make_mutation(shadow_start_date=start, original_sharpe="0.55")
        weight_row = _make_weight(rolling_accuracy=None)  # NULL

        result = await _evaluate_shadow(db, mutation, data_as_of, weight_row)
        assert result == "reverted"

    @pytest.mark.asyncio
    async def test_shadow_pending_when_no_start_date(self) -> None:
        """Shadow evaluation returns 'pending' when shadow_start_date is None."""
        db = AsyncMock()
        mutation = _make_mutation()
        mutation.shadow_start_date = None
        weight_row = _make_weight(rolling_accuracy="0.70")

        result = await _evaluate_shadow(db, mutation, _MONDAY, weight_row)
        assert result == "pending"


# ---------------------------------------------------------------------------
# 7. _merge_mutation / _revert_mutation — history persistence
# ---------------------------------------------------------------------------


class TestMutationHistoryPersistence:
    @pytest.mark.asyncio
    async def test_merge_mutation_updates_fields(self) -> None:
        """_merge_mutation sets status=merged, outcome, shadow_end_date, outcome_reason."""
        db = AsyncMock()
        db.flush = AsyncMock()

        mutation = _make_mutation(original_sharpe="0.42", mutated_sharpe="0.60")

        result = await _merge_mutation(db, mutation, _MONDAY)

        assert mutation.status == "merged"
        assert mutation.outcome == "merged"
        assert mutation.shadow_end_date == _MONDAY
        assert mutation.outcome_reason is not None
        assert "Sharpe improved" in mutation.outcome_reason
        assert result["outcome"] == "merged"
        assert result["original_sharpe"] == "0.42"
        assert result["mutated_sharpe"] == "0.60"
        db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_revert_mutation_updates_fields(self) -> None:
        """_revert_mutation sets status=reverted, outcome, shadow_end_date, outcome_reason."""
        db = AsyncMock()
        db.flush = AsyncMock()

        mutation = _make_mutation(original_sharpe="0.60", mutated_sharpe="0.35")

        result = await _revert_mutation(db, mutation, _FRIDAY)

        assert mutation.status == "reverted"
        assert mutation.outcome == "reverted"
        assert mutation.shadow_end_date == _FRIDAY
        assert mutation.outcome_reason is not None
        assert "Sharpe degraded" in mutation.outcome_reason
        assert result["outcome"] == "reverted"
        assert result["original_sharpe"] == "0.60"
        assert result["mutated_sharpe"] == "0.35"
        db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_merge_result_has_all_required_fields(self) -> None:
        """Merge result dict contains mutation_id, agent_id, version, outcome, Sharpe values."""
        db = AsyncMock()
        db.flush = AsyncMock()
        mutation = _make_mutation(mutation_id=42, version=3, agent_id="sector-analyst")
        mutation.mutated_sharpe = Decimal("0.70")
        mutation.original_sharpe = Decimal("0.45")

        result = await _merge_mutation(db, mutation, _MONDAY)

        assert result["mutation_id"] == 42
        assert result["agent_id"] == "sector-analyst"
        assert result["version"] == 3
        assert "original_sharpe" in result
        assert "mutated_sharpe" in result

    @pytest.mark.asyncio
    async def test_sharpe_values_are_strings_in_result(self) -> None:
        """Sharpe values in result dict must be strings (JSON-serializable)."""
        db = AsyncMock()
        db.flush = AsyncMock()
        mutation = _make_mutation(original_sharpe="0.42", mutated_sharpe="0.60")

        result = await _merge_mutation(db, mutation, _MONDAY)

        assert isinstance(result["original_sharpe"], str)
        assert isinstance(result["mutated_sharpe"], str)


# ---------------------------------------------------------------------------
# 8. Full merge path — integration-style
# ---------------------------------------------------------------------------


class TestFullMergePath:
    @pytest.mark.asyncio
    async def test_full_merge_path(self) -> None:
        """Full path: weight < 0.5 → start mutation → shadow → Sharpe improves → merge.

        This test drives the complete lifecycle across two cycle calls:
        - Cycle 1 (Monday): Start mutation (no active shadow, weight < 0.5)
        - Cycle 2 (Friday): Shadow period elapsed, Sharpe improved → merge
        """
        agent_id = "rs-analyzer"
        start_date = _MONDAY
        end_date = _MONDAY + timedelta(days=4)  # Friday (5 trading days incl.)

        # ---- Cycle 1: Start mutation ----
        db1 = AsyncMock()
        db1.flush = AsyncMock()
        db1.add = MagicMock()

        # Lock: acquired
        lock_row1 = MagicMock()
        lock_row1.__getitem__ = MagicMock(return_value=True)
        lock_result1 = MagicMock()
        lock_result1.fetchone.return_value = lock_row1

        # get_agent_weight → weight < 0.5
        weight_obj = _make_weight(agent_id=agent_id, weight="0.40", rolling_accuracy="0.40")
        weight_result1 = MagicMock()
        weight_result1.scalar_one_or_none.return_value = weight_obj

        # _get_active_shadow_mutation → None (no active mutation)
        no_shadow1 = MagicMock()
        no_shadow1.scalar_one_or_none.return_value = None

        # _check_mutation_eligible sub-calls:
        # _get_active_shadow_mutation → None (same as above, but called again inside eligible check)
        no_shadow2 = MagicMock()
        no_shadow2.scalar_one_or_none.return_value = None

        # _count_mutations_this_month → 0
        month_count = MagicMock()
        month_count.scalar.return_value = 0

        # _count_active_shadow_experiments → 0
        global_count = MagicMock()
        global_count.scalar.return_value = 0

        # _get_next_version → 0 (so next = 1)
        version_result = MagicMock()
        version_result.scalar.return_value = 0

        db1.execute = AsyncMock(
            side_effect=[
                lock_result1,
                weight_result1,
                no_shadow1,  # _get_active_shadow_mutation in main cycle
                no_shadow2,  # _get_active_shadow_mutation inside _check_mutation_eligible
                month_count,
                global_count,
                version_result,  # _get_next_version
            ]
        )

        result1 = await run_mutation_cycle(
            db1, data_as_of=start_date, candidate_agent_ids=[agent_id]
        )

        assert result1["status"] == "ok"
        assert len(result1["started"]) == 1
        assert result1["started"][0]["agent_id"] == agent_id
        assert result1["started"][0]["version"] == 1
        assert len(result1["evaluated"]) == 0

        # ---- Cycle 2: Evaluate shadow → merge ----
        db2 = AsyncMock()
        db2.flush = AsyncMock()
        db2.add = MagicMock()

        # Lock: acquired
        lock_row2 = MagicMock()
        lock_row2.__getitem__ = MagicMock(return_value=True)
        lock_result2 = MagicMock()
        lock_result2.fetchone.return_value = lock_row2

        # get_agent_weight → now higher rolling_accuracy (simulated improvement)
        weight_obj2 = _make_weight(agent_id=agent_id, weight="0.40", rolling_accuracy="0.65")
        weight_result2 = MagicMock()
        weight_result2.scalar_one_or_none.return_value = weight_obj2

        # _get_active_shadow_mutation → the mutation started in cycle 1
        active_mutation = _make_mutation(
            agent_id=agent_id,
            version=1,
            status="shadow",
            shadow_start_date=start_date,
            original_sharpe="0.40",
        )
        shadow_result2 = MagicMock()
        shadow_result2.scalar_one_or_none.return_value = active_mutation

        db2.execute = AsyncMock(
            side_effect=[
                lock_result2,
                weight_result2,
                shadow_result2,  # _get_active_shadow_mutation
            ]
        )

        result2 = await run_mutation_cycle(db2, data_as_of=end_date, candidate_agent_ids=[agent_id])

        assert result2["status"] == "ok"
        assert len(result2["evaluated"]) == 1
        assert result2["evaluated"][0]["outcome"] == "merged"
        assert result2["evaluated"][0]["agent_id"] == agent_id
        # Mutation record should be updated
        assert active_mutation.status == "merged"
        assert active_mutation.shadow_end_date == end_date


# ---------------------------------------------------------------------------
# 9. Full revert path — integration-style
# ---------------------------------------------------------------------------


class TestFullRevertPath:
    @pytest.mark.asyncio
    async def test_full_revert_path(self) -> None:
        """Full path: weight < 0.5 → start mutation → shadow → Sharpe degrades → revert."""
        agent_id = "sector-analyst"
        start_date = _MONDAY
        end_date = _MONDAY + timedelta(days=4)  # Friday

        # Only test the evaluation half — starting was tested above
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        # Lock: acquired
        lock_row = MagicMock()
        lock_row.__getitem__ = MagicMock(return_value=True)
        lock_result = MagicMock()
        lock_result.fetchone.return_value = lock_row

        # get_agent_weight → rolling_accuracy degraded vs original
        weight_obj = _make_weight(agent_id=agent_id, weight="0.40", rolling_accuracy="0.30")
        weight_result = MagicMock()
        weight_result.scalar_one_or_none.return_value = weight_obj

        # Active shadow mutation with higher original_sharpe
        active_mutation = _make_mutation(
            agent_id=agent_id,
            version=2,
            status="shadow",
            shadow_start_date=start_date,
            original_sharpe="0.60",  # was 0.60, now 0.30 → degraded
        )
        shadow_result = MagicMock()
        shadow_result.scalar_one_or_none.return_value = active_mutation

        db.execute = AsyncMock(side_effect=[lock_result, weight_result, shadow_result])

        result = await run_mutation_cycle(db, data_as_of=end_date, candidate_agent_ids=[agent_id])

        assert result["status"] == "ok"
        assert len(result["evaluated"]) == 1
        assert result["evaluated"][0]["outcome"] == "reverted"
        assert active_mutation.status == "reverted"
        assert active_mutation.shadow_end_date == end_date
        assert active_mutation.outcome_reason is not None
        assert "Sharpe degraded" in active_mutation.outcome_reason

    @pytest.mark.asyncio
    async def test_revert_when_current_sharpe_null(self) -> None:
        """Mutation is reverted when current rolling_accuracy is NULL (safe default)."""
        agent_id = "goldilocks-analyst"
        start_date = _MONDAY
        end_date = _MONDAY + timedelta(days=4)

        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        lock_row = MagicMock()
        lock_row.__getitem__ = MagicMock(return_value=True)
        lock_result = MagicMock()
        lock_result.fetchone.return_value = lock_row

        weight_obj = _make_weight(agent_id=agent_id, weight="0.40", rolling_accuracy=None)
        weight_result = MagicMock()
        weight_result.scalar_one_or_none.return_value = weight_obj

        active_mutation = _make_mutation(
            agent_id=agent_id,
            shadow_start_date=start_date,
            original_sharpe="0.55",
        )
        shadow_result = MagicMock()
        shadow_result.scalar_one_or_none.return_value = active_mutation

        db.execute = AsyncMock(side_effect=[lock_result, weight_result, shadow_result])

        result = await run_mutation_cycle(db, data_as_of=end_date, candidate_agent_ids=[agent_id])

        assert len(result["evaluated"]) == 1
        assert result["evaluated"][0]["outcome"] == "reverted"


# ---------------------------------------------------------------------------
# 10. No-op when weight is above threshold
# ---------------------------------------------------------------------------


class TestNoOpAboveThreshold:
    @pytest.mark.asyncio
    async def test_no_mutation_when_weight_above_threshold(self) -> None:
        """Cycle does nothing if all agents have weight >= 0.5."""
        agent_id = "rs-analyzer"
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        lock_row = MagicMock()
        lock_row.__getitem__ = MagicMock(return_value=True)
        lock_result = MagicMock()
        lock_result.fetchone.return_value = lock_row

        weight_obj = _make_weight(agent_id=agent_id, weight="1.20", rolling_accuracy="0.75")
        weight_result = MagicMock()
        weight_result.scalar_one_or_none.return_value = weight_obj

        no_shadow = MagicMock()
        no_shadow.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[lock_result, weight_result, no_shadow])

        result = await run_mutation_cycle(db, data_as_of=_MONDAY, candidate_agent_ids=[agent_id])

        assert result["status"] == "ok"
        assert result["started"] == []
        assert result["evaluated"] == []

    @pytest.mark.asyncio
    async def test_shadow_pending_does_not_start_new_mutation(self) -> None:
        """When a shadow mutation is still pending, no new mutation is started."""
        agent_id = "regime-analyst"
        db = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()

        lock_row = MagicMock()
        lock_row.__getitem__ = MagicMock(return_value=True)
        lock_result = MagicMock()
        lock_result.fetchone.return_value = lock_row

        weight_obj = _make_weight(agent_id=agent_id, weight="0.35", rolling_accuracy="0.50")
        weight_result = MagicMock()
        weight_result.scalar_one_or_none.return_value = weight_obj

        # Shadow mutation started yesterday — only 1 trading day, not 5 yet
        yesterday = _MONDAY - timedelta(days=1)  # Sunday (0 trading days from Mon)
        active_mutation = _make_mutation(
            agent_id=agent_id,
            shadow_start_date=yesterday,
            original_sharpe="0.40",
        )
        shadow_result = MagicMock()
        shadow_result.scalar_one_or_none.return_value = active_mutation

        db.execute = AsyncMock(side_effect=[lock_result, weight_result, shadow_result])

        result = await run_mutation_cycle(db, data_as_of=_MONDAY, candidate_agent_ids=[agent_id])

        assert result["status"] == "ok"
        assert result["started"] == []
        assert result["evaluated"] == []  # still pending

    def test_mutation_trigger_weight_constant(self) -> None:
        """MUTATION_TRIGGER_WEIGHT must be Decimal("0.5")."""
        assert MUTATION_TRIGGER_WEIGHT == Decimal("0.5")
        assert isinstance(MUTATION_TRIGGER_WEIGHT, Decimal)

    def test_shadow_trading_days_constant(self) -> None:
        """SHADOW_TRADING_DAYS must be 5."""
        assert SHADOW_TRADING_DAYS == 5

    def test_max_mutations_per_month_constant(self) -> None:
        """MAX_MUTATIONS_PER_MONTH must be 3."""
        assert MAX_MUTATIONS_PER_MONTH == 3
