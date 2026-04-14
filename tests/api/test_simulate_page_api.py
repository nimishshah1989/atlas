"""Backend API shape tests for V3-8 Simulation Lab frontend consumption.

Verifies that simulation API endpoints return the shapes the frontend
components expect. Uses mock SimulationService and JIPDataService.
These are unit-level tests (no real DB), not integration tests.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.db.session import get_db
from backend.main import app
from backend.models.simulation import (
    SimulationResult,
    SimulationSummary,
    TaxSummary,
    SimulationListItem,
    SimulationConfig,
    SimulationParameters,
    SignalType,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_config() -> dict[str, Any]:
    return {
        "signal": "breadth",
        "instrument": "NIFTY50.NS",
        "instrument_type": "equity",
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
        "start_date": "2018-01-01",
        "end_date": "2023-12-31",
        "combined_config": None,
    }


def _make_summary() -> SimulationSummary:
    return SimulationSummary(
        total_invested=Decimal("120000"),
        final_value=Decimal("180000"),
        xirr=Decimal("12.5"),
        cagr=Decimal("10.2"),
        vs_plain_sip=Decimal("3.1"),
        vs_benchmark=Decimal("2.5"),
        alpha=Decimal("1.8"),
        max_drawdown=Decimal("-0.15"),
        sharpe=Decimal("0.85"),
        sortino=Decimal("1.10"),
    )


def _make_tax_summary() -> TaxSummary:
    return TaxSummary(
        stcg=Decimal("1200"),
        ltcg=Decimal("3500"),
        total_tax=Decimal("4700"),
        post_tax_xirr=Decimal("11.3"),
        unrealized=Decimal("15000"),
    )


def _make_simulation_result() -> SimulationResult:
    return SimulationResult(
        summary=_make_summary(),
        daily_values=[],
        transactions=[],
        tax_summary=_make_tax_summary(),
        tear_sheet_url=None,
        data_as_of=datetime.datetime(2026, 4, 14, tzinfo=datetime.timezone.utc),
    )


def _make_list_item(sim_id: uuid.UUID | None = None) -> SimulationListItem:
    cfg = SimulationConfig(
        signal=SignalType.BREADTH,
        instrument="NIFTY50.NS",
        instrument_type="equity",
        parameters=SimulationParameters(
            sip_amount=Decimal("10000"),
            lumpsum_amount=Decimal("50000"),
            buy_level=Decimal("60"),
            sell_level=Decimal("40"),
            sell_pct=Decimal("100"),
            redeploy_pct=Decimal("100"),
            cooldown_days=30,
        ),
        start_date=datetime.date(2018, 1, 1),
        end_date=datetime.date(2023, 12, 31),
    )
    return SimulationListItem(
        id=sim_id or uuid.uuid4(),
        name="Test Sim",
        config=cfg,
        created_at=datetime.datetime(2026, 4, 10, tzinfo=datetime.timezone.utc),
        is_auto_loop=False,
    )


def _override_db(mock_session: Any) -> Any:
    async def _get_db() -> Any:  # type: ignore[misc]
        yield mock_session

    return _get_db


# ---------------------------------------------------------------------------
# POST /run tests
# ---------------------------------------------------------------------------


class TestPostRunShape:
    """Verify POST /run returns the shape SimulationResults component expects."""

    def test_run_returns_200(self) -> None:
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.run_backtest = AsyncMock(return_value=_make_simulation_result())

        mock_jip = MagicMock()
        last_update = datetime.datetime(2026, 4, 14, tzinfo=datetime.timezone.utc)
        mock_jip.get_data_freshness = AsyncMock(return_value={"last_update": last_update})

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            with patch("backend.routes.simulate.JIPDataService", return_value=mock_jip):
                app.dependency_overrides[get_db] = _override_db(mock_session)
                try:
                    client = TestClient(app)
                    resp = client.post(
                        "/api/v1/simulate/run",
                        json={"config": _make_config()},
                    )
                finally:
                    app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_run_response_has_result_field(self) -> None:
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.run_backtest = AsyncMock(return_value=_make_simulation_result())

        mock_jip = MagicMock()
        mock_jip.get_data_freshness = AsyncMock(return_value={})

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            with patch("backend.routes.simulate.JIPDataService", return_value=mock_jip):
                app.dependency_overrides[get_db] = _override_db(mock_session)
                try:
                    client = TestClient(app)
                    resp = client.post(
                        "/api/v1/simulate/run",
                        json={"config": _make_config()},
                    )
                finally:
                    app.dependency_overrides.pop(get_db, None)

        data = resp.json()
        assert "result" in data
        assert "data_as_of" in data
        assert "staleness" in data

    def test_run_response_summary_has_kpi_fields(self) -> None:
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.run_backtest = AsyncMock(return_value=_make_simulation_result())

        mock_jip = MagicMock()
        mock_jip.get_data_freshness = AsyncMock(return_value={})

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            with patch("backend.routes.simulate.JIPDataService", return_value=mock_jip):
                app.dependency_overrides[get_db] = _override_db(mock_session)
                try:
                    client = TestClient(app)
                    resp = client.post(
                        "/api/v1/simulate/run",
                        json={"config": _make_config()},
                    )
                finally:
                    app.dependency_overrides.pop(get_db, None)

        summary = resp.json()["result"]["summary"]
        required_kpis = [
            "total_invested",
            "final_value",
            "xirr",
            "cagr",
            "vs_plain_sip",
            "vs_benchmark",
            "alpha",
            "max_drawdown",
            "sharpe",
            "sortino",
        ]
        for kpi in required_kpis:
            assert kpi in summary, f"Missing KPI: {kpi}"

    def test_run_response_has_tax_summary(self) -> None:
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.run_backtest = AsyncMock(return_value=_make_simulation_result())

        mock_jip = MagicMock()
        mock_jip.get_data_freshness = AsyncMock(return_value={})

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            with patch("backend.routes.simulate.JIPDataService", return_value=mock_jip):
                app.dependency_overrides[get_db] = _override_db(mock_session)
                try:
                    client = TestClient(app)
                    resp = client.post(
                        "/api/v1/simulate/run",
                        json={"config": _make_config()},
                    )
                finally:
                    app.dependency_overrides.pop(get_db, None)

        tax = resp.json()["result"]["tax_summary"]
        assert "stcg" in tax
        assert "ltcg" in tax
        assert "total_tax" in tax
        assert "post_tax_xirr" in tax
        assert "unrealized" in tax

    def test_run_returns_400_on_value_error(self) -> None:
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.run_backtest = AsyncMock(side_effect=ValueError("buy_level must be > sell_level"))

        mock_jip = MagicMock()
        mock_jip.get_data_freshness = AsyncMock(return_value={})

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            with patch("backend.routes.simulate.JIPDataService", return_value=mock_jip):
                app.dependency_overrides[get_db] = _override_db(mock_session)
                try:
                    client = TestClient(app)
                    resp = client.post(
                        "/api/v1/simulate/run",
                        json={"config": _make_config()},
                    )
                finally:
                    app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 400
        assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# GET / list tests
# ---------------------------------------------------------------------------


class TestGetListShape:
    """Verify GET / returns the shape SavedSimulations component expects."""

    def test_list_returns_200(self) -> None:
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.list_simulations = AsyncMock(return_value=[_make_list_item()])

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            app.dependency_overrides[get_db] = _override_db(mock_session)
            try:
                client = TestClient(app)
                resp = client.get("/api/v1/simulate/")
            finally:
                app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_list_has_simulations_count_data_as_of(self) -> None:
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.list_simulations = AsyncMock(return_value=[_make_list_item(), _make_list_item()])

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            app.dependency_overrides[get_db] = _override_db(mock_session)
            try:
                client = TestClient(app)
                resp = client.get("/api/v1/simulate/")
            finally:
                app.dependency_overrides.pop(get_db, None)

        data = resp.json()
        assert "simulations" in data
        assert "count" in data
        assert "data_as_of" in data
        assert data["count"] == 2
        assert len(data["simulations"]) == 2

    def test_list_item_has_required_fields(self) -> None:
        sim_id = uuid.uuid4()
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.list_simulations = AsyncMock(return_value=[_make_list_item(sim_id)])

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            app.dependency_overrides[get_db] = _override_db(mock_session)
            try:
                client = TestClient(app)
                resp = client.get("/api/v1/simulate/")
            finally:
                app.dependency_overrides.pop(get_db, None)

        item = resp.json()["simulations"][0]
        assert "id" in item
        assert "config" in item
        assert "created_at" in item
        assert "is_auto_loop" in item
        assert item["id"] == str(sim_id)

    def test_list_empty_returns_zero_count(self) -> None:
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.list_simulations = AsyncMock(return_value=[])

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            app.dependency_overrides[get_db] = _override_db(mock_session)
            try:
                client = TestClient(app)
                resp = client.get("/api/v1/simulate/")
            finally:
                app.dependency_overrides.pop(get_db, None)

        data = resp.json()
        assert data["count"] == 0
        assert data["simulations"] == []


# ---------------------------------------------------------------------------
# POST /save tests
# ---------------------------------------------------------------------------


class TestPostSaveShape:
    """Verify POST /save returns the shape the frontend save flow expects."""

    def test_save_returns_201(self) -> None:
        sim_id = uuid.uuid4()
        mock_session = AsyncMock()
        mock_svc = MagicMock()

        mock_orm = MagicMock()
        mock_orm.id = sim_id
        mock_orm.name = "My Sim"
        mock_orm.created_at = datetime.datetime(2026, 4, 14, tzinfo=datetime.timezone.utc)
        mock_svc.save_config = AsyncMock(return_value=mock_orm)

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            app.dependency_overrides[get_db] = _override_db(mock_session)
            try:
                client = TestClient(app)
                resp = client.post(
                    "/api/v1/simulate/save",
                    json={"config": _make_config(), "name": "My Sim"},
                )
            finally:
                app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 201

    def test_save_returns_id_name_created_at(self) -> None:
        sim_id = uuid.uuid4()
        mock_session = AsyncMock()
        mock_svc = MagicMock()

        mock_orm = MagicMock()
        mock_orm.id = sim_id
        mock_orm.name = "My Sim"
        mock_orm.created_at = datetime.datetime(2026, 4, 14, tzinfo=datetime.timezone.utc)
        mock_svc.save_config = AsyncMock(return_value=mock_orm)

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            app.dependency_overrides[get_db] = _override_db(mock_session)
            try:
                client = TestClient(app)
                resp = client.post(
                    "/api/v1/simulate/save",
                    json={"config": _make_config(), "name": "My Sim"},
                )
            finally:
                app.dependency_overrides.pop(get_db, None)

        data = resp.json()
        assert "id" in data
        assert "name" in data
        assert "created_at" in data
        assert data["id"] == str(sim_id)
        assert data["name"] == "My Sim"


# ---------------------------------------------------------------------------
# DELETE /{id} tests
# ---------------------------------------------------------------------------


class TestDeleteShape:
    """Verify DELETE /{id} returns 204 and frontend can handle soft-delete."""

    def test_delete_returns_204(self) -> None:
        sim_id = uuid.uuid4()
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.delete_simulation = AsyncMock(return_value=True)

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            app.dependency_overrides[get_db] = _override_db(mock_session)
            try:
                client = TestClient(app)
                resp = client.delete(f"/api/v1/simulate/{sim_id}")
            finally:
                app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 204

    def test_delete_returns_404_for_unknown_id(self) -> None:
        sim_id = uuid.uuid4()
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.delete_simulation = AsyncMock(return_value=False)

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            app.dependency_overrides[get_db] = _override_db(mock_session)
            try:
                client = TestClient(app)
                resp = client.delete(f"/api/v1/simulate/{sim_id}")
            finally:
                app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /{id} detail tests
# ---------------------------------------------------------------------------


def _make_orm_sim(sim_id: uuid.UUID) -> MagicMock:
    """Build an ORM-like mock that the GET /{id} route reconstructs from JSONB."""
    created = datetime.datetime(2026, 4, 10, tzinfo=datetime.timezone.utc)
    summary_dict = {
        "total_invested": "120000",
        "final_value": "180000",
        "xirr": "12.5",
        "cagr": "10.2",
        "vs_plain_sip": "3.1",
        "vs_benchmark": "2.5",
        "alpha": "1.8",
        "max_drawdown": "-0.15",
        "sharpe": "0.85",
        "sortino": "1.10",
    }
    tax_dict = {
        "stcg": "1200",
        "ltcg": "3500",
        "total_tax": "4700",
        "post_tax_xirr": "11.3",
        "unrealized": "15000",
    }
    config_dict = {
        "signal": "breadth",
        "instrument": "NIFTY50.NS",
        "instrument_type": "equity",
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
        "start_date": "2018-01-01",
        "end_date": "2023-12-31",
        "combined_config": None,
    }
    mock_orm = MagicMock()
    mock_orm.id = sim_id
    mock_orm.name = "Test Sim"
    mock_orm.config = config_dict
    mock_orm.result_summary = summary_dict
    mock_orm.tax_summary = tax_dict
    mock_orm.daily_values = []
    mock_orm.transactions = []
    mock_orm.created_at = created
    mock_orm.is_auto_loop = False
    mock_orm.auto_loop_cron = None
    mock_orm.last_auto_run = None
    return mock_orm


class TestGetDetailShape:
    """Verify GET /{id} returns the SimulationDetailResponse shape."""

    def test_get_detail_returns_200(self) -> None:
        sim_id = uuid.uuid4()
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.get_simulation = AsyncMock(return_value=_make_orm_sim(sim_id))

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            app.dependency_overrides[get_db] = _override_db(mock_session)
            try:
                client = TestClient(app)
                resp = client.get(f"/api/v1/simulate/{sim_id}")
            finally:
                app.dependency_overrides.pop(get_db, None)

        assert resp.status_code == 200

    def test_get_detail_response_has_config_and_result(self) -> None:
        sim_id = uuid.uuid4()
        mock_session = AsyncMock()
        mock_svc = MagicMock()
        mock_svc.get_simulation = AsyncMock(return_value=_make_orm_sim(sim_id))

        with patch("backend.routes.simulate.SimulationService", return_value=mock_svc):
            app.dependency_overrides[get_db] = _override_db(mock_session)
            try:
                client = TestClient(app)
                resp = client.get(f"/api/v1/simulate/{sim_id}")
            finally:
                app.dependency_overrides.pop(get_db, None)

        data = resp.json()
        assert "id" in data
        assert "config" in data
        assert "result" in data
        assert "is_auto_loop" in data
        assert "data_as_of" in data
        assert data["id"] == str(sim_id)
