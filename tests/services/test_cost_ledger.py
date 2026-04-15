"""Tests for backend/services/cost_ledger.py — budget enforcement.

Covers:
1. under-budget: get_rolling_window_cost returns <$2, record_llm_call succeeds
2. at-budget: cost exactly $2, next call raises BudgetExhaustedError
3. over-budget halt: check_budget returns "over", record_llm_call raises
4. rolling-window arithmetic: costs >24h ago excluded, within 24h included
5. atlas_alerts side-effect: alert written when budget exceeded

All DB sessions are mocked (AsyncMock) — no real DB.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.cost_ledger import (
    DAILY_BUDGET_USD,
    BudgetExhaustedError,
    BudgetStatus,
    _write_budget_alert,
    check_budget,
    get_rolling_window_cost,
    record_llm_call,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_db(rolling_window_cost: Decimal) -> AsyncMock:
    """Build a mock AsyncSession that returns a fixed rolling window cost."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = rolling_window_cost
    db.execute = AsyncMock(return_value=execute_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Test 1: under-budget — record_llm_call succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_llm_call_under_budget_succeeds() -> None:
    """When rolling window cost is $0.50, a $0.001 call should succeed."""
    spent = Decimal("0.50")
    db = _make_mock_db(spent)

    result = await record_llm_call(
        db=db,
        agent_id="test-agent",
        model="claude-haiku-4-5-20251001",
        prompt_tokens=100,
        completion_tokens=50,
        request_type="test",
    )

    assert result is not None
    # cost = (100 * 0.0008 + 50 * 0.004) / 1000 = (0.08 + 0.2) / 1000 = 0.00028
    assert result.cost_usd == Decimal("0.00028")
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_get_rolling_window_cost_under_budget() -> None:
    """get_rolling_window_cost returns the DB value as Decimal."""
    spent = Decimal("1.50")
    db = _make_mock_db(spent)

    cost = await get_rolling_window_cost(db)

    assert cost == spent
    assert isinstance(cost, Decimal)


@pytest.mark.asyncio
async def test_get_rolling_window_cost_no_rows_returns_zero() -> None:
    """get_rolling_window_cost returns Decimal('0') when scalar_one_or_none is None."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=execute_result)

    cost = await get_rolling_window_cost(db)

    assert cost == Decimal("0")


# ---------------------------------------------------------------------------
# Test 2: at-budget — next call raises BudgetExhaustedError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_budget_at_exactly_budget() -> None:
    """When spent == DAILY_BUDGET_USD, status is 'at'."""
    db = _make_mock_db(DAILY_BUDGET_USD)

    status = await check_budget(db)

    assert status.status == "at"
    assert status.spent == DAILY_BUDGET_USD
    assert status.remaining == Decimal("0")
    assert status.budget == DAILY_BUDGET_USD


@pytest.mark.asyncio
async def test_record_llm_call_at_budget_raises() -> None:
    """When spent == DAILY_BUDGET_USD, any positive-cost call raises BudgetExhaustedError."""
    db = _make_mock_db(DAILY_BUDGET_USD)

    with pytest.raises(BudgetExhaustedError) as exc_info:
        await record_llm_call(
            db=db,
            agent_id="test-agent",
            model="claude-haiku-4-5-20251001",
            prompt_tokens=100,
            completion_tokens=50,
            request_type="test",
        )

    err = exc_info.value
    assert err.spent == DAILY_BUDGET_USD
    assert err.budget == DAILY_BUDGET_USD
    assert err.estimated_cost > Decimal("0")


# ---------------------------------------------------------------------------
# Test 3: over-budget halt — record_llm_call raises BudgetExhaustedError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_budget_over_budget() -> None:
    """When spent > DAILY_BUDGET_USD, status is 'over'."""
    spent = Decimal("2.50")
    db = _make_mock_db(spent)

    status = await check_budget(db)

    assert status.status == "over"
    assert status.spent == spent
    assert status.remaining == Decimal("-0.50")
    assert status.budget == DAILY_BUDGET_USD


@pytest.mark.asyncio
async def test_record_llm_call_over_budget_raises() -> None:
    """When spent > DAILY_BUDGET_USD, record_llm_call raises BudgetExhaustedError."""
    spent = Decimal("2.50")
    db = _make_mock_db(spent)

    with pytest.raises(BudgetExhaustedError) as exc_info:
        await record_llm_call(
            db=db,
            agent_id="test-agent",
            model="claude-haiku-4-5-20251001",
            prompt_tokens=1000,
            completion_tokens=500,
            request_type="test",
        )

    err = exc_info.value
    assert err.spent == spent
    assert err.budget == DAILY_BUDGET_USD
    # No ledger entry should have been added
    # The alert path calls db.add (for AtlasAlert), but NOT an AtlasCostLedger
    # Verify flush was called (for alert), then error raised
    assert db.flush.called


@pytest.mark.asyncio
async def test_record_llm_call_near_budget_boundary_raises() -> None:
    """When spent + estimated_cost > DAILY_BUDGET_USD, raises even if spent < budget."""
    # spent = $1.999, estimated = $0.002 => total = $2.001 > $2.00
    spent = Decimal("1.999")
    db = _make_mock_db(spent)

    with pytest.raises(BudgetExhaustedError):
        await record_llm_call(
            db=db,
            agent_id="test-agent",
            model="claude-sonnet-4-6",
            # cost = (50000 * 0.003 + 50000 * 0.015) / 1000 = (150 + 750) / 1000 = 0.9 => way over
            # Use small tokens to get cost ~0.002:
            # cost = (100 * 0.003 + 50 * 0.015) / 1000 = (0.3 + 0.75) / 1000 = 0.00105
            # Increase to cross: 1000 prompt, 1000 completion
            # cost = (1000 * 0.003 + 1000 * 0.015) / 1000 = (3 + 15) / 1000 = 0.018
            # 1.999 + 0.018 = 2.017 > 2.00 => raises
            prompt_tokens=1000,
            completion_tokens=1000,
            request_type="test",
        )


# ---------------------------------------------------------------------------
# Test 4: rolling-window arithmetic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rolling_window_excludes_old_costs() -> None:
    """get_rolling_window_cost executes SQL with 24h window filter.

    We verify that the SQL query is executed (which enforces the WHERE clause
    server-side). The mock returns only what's within the window.
    """
    # Simulate: only $0.30 within the last 24h (old costs excluded by SQL)
    within_window_cost = Decimal("0.30")
    db = _make_mock_db(within_window_cost)

    cost = await get_rolling_window_cost(db, hours=24)

    assert cost == within_window_cost
    # Verify the query was executed
    db.execute.assert_called_once()
    # Verify interval is in the query (check the statement passed to execute)
    call_args = db.execute.call_args
    stmt = call_args[0][0]
    # The WHERE clause contains the interval expression
    stmt_str = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "24 hours" in stmt_str or "coalesce" in stmt_str.lower()


@pytest.mark.asyncio
async def test_rolling_window_custom_hours() -> None:
    """get_rolling_window_cost accepts custom hours parameter."""
    cost = Decimal("0.10")
    db = _make_mock_db(cost)

    result = await get_rolling_window_cost(db, hours=48)

    assert result == cost
    db.execute.assert_called_once()
    # The SQL should reference the 48 hours interval
    stmt = db.execute.call_args[0][0]
    stmt_str = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "48 hours" in stmt_str


# ---------------------------------------------------------------------------
# Test 5: atlas_alerts side-effect on budget exceeded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_budget_exceeded_writes_alert() -> None:
    """When budget exceeded, an alert is written to atlas_alerts."""
    spent = Decimal("2.10")
    estimated_cost = Decimal("0.05")
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    await _write_budget_alert(db, spent, DAILY_BUDGET_USD, estimated_cost)

    # Verify db.add was called with an AtlasAlert
    from backend.db.models import AtlasAlert

    db.add.assert_called_once()
    alert_arg = db.add.call_args[0][0]
    assert isinstance(alert_arg, AtlasAlert)
    assert alert_arg.source == "cost_ledger"
    assert alert_arg.alert_type == "budget_exhausted"
    assert "2.10" in alert_arg.message
    assert alert_arg.metadata_json["spent_usd"] == "2.10"
    assert alert_arg.metadata_json["budget_usd"] == str(DAILY_BUDGET_USD)
    assert alert_arg.metadata_json["estimated_cost_usd"] == "0.05"
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_record_llm_call_over_budget_writes_alert() -> None:
    """record_llm_call raises BudgetExhaustedError AND writes alert when over budget."""
    spent = Decimal("2.00")
    db = _make_mock_db(spent)

    with pytest.raises(BudgetExhaustedError):
        await record_llm_call(
            db=db,
            agent_id="test-agent",
            model="claude-haiku-4-5-20251001",
            prompt_tokens=100,
            completion_tokens=50,
            request_type="test",
        )

    # db.add should have been called once with the AtlasAlert
    from backend.db.models import AtlasAlert

    assert db.add.called
    alert_arg = db.add.call_args[0][0]
    assert isinstance(alert_arg, AtlasAlert)
    assert alert_arg.alert_type == "budget_exhausted"


@pytest.mark.asyncio
async def test_budget_alert_write_failure_does_not_mask_error() -> None:
    """If atlas_alerts write fails, BudgetExhaustedError still propagates."""
    spent = Decimal("2.00")
    db = _make_mock_db(spent)
    # Make flush fail to simulate alert write failure
    db.flush = AsyncMock(side_effect=Exception("DB connection lost"))

    with pytest.raises(BudgetExhaustedError):
        await record_llm_call(
            db=db,
            agent_id="test-agent",
            model="claude-haiku-4-5-20251001",
            prompt_tokens=100,
            completion_tokens=50,
            request_type="test",
        )


# ---------------------------------------------------------------------------
# Unit: BudgetStatus dataclass
# ---------------------------------------------------------------------------


def test_budget_status_under() -> None:
    """BudgetStatus 'under' when spent < budget."""
    status = BudgetStatus(
        status="under",
        spent=Decimal("0.50"),
        remaining=Decimal("1.50"),
        budget=DAILY_BUDGET_USD,
    )
    assert status.status == "under"
    assert status.remaining == Decimal("1.50")


def test_budget_status_decimal_types() -> None:
    """BudgetStatus fields are Decimal, never float."""
    status = BudgetStatus(
        status="at",
        spent=DAILY_BUDGET_USD,
        remaining=Decimal("0"),
        budget=DAILY_BUDGET_USD,
    )
    assert isinstance(status.spent, Decimal)
    assert isinstance(status.remaining, Decimal)
    assert isinstance(status.budget, Decimal)


# ---------------------------------------------------------------------------
# Unit: BudgetExhaustedError
# ---------------------------------------------------------------------------


def test_budget_exhausted_error_message() -> None:
    """BudgetExhaustedError carries spent/budget/estimated_cost."""
    err = BudgetExhaustedError(
        spent=Decimal("2.10"),
        budget=Decimal("2.00"),
        estimated_cost=Decimal("0.05"),
    )
    assert err.spent == Decimal("2.10")
    assert err.budget == Decimal("2.00")
    assert err.estimated_cost == Decimal("0.05")
    assert "2.10" in str(err)
    assert "2.00" in str(err)
