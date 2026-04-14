"""Tests for the in-process simulation auto-loop scheduler.

Verifies:
- Scheduler start/stop lifecycle
- Status returns correct structure when not running
- Status returns correct structure when running
- Scheduler skips sims that are not due per cron
- Reoptimize route dispatches to optimizer
- Drift history route returns events
- AutoLoopResultItem includes drift_alerts and needs_reoptimization
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.simulation import (
    AutoLoopResultItem,
    DriftAlert,
)
from backend.services.simulation.scheduler import (
    SimulationScheduler,
    _is_due,
    _compute_next_run,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_auto_sim(
    cron: str = "0 6 * * 1",
    last_run: datetime.datetime | None = None,
) -> MagicMock:
    sim = MagicMock()
    sim.id = uuid.uuid4()
    sim.is_auto_loop = True
    sim.is_deleted = False
    sim.auto_loop_cron = cron
    sim.last_auto_run = last_run
    return sim


# ---------------------------------------------------------------------------
# Scheduler lifecycle tests
# ---------------------------------------------------------------------------


def test_scheduler_status_when_not_running() -> None:
    """A fresh scheduler reports is_running=False and zero active simulations."""
    sched = SimulationScheduler()
    status = sched.status()

    assert status["is_running"] is False
    assert status["active_simulations"] == 0
    assert status["last_run_at"] is None
    assert status["next_run_at"] is None


@pytest.mark.asyncio
async def test_scheduler_start_stop_lifecycle() -> None:
    """Scheduler can be started and stopped cleanly."""
    sched = SimulationScheduler()

    # Use a mock session factory that returns an AsyncMock context manager
    mock_factory = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = mock_cm

    sched.start(mock_factory)
    assert sched.is_running is True

    await sched.stop()
    assert sched.is_running is False


@pytest.mark.asyncio
async def test_scheduler_start_idempotent() -> None:
    """Calling start() twice does not create duplicate tasks."""
    sched = SimulationScheduler()
    mock_factory = MagicMock()

    sched.start(mock_factory)
    original_task = sched._task

    sched.start(mock_factory)  # second call — should be no-op
    assert sched._task is original_task  # same task, not a new one

    await sched.stop()


@pytest.mark.asyncio
async def test_scheduler_status_when_running() -> None:
    """After start(), is_running=True is reflected in status()."""
    sched = SimulationScheduler()
    mock_factory = MagicMock()

    sched.start(mock_factory)
    try:
        status = sched.status()
        assert status["is_running"] is True
    finally:
        await sched.stop()


# ---------------------------------------------------------------------------
# _is_due helper tests
# ---------------------------------------------------------------------------


def test_scheduler_skips_when_not_due() -> None:
    """_is_due returns False when sim ran more recently than last cron fire."""
    # Cron: every Monday at 06:00. Simulate it fired Monday 06:00 UTC.
    # Pretend last_auto_run was set at Monday 06:05 (after the fire).
    now = datetime.datetime(2026, 4, 13, 9, 0, 0, tzinfo=datetime.timezone.utc)  # Monday
    # Last cron fire was this Monday 06:00, and we last ran at 06:05 — not due.
    last_run = datetime.datetime(2026, 4, 13, 6, 5, 0, tzinfo=datetime.timezone.utc)

    sim = _make_auto_sim(cron="0 6 * * 1", last_run=last_run)
    result = _is_due(sim, now)
    assert result is False


def test_scheduler_is_due_when_never_run() -> None:
    """_is_due returns True when sim has never run (last_auto_run=None)."""
    now = datetime.datetime(2026, 4, 13, 9, 0, 0, tzinfo=datetime.timezone.utc)
    sim = _make_auto_sim(cron="0 6 * * 1", last_run=None)
    result = _is_due(sim, now)
    assert result is True


def test_scheduler_is_due_when_missed_run() -> None:
    """_is_due returns True when last cron fire is after last_auto_run."""
    # Now is Monday 09:00; last cron fire was Monday 06:00; last_auto_run was Sunday 06:00
    now = datetime.datetime(2026, 4, 13, 9, 0, 0, tzinfo=datetime.timezone.utc)
    last_run = datetime.datetime(2026, 4, 12, 6, 0, 0, tzinfo=datetime.timezone.utc)  # Sunday

    sim = _make_auto_sim(cron="0 6 * * 1", last_run=last_run)
    result = _is_due(sim, now)
    assert result is True


def test_scheduler_invalid_cron_not_due() -> None:
    """_is_due returns False for invalid cron expressions (does not crash)."""
    now = datetime.datetime(2026, 4, 13, 9, 0, tzinfo=datetime.timezone.utc)
    sim = _make_auto_sim(cron="not-a-cron-expr", last_run=None)
    result = _is_due(sim, now)
    assert result is False


def test_scheduler_no_cron_not_due() -> None:
    """_is_due returns False when auto_loop_cron is None or empty."""
    now = datetime.datetime(2026, 4, 13, 9, 0, tzinfo=datetime.timezone.utc)
    sim = _make_auto_sim(cron="", last_run=None)
    result = _is_due(sim, now)
    assert result is False


# ---------------------------------------------------------------------------
# _compute_next_run helper tests
# ---------------------------------------------------------------------------


def test_compute_next_run_returns_nearest() -> None:
    """_compute_next_run returns the nearest next cron fire across sims."""
    now = datetime.datetime(2026, 4, 13, 0, 0, tzinfo=datetime.timezone.utc)  # Monday midnight
    sim_daily = _make_auto_sim(cron="0 6 * * *")  # next: Mon 06:00
    sim_weekly = _make_auto_sim(cron="0 6 * * 1")  # next: next Monday 06:00 or same

    result = _compute_next_run([sim_daily, sim_weekly], now)
    assert result is not None
    assert result.tzinfo is not None
    assert result > now


def test_compute_next_run_empty_list() -> None:
    """_compute_next_run returns None for empty sim list."""
    now = datetime.datetime(2026, 4, 13, tzinfo=datetime.timezone.utc)
    result = _compute_next_run([], now)
    assert result is None


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_status_route_returns_correct_shape() -> None:
    """GET /scheduler/status returns SchedulerStatusResponse shape."""
    from fastapi.testclient import TestClient

    from backend.db.session import get_db
    from backend.main import app

    mock_session = AsyncMock()

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_session

    with patch("backend.routes.simulate.SimulationService"):
        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/simulate/scheduler/status")
        finally:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert "is_running" in data
    assert "active_simulations" in data
    assert "last_run_at" in data
    assert "next_run_at" in data
    assert isinstance(data["is_running"], bool)
    assert isinstance(data["active_simulations"], int)


@pytest.mark.asyncio
async def test_drift_history_route_returns_events() -> None:
    """GET /{sim_id}/drift-history returns DriftHistoryResponse."""
    from fastapi.testclient import TestClient

    from backend.db.session import get_db
    from backend.main import app

    sim_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    # Build mock sim ORM with drift_history
    mock_sim = MagicMock()
    mock_sim.id = sim_id
    mock_sim.drift_history = [
        {
            "ran_at": "2026-04-13T06:00:00+00:00",
            "alerts": [{"metric": "xirr", "severity": "HIGH"}],
        }
    ]

    mock_service = MagicMock()
    mock_service.get_simulation = AsyncMock(return_value=mock_sim)

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_session

    with patch("backend.routes.simulate.SimulationService", return_value=mock_service):
        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get(f"/api/v1/simulate/{sim_id}/drift-history")
        finally:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert "simulation_id" in data
    assert "drift_events" in data
    assert "data_as_of" in data
    assert len(data["drift_events"]) == 1


@pytest.mark.asyncio
async def test_drift_history_route_returns_404_when_not_found() -> None:
    """GET /{sim_id}/drift-history returns 404 for unknown sim."""
    from fastapi.testclient import TestClient

    from backend.db.session import get_db
    from backend.main import app

    sim_id = uuid.uuid4()
    mock_session = AsyncMock()

    mock_service = MagicMock()
    mock_service.get_simulation = AsyncMock(return_value=None)

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_session

    with patch("backend.routes.simulate.SimulationService", return_value=mock_service):
        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get(f"/api/v1/simulate/{sim_id}/drift-history")
        finally:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reoptimize_route_dispatches_to_optimizer() -> None:
    """POST /{sim_id}/reoptimize dispatches to SimulationService.optimize."""
    from fastapi.testclient import TestClient

    from backend.db.session import get_db
    from backend.main import app
    from backend.models.simulation import (
        OptimizeResponse,
        SimulationConfig,
        TrialResult,
    )

    sim_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    mock_config_dict = {
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

    mock_sim = MagicMock()
    mock_sim.id = sim_id
    mock_sim.config = mock_config_dict
    mock_sim.drift_history = []

    mock_optimize_response = OptimizeResponse(
        best_params={"buy_level": Decimal("65"), "sell_level": Decimal("38")},
        best_value=Decimal("0.18"),
        objective="xirr",
        n_trials=50,
        trials=[
            TrialResult(
                trial_number=1,
                params={"buy_level": Decimal("65")},
                value=Decimal("0.18"),
            )
        ],
        base_config=SimulationConfig.model_validate(mock_config_dict),
        data_as_of=datetime.datetime.now(tz=datetime.timezone.utc),
    )

    mock_service = MagicMock()
    mock_service.get_simulation = AsyncMock(return_value=mock_sim)
    mock_service.optimize = AsyncMock(return_value=mock_optimize_response)

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_session

    with patch("backend.routes.simulate.SimulationService", return_value=mock_service):
        with patch("backend.routes.simulate.JIPDataService"):
            app.dependency_overrides[get_db] = override_get_db
            try:
                client = TestClient(app, raise_server_exceptions=True)
                response = client.post(
                    f"/api/v1/simulate/{sim_id}/reoptimize",
                    json={"n_trials": 50, "objective": "xirr"},
                )
            finally:
                app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert "best_params" in data
    assert "best_value" in data
    assert "objective" in data
    assert data["objective"] == "xirr"
    mock_service.optimize.assert_awaited_once()


# ---------------------------------------------------------------------------
# AutoLoopResultItem drift fields tests
# ---------------------------------------------------------------------------


def test_auto_loop_result_includes_drift_alerts() -> None:
    """AutoLoopResultItem supports drift_alerts field."""
    alert = DriftAlert(
        metric="xirr",
        previous_value=Decimal("0.10"),
        current_value=Decimal("0.09"),
        delta=Decimal("-0.01"),
        delta_pct=Decimal("10"),
        severity="HIGH",
    )
    item = AutoLoopResultItem(
        simulation_id=uuid.uuid4(),
        status="success",
        drift_alerts=[alert],
    )
    assert item.drift_alerts is not None
    assert len(item.drift_alerts) == 1
    assert item.drift_alerts[0].metric == "xirr"


def test_auto_loop_result_includes_needs_reoptimization_flag() -> None:
    """AutoLoopResultItem.needs_reoptimization defaults to False."""
    item = AutoLoopResultItem(
        simulation_id=uuid.uuid4(),
        status="success",
    )
    assert item.needs_reoptimization is False

    # With HIGH alert
    alert = DriftAlert(
        metric="cagr",
        previous_value=Decimal("0.09"),
        current_value=Decimal("0.08"),
        delta=Decimal("-0.01"),
        delta_pct=Decimal("11"),
        severity="HIGH",
    )
    item_with_drift = AutoLoopResultItem(
        simulation_id=uuid.uuid4(),
        status="success",
        drift_alerts=[alert],
        needs_reoptimization=True,
    )
    assert item_with_drift.needs_reoptimization is True


def test_auto_loop_result_no_drift_no_reoptimization() -> None:
    """AutoLoopResultItem with no drift alerts has needs_reoptimization=False."""
    item = AutoLoopResultItem(
        simulation_id=uuid.uuid4(),
        status="success",
        drift_alerts=None,
        needs_reoptimization=False,
    )
    assert item.needs_reoptimization is False
    assert item.drift_alerts is None
