"""Tests for simulation listing, get-by-id, save, and delete endpoints.

Tests use AsyncMock for DB session (per AsyncMock Context Manager Pattern wiki article).
All financial values use Decimal — never float.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

_SAMPLE_SUMMARY_DICT: dict[str, Any] = {
    "total_invested": "120000",
    "final_value": "140000",
    "xirr": "0.15",
    "cagr": "0.14",
    "vs_plain_sip": "0.02",
    "vs_benchmark": "0.01",
    "alpha": "0.01",
    "max_drawdown": "-0.12",
    "sharpe": "1.2",
    "sortino": "1.5",
}

_SAMPLE_TAX_DICT: dict[str, Any] = {
    "stcg": "0",
    "ltcg": "5000",
    "total_tax": "750",
    "post_tax_xirr": "0.13",
    "unrealized": "15000",
}


def _make_sim_orm(
    sim_id: uuid.UUID | None = None,
    is_auto_loop: bool = False,
    is_deleted: bool = False,
    has_result: bool = True,
) -> MagicMock:
    """Create a mock AtlasSimulation ORM row."""
    sim = MagicMock()
    sim.id = sim_id or uuid.uuid4()
    sim.name = "Test Simulation"
    sim.config = _SAMPLE_CONFIG_DICT
    sim.result_summary = _SAMPLE_SUMMARY_DICT if has_result else None
    sim.daily_values = [] if has_result else None
    sim.transactions = [] if has_result else None
    sim.tax_summary = _SAMPLE_TAX_DICT if has_result else None
    sim.is_auto_loop = is_auto_loop
    sim.is_deleted = is_deleted
    sim.auto_loop_cron = "0 6 * * 1" if is_auto_loop else None
    sim.last_auto_run = None
    sim.created_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    sim.updated_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    sim.user_id = None
    return sim


def _make_mock_session() -> AsyncMock:
    """Build an AsyncMock session with flush() support."""
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock(return_value=None)
    mock_session.add = MagicMock()
    return mock_session


# ---------------------------------------------------------------------------
# list_simulations service method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_simulations_returns_all_active() -> None:
    """list_simulations returns ORM rows from repo."""
    sim1 = _make_sim_orm()
    sim2 = _make_sim_orm()

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)

    service._repo = MagicMock()
    service._repo.list_simulations = AsyncMock(return_value=[sim1, sim2])

    result = await service.list_simulations(user_id=None, limit=50)

    assert len(result) == 2
    service._repo.list_simulations.assert_awaited_once_with(user_id=None, limit=50)


@pytest.mark.asyncio
async def test_list_simulations_with_user_id_filter() -> None:
    """list_simulations passes user_id to repo."""
    mock_session = _make_mock_session()
    service = SimulationService(mock_session)

    service._repo = MagicMock()
    service._repo.list_simulations = AsyncMock(return_value=[])

    await service.list_simulations(user_id="alice", limit=10)

    service._repo.list_simulations.assert_awaited_once_with(user_id="alice", limit=10)


# ---------------------------------------------------------------------------
# get_simulation service method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_simulation_returns_orm_row() -> None:
    """get_simulation returns the ORM row for a valid UUID."""
    sim_id = uuid.uuid4()
    sim = _make_sim_orm(sim_id=sim_id)

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)
    service._repo = MagicMock()
    service._repo.get_simulation = AsyncMock(return_value=sim)

    result = await service.get_simulation(str(sim_id))

    assert result is sim
    service._repo.get_simulation.assert_awaited_once_with(sim_id)


@pytest.mark.asyncio
async def test_get_simulation_returns_none_for_missing() -> None:
    """get_simulation returns None when repo returns None (not found / soft-deleted)."""
    mock_session = _make_mock_session()
    service = SimulationService(mock_session)
    service._repo = MagicMock()
    service._repo.get_simulation = AsyncMock(return_value=None)

    result = await service.get_simulation(str(uuid.uuid4()))

    assert result is None


@pytest.mark.asyncio
async def test_get_simulation_returns_none_for_invalid_uuid() -> None:
    """get_simulation returns None for a non-UUID string."""
    mock_session = _make_mock_session()
    service = SimulationService(mock_session)
    service._repo = MagicMock()
    service._repo.get_simulation = AsyncMock(return_value=None)

    result = await service.get_simulation("not-a-uuid")

    assert result is None
    service._repo.get_simulation.assert_not_awaited()


# ---------------------------------------------------------------------------
# save_config service method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_config_creates_simulation_without_running() -> None:
    """save_config persists config and returns ORM row without calling run_backtest."""
    from backend.db.models import AtlasSimulation
    from backend.models.simulation import SimulationConfig

    config = SimulationConfig.model_validate(_SAMPLE_CONFIG_DICT)

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)
    service._repo = MagicMock()

    # save_simulation receives the ORM, sets id/created_at server-side; return the same object
    async def passthrough_save(sim: AtlasSimulation) -> AtlasSimulation:
        return sim

    service._repo.save_simulation = passthrough_save

    # Ensure run_backtest is NOT called
    service.run_backtest = AsyncMock()

    result = await service.save_config(config=config, name="My Config", is_auto_loop=False)

    # Result should be an AtlasSimulation ORM instance (not a mock)
    assert isinstance(result, AtlasSimulation)
    assert result.name == "My Config"
    assert result.is_auto_loop is False
    assert result.result_summary is None
    service.run_backtest.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_config_sets_auto_loop_fields() -> None:
    """save_config passes is_auto_loop and auto_loop_cron to ORM."""
    from backend.db.models import AtlasSimulation
    from backend.models.simulation import SimulationConfig

    config = SimulationConfig.model_validate(_SAMPLE_CONFIG_DICT)

    captured_orm: list[AtlasSimulation] = []

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)
    service._repo = MagicMock()

    async def capture_save(sim: AtlasSimulation) -> AtlasSimulation:
        captured_orm.append(sim)
        sim.id = uuid.uuid4()
        sim.created_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        return sim

    service._repo.save_simulation = capture_save

    await service.save_config(
        config=config,
        name="Weekly Run",
        is_auto_loop=True,
        auto_loop_cron="0 6 * * 1",
    )

    assert len(captured_orm) == 1
    orm = captured_orm[0]
    assert orm.is_auto_loop is True
    assert orm.auto_loop_cron == "0 6 * * 1"
    assert orm.name == "Weekly Run"


# ---------------------------------------------------------------------------
# delete_simulation service method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_simulation_returns_true_for_existing() -> None:
    """delete_simulation returns True when repo soft-deletes successfully."""
    sim_id = uuid.uuid4()

    mock_session = _make_mock_session()
    service = SimulationService(mock_session)
    service._repo = MagicMock()
    service._repo.soft_delete = AsyncMock(return_value=True)

    result = await service.delete_simulation(str(sim_id))

    assert result is True
    service._repo.soft_delete.assert_awaited_once_with(sim_id)


@pytest.mark.asyncio
async def test_delete_simulation_returns_false_for_missing() -> None:
    """delete_simulation returns False when sim is not found."""
    mock_session = _make_mock_session()
    service = SimulationService(mock_session)
    service._repo = MagicMock()
    service._repo.soft_delete = AsyncMock(return_value=False)

    result = await service.delete_simulation(str(uuid.uuid4()))

    assert result is False


@pytest.mark.asyncio
async def test_delete_simulation_returns_false_for_invalid_uuid() -> None:
    """delete_simulation returns False for non-UUID string without hitting repo."""
    mock_session = _make_mock_session()
    service = SimulationService(mock_session)
    service._repo = MagicMock()
    service._repo.soft_delete = AsyncMock(return_value=False)

    result = await service.delete_simulation("bad-uuid-string")

    assert result is False
    service._repo.soft_delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# GET / route — list endpoint shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_endpoint_returns_simulation_list_response_shape() -> None:
    """GET / returns SimulationListResponse with correct fields."""
    from fastapi.testclient import TestClient

    from backend.db.session import get_db
    from backend.main import app

    sim_id = uuid.uuid4()
    sim = _make_sim_orm(sim_id=sim_id)

    mock_session = _make_mock_session()

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_session

    mock_service = MagicMock()
    mock_service.list_simulations = AsyncMock(return_value=[sim])

    with patch("backend.routes.simulate.SimulationService", return_value=mock_service):
        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=True)
            response = client.get("/api/v1/simulate/")
        finally:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert "simulations" in data
    assert "count" in data
    assert "data_as_of" in data
    assert data["count"] == 1
    assert data["simulations"][0]["id"] == str(sim_id)


# ---------------------------------------------------------------------------
# GET /{id} route — 404 shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_id_returns_404_for_missing() -> None:
    """GET /{id} returns 404 when simulation not found."""
    from fastapi.testclient import TestClient

    from backend.db.session import get_db
    from backend.main import app

    mock_session = _make_mock_session()

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_session

    mock_service = MagicMock()
    mock_service.get_simulation = AsyncMock(return_value=None)

    with patch("backend.routes.simulate.SimulationService", return_value=mock_service):
        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=False)
            missing_id = str(uuid.uuid4())
            response = client.get(f"/api/v1/simulate/{missing_id}")
        finally:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /save route — creates new sim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_route_returns_201_with_id() -> None:
    """POST /save returns 201 with id, name, created_at."""
    from fastapi.testclient import TestClient

    from backend.db.session import get_db
    from backend.main import app

    sim_id = uuid.uuid4()
    saved_sim = _make_sim_orm(sim_id=sim_id, has_result=False)
    saved_sim.result_summary = None

    mock_session = _make_mock_session()

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_session

    mock_service = MagicMock()
    mock_service.save_config = AsyncMock(return_value=saved_sim)

    payload = {
        "config": {
            "signal": "breadth",
            "instrument": "TEST",
            "instrument_type": "mf",
            "parameters": {
                "sip_amount": "10000",
                "lumpsum_amount": "50000",
                "buy_level": "60",
                "sell_level": "40",
                "sell_pct": "100",
                "redeploy_pct": "100",
                "cooldown_days": 30,
            },
            "start_date": "2022-01-01",
            "end_date": "2023-12-31",
        },
        "name": "Test Config",
        "is_auto_loop": False,
    }

    with patch("backend.routes.simulate.SimulationService", return_value=mock_service):
        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=True)
            response = client.post("/api/v1/simulate/save", json=payload)
        finally:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == str(sim_id)
    assert "created_at" in data


# ---------------------------------------------------------------------------
# DELETE /{id} route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_route_returns_204_for_existing() -> None:
    """DELETE /{id} returns 204 when found and soft-deleted."""
    from fastapi.testclient import TestClient

    from backend.db.session import get_db
    from backend.main import app

    sim_id = uuid.uuid4()
    mock_session = _make_mock_session()

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_session

    mock_service = MagicMock()
    mock_service.delete_simulation = AsyncMock(return_value=True)

    with patch("backend.routes.simulate.SimulationService", return_value=mock_service):
        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=True)
            response = client.delete(f"/api/v1/simulate/{sim_id}")
        finally:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_route_returns_404_for_missing() -> None:
    """DELETE /{id} returns 404 when simulation not found."""
    from fastapi.testclient import TestClient

    from backend.db.session import get_db
    from backend.main import app

    sim_id = uuid.uuid4()
    mock_session = _make_mock_session()

    async def override_get_db() -> AsyncMock:  # type: ignore[misc]
        yield mock_session

    mock_service = MagicMock()
    mock_service.delete_simulation = AsyncMock(return_value=False)

    with patch("backend.routes.simulate.SimulationService", return_value=mock_service):
        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app, raise_server_exceptions=False)
            response = client.delete(f"/api/v1/simulate/{sim_id}")
        finally:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404
