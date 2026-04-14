"""Tests for the auto-loop re-run service logic.

Verifies:
- All is_auto_loop=True simulations are re-run
- Soft-deleted simulations are skipped
- Per-simulation failure does not abort others
- last_auto_run is updated after each successful re-run
- Lock acquisition failure → skipped (not error)
- All financial values remain Decimal throughout
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.simulation import (
    AutoLoopResultItem,
    SimulationSummary,
    SimulationResult,
    TaxSummary,
)
from backend.services.simulation.service import SimulationService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_CONFIG_DICT: dict[str, Any] = {
    "signal": "breadth",
    "instrument": "TEST-FUND",
    "instrument_type": "mf",
    "parameters": {
        "sip_amount": "10000",
        "lumpsum_amount": "50000",
        "buy_level": "60",
        "sell_level": "40",
        "reentry_level": None,
        "sell_pct": "100",
        "redeploy_pct": "100",
        "cooldown_days": 30,
    },
    "start_date": "2022-01-01",
    "end_date": "2023-12-31",
    "combined_config": None,
}

_PREV_SUMMARY_DICT: dict[str, Any] = {
    "total_invested": "120000",
    "final_value": "130000",
    "xirr": "0.10",
    "cagr": "0.09",
    "vs_plain_sip": "0.01",
    "vs_benchmark": "0.00",
    "alpha": "0.00",
    "max_drawdown": "-0.10",
    "sharpe": "1.0",
    "sortino": "1.1",
}


def _make_sim_orm(
    sim_id: uuid.UUID | None = None,
    is_auto_loop: bool = True,
    is_deleted: bool = False,
    config: dict[str, Any] | None = None,
    result_summary: dict[str, Any] | None = None,
) -> MagicMock:
    sim = MagicMock()
    sim.id = sim_id or uuid.uuid4()
    sim.name = "Auto Loop Sim"
    sim.config = config or _SAMPLE_CONFIG_DICT
    sim.result_summary = result_summary or _PREV_SUMMARY_DICT
    sim.daily_values = []
    sim.transactions = []
    sim.tax_summary = {
        "stcg": "0",
        "ltcg": "0",
        "total_tax": "0",
        "post_tax_xirr": "0.10",
        "unrealized": "0",
    }
    sim.is_auto_loop = is_auto_loop
    sim.is_deleted = is_deleted
    sim.auto_loop_cron = "0 6 * * 1"
    sim.last_auto_run = None
    sim.created_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    return sim


def _make_simulation_result(xirr: str = "0.15") -> SimulationResult:
    """Build a minimal SimulationResult with Decimal-typed fields."""
    summary = SimulationSummary(
        total_invested=Decimal("120000"),
        final_value=Decimal("140000"),
        xirr=Decimal(xirr),
        cagr=Decimal("0.14"),
        vs_plain_sip=Decimal("0.02"),
        vs_benchmark=Decimal("0.01"),
        alpha=Decimal("0.01"),
        max_drawdown=Decimal("-0.12"),
        sharpe=Decimal("1.2"),
        sortino=Decimal("1.5"),
    )
    tax = TaxSummary(
        stcg=Decimal("0"),
        ltcg=Decimal("5000"),
        total_tax=Decimal("750"),
        post_tax_xirr=Decimal("0.13"),
        unrealized=Decimal("15000"),
    )
    return SimulationResult(
        summary=summary,
        daily_values=[],
        transactions=[],
        tax_summary=tax,
        tear_sheet_url=None,
        data_as_of=datetime.datetime.now(tz=datetime.timezone.utc),
    )


def _make_mock_session() -> AsyncMock:
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock(return_value=None)
    mock_session.add = MagicMock()
    return mock_session


# ---------------------------------------------------------------------------
# run_auto_loop tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_loop_reruns_all_active_auto_loop_sims() -> None:
    """run_auto_loop re-runs all is_auto_loop=True simulations."""
    sim1 = _make_sim_orm(is_auto_loop=True)
    sim2 = _make_sim_orm(is_auto_loop=True)

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)

    service._repo = MagicMock()
    service._repo.list_simulations = AsyncMock(return_value=[sim1, sim2])
    service._repo.lock_for_update = AsyncMock(side_effect=[sim1, sim2])

    mock_result = _make_simulation_result()
    service.run_backtest = AsyncMock(return_value=mock_result)

    mock_jip = MagicMock()
    results = await service.run_auto_loop(jip=mock_jip)

    assert len(results) == 2
    assert all(r.status == "success" for r in results)
    assert service.run_backtest.await_count == 2


@pytest.mark.asyncio
async def test_auto_loop_skips_soft_deleted_sims() -> None:
    """run_auto_loop skips sims with is_deleted=True."""
    active_sim = _make_sim_orm(is_auto_loop=True, is_deleted=False)
    deleted_sim = _make_sim_orm(is_auto_loop=True, is_deleted=True)

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)

    # list_simulations repo already excludes soft-deleted, but service also filters
    # The repo mock here returns both, and service should filter is_deleted
    service._repo = MagicMock()
    service._repo.list_simulations = AsyncMock(return_value=[active_sim, deleted_sim])
    service._repo.lock_for_update = AsyncMock(return_value=active_sim)

    mock_result = _make_simulation_result()
    service.run_backtest = AsyncMock(return_value=mock_result)

    mock_jip = MagicMock()
    results = await service.run_auto_loop(jip=mock_jip)

    # Only 1 result — deleted sim was filtered out before lock attempt
    assert len(results) == 1
    assert results[0].simulation_id == active_sim.id
    assert service.run_backtest.await_count == 1


@pytest.mark.asyncio
async def test_auto_loop_skips_non_auto_loop_sims() -> None:
    """run_auto_loop skips sims with is_auto_loop=False."""
    normal_sim = _make_sim_orm(is_auto_loop=False)
    auto_sim = _make_sim_orm(is_auto_loop=True)

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)

    service._repo = MagicMock()
    service._repo.list_simulations = AsyncMock(return_value=[normal_sim, auto_sim])
    service._repo.lock_for_update = AsyncMock(return_value=auto_sim)

    mock_result = _make_simulation_result()
    service.run_backtest = AsyncMock(return_value=mock_result)

    mock_jip = MagicMock()
    results = await service.run_auto_loop(jip=mock_jip)

    assert len(results) == 1
    assert results[0].simulation_id == auto_sim.id


@pytest.mark.asyncio
async def test_auto_loop_handles_per_sim_failure_gracefully() -> None:
    """A failure on one sim produces error status but does not stop others."""
    sim1 = _make_sim_orm(is_auto_loop=True)
    sim2 = _make_sim_orm(is_auto_loop=True)

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)

    service._repo = MagicMock()
    service._repo.list_simulations = AsyncMock(return_value=[sim1, sim2])
    service._repo.lock_for_update = AsyncMock(side_effect=[sim1, sim2])

    mock_result = _make_simulation_result()

    call_count = 0

    async def maybe_fail(*args: Any, **kwargs: Any) -> SimulationResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("Simulated data fetch failure")
        return mock_result

    service.run_backtest = maybe_fail  # type: ignore[method-assign]

    mock_jip = MagicMock()
    results = await service.run_auto_loop(jip=mock_jip)

    assert len(results) == 2
    statuses = {r.status for r in results}
    assert "error" in statuses
    assert "success" in statuses

    # Error result should include error message
    error_results = [r for r in results if r.status == "error"]
    assert len(error_results) == 1
    assert error_results[0].error is not None
    assert "Simulated data fetch failure" in error_results[0].error


@pytest.mark.asyncio
async def test_auto_loop_skips_when_lock_fails() -> None:
    """When lock_for_update returns None, sim is marked as skipped."""
    sim1 = _make_sim_orm(is_auto_loop=True)

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)

    service._repo = MagicMock()
    service._repo.list_simulations = AsyncMock(return_value=[sim1])
    service._repo.lock_for_update = AsyncMock(return_value=None)  # lock fails

    service.run_backtest = AsyncMock()

    mock_jip = MagicMock()
    results = await service.run_auto_loop(jip=mock_jip)

    assert len(results) == 1
    assert results[0].status == "skipped"
    service.run_backtest.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_loop_updates_last_auto_run() -> None:
    """After a successful re-run, last_auto_run is set on the locked ORM row."""
    sim1 = _make_sim_orm(is_auto_loop=True)
    assert sim1.last_auto_run is None

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)

    service._repo = MagicMock()
    service._repo.list_simulations = AsyncMock(return_value=[sim1])
    service._repo.lock_for_update = AsyncMock(return_value=sim1)

    mock_result = _make_simulation_result()
    service.run_backtest = AsyncMock(return_value=mock_result)

    mock_jip = MagicMock()
    await service.run_auto_loop(jip=mock_jip)

    # last_auto_run should have been set
    assert sim1.last_auto_run is not None
    assert isinstance(sim1.last_auto_run, datetime.datetime)
    assert sim1.last_auto_run.tzinfo is not None


@pytest.mark.asyncio
async def test_auto_loop_computes_summary_delta() -> None:
    """run_auto_loop populates summary_delta with Decimal-as-str differences."""
    sim1 = _make_sim_orm(
        is_auto_loop=True,
        result_summary={
            "total_invested": "120000",
            "final_value": "130000",
            "xirr": "0.10",
            "cagr": "0.09",
            "vs_plain_sip": "0.01",
            "vs_benchmark": "0.00",
            "alpha": "0.00",
            "max_drawdown": "-0.10",
            "sharpe": "1.0",
            "sortino": "1.1",
        },
    )

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)

    service._repo = MagicMock()
    service._repo.list_simulations = AsyncMock(return_value=[sim1])
    service._repo.lock_for_update = AsyncMock(return_value=sim1)

    # New run with higher XIRR
    mock_result = _make_simulation_result(xirr="0.15")
    service.run_backtest = AsyncMock(return_value=mock_result)

    mock_jip = MagicMock()
    results = await service.run_auto_loop(jip=mock_jip)

    assert len(results) == 1
    assert results[0].status == "success"
    assert results[0].summary_delta is not None
    # XIRR delta should be 0.15 - 0.10 = 0.05
    assert "xirr" in results[0].summary_delta
    xirr_delta = Decimal(results[0].summary_delta["xirr"])
    assert abs(xirr_delta - Decimal("0.05")) < Decimal("0.001")


@pytest.mark.asyncio
async def test_auto_loop_returns_zero_results_when_none_configured() -> None:
    """run_auto_loop returns empty list when no is_auto_loop sims exist."""
    mock_session = _make_mock_session()
    service = SimulationService(mock_session)

    service._repo = MagicMock()
    service._repo.list_simulations = AsyncMock(return_value=[])
    service.run_backtest = AsyncMock()

    mock_jip = MagicMock()
    results = await service.run_auto_loop(jip=mock_jip)

    assert results == []
    service.run_backtest.assert_not_awaited()


# ---------------------------------------------------------------------------
# POST /auto-loop/run route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_loop_run_route_returns_auto_loop_response() -> None:
    """POST /auto-loop/run returns AutoLoopResponse shape."""
    from fastapi.testclient import TestClient

    from backend.db.session import get_db
    from backend.main import app

    mock_session = _make_mock_session()

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_session

    item = AutoLoopResultItem(
        simulation_id=uuid.uuid4(),
        status="success",
        summary_delta={"xirr": "0.05"},
    )

    mock_service = MagicMock()
    mock_service.run_auto_loop = AsyncMock(return_value=[item])

    with patch("backend.routes.simulate.SimulationService", return_value=mock_service):
        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=True)
            response = client.post("/api/v1/simulate/auto-loop/run")
        finally:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "total" in data
    assert "succeeded" in data
    assert "failed" in data
    assert "ran_at" in data
    assert data["total"] == 1
    assert data["succeeded"] == 1
    assert data["failed"] == 0
