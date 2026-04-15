"""API-level tests for GET /api/v1/portfolio/{id}/optimize.

Tests:
- 200 response with full optimization structure
- 404 for non-existent portfolio
- Query params parsed correctly (models, max_weight, max_positions)
- Response schema conformance (models list, weights, constraints_applied)
- Infeasibility result included in 200 with solver_status != optimal
- data_as_of query param accepted
- Determinism: same params → same weights (via mocked service)
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.portfolio import (
    AnalysisProvenance,
    OptimizationModel,
    OptimizationResult,
    OptimizedWeight,
    PortfolioOptimizationResponse,
    SEBIConstraint,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_session() -> MagicMock:
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.execute = AsyncMock()
    mock.begin = MagicMock()
    mock.begin.return_value.__aenter__ = AsyncMock(return_value=mock)
    mock.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock


@pytest.fixture
def client() -> TestClient:
    from backend.db.session import get_db

    mock_session = _make_mock_session()

    async def override_get_db() -> Any:
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def _prov() -> AnalysisProvenance:
    return AnalysisProvenance(
        source_table="de_mf_nav_daily",
        formula="Riskfolio-Lib optimization on daily returns",
    )


def _make_opt_weight(mstar_id: str, opt_w: str, curr_w: str = "0.2000") -> OptimizedWeight:
    return OptimizedWeight(
        mstar_id=mstar_id,
        scheme_name=f"Scheme {mstar_id}",
        current_weight=Decimal(curr_w),
        optimized_weight=Decimal(opt_w),
        weight_change=Decimal(str(round(float(opt_w) - float(curr_w), 4))),
        provenance=_prov(),
    )


def _make_optimization_response(
    portfolio_id: uuid.UUID,
    include_mv: bool = True,
    include_hrp: bool = True,
    mv_status: str = "optimal",
) -> PortfolioOptimizationResponse:
    models = []

    constraint = SEBIConstraint(
        constraint_id="sebi_pms_max_weight",
        constraint_type="max_weight",
        description="SEBI PMS: maximum weight per fund",
        value=Decimal("0.1000"),
        is_binding=True,
        is_violated=False,
    )

    if include_mv:
        mv_weights = (
            [
                _make_opt_weight("F1", "0.1000"),
                _make_opt_weight("F2", "0.0800"),
                _make_opt_weight("F3", "0.0900"),
            ]
            if mv_status == "optimal"
            else []
        )
        models.append(
            OptimizationResult(
                model=OptimizationModel.mean_variance,
                weights=mv_weights,
                expected_return=Decimal("0.1200") if mv_status == "optimal" else None,
                expected_risk=Decimal("0.0800") if mv_status == "optimal" else None,
                sharpe_ratio=Decimal("1.5000") if mv_status == "optimal" else None,
                constraints_applied=[constraint],
                solver_status=mv_status,
                computation_time_ms=250,
            )
        )

    if include_hrp:
        models.append(
            OptimizationResult(
                model=OptimizationModel.hrp,
                weights=[
                    _make_opt_weight("F1", "0.3500"),
                    _make_opt_weight("F2", "0.3200"),
                    _make_opt_weight("F3", "0.3300"),
                ],
                constraints_applied=[],
                solver_status="optimal",
                computation_time_ms=80,
            )
        )

    return PortfolioOptimizationResponse(
        portfolio_id=portfolio_id,
        portfolio_name="Test Portfolio",
        data_as_of=datetime.date(2026, 4, 14),
        computed_at=datetime.datetime(2026, 4, 14, 12, 0, 0, tzinfo=datetime.timezone.utc),
        models=models,
        candidate_count=3,
        excluded_funds=[],
        provenance={"optimization": _prov()},
    )


# ---------------------------------------------------------------------------
# Tests: 200 response structure
# ---------------------------------------------------------------------------


def test_portfolio_optimize_returns_200(client: TestClient) -> None:
    """GET /{id}/optimize returns 200 with optimization structure."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id)

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["portfolio_id"] == str(portfolio_id)
    assert data["portfolio_name"] == "Test Portfolio"
    assert "data_as_of" in data
    assert "computed_at" in data
    assert "models" in data
    assert "candidate_count" in data
    assert "excluded_funds" in data
    assert "provenance" in data


def test_portfolio_optimize_response_includes_model_results(client: TestClient) -> None:
    """Response includes model results with weights and constraints."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id)

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")

    assert resp.status_code == 200
    data = resp.json()
    models = data["models"]
    assert len(models) == 2

    # MV result
    mv = next(m for m in models if m["model"] == "mean_variance")
    assert mv["solver_status"] == "optimal"
    assert len(mv["weights"]) == 3
    assert "expected_return" in mv
    assert "expected_risk" in mv
    assert "sharpe_ratio" in mv
    assert "constraints_applied" in mv
    assert "computation_time_ms" in mv

    # HRP result
    hrp = next(m for m in models if m["model"] == "hrp")
    assert hrp["solver_status"] == "optimal"
    assert len(hrp["weights"]) == 3


def test_portfolio_optimize_weight_fields(client: TestClient) -> None:
    """Each weight entry has mstar_id, scheme_name, current/optimized weight, change, provenance."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id)

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")

    assert resp.status_code == 200
    mv = next(m for m in resp.json()["models"] if m["model"] == "mean_variance")
    w = mv["weights"][0]
    assert "mstar_id" in w
    assert "scheme_name" in w
    assert "current_weight" in w
    assert "optimized_weight" in w
    assert "weight_change" in w
    assert "provenance" in w


def test_portfolio_optimize_constraint_fields(client: TestClient) -> None:
    """SEBI constraint fields are present in constraints_applied."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id)

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")

    assert resp.status_code == 200
    mv = next(m for m in resp.json()["models"] if m["model"] == "mean_variance")
    c = mv["constraints_applied"][0]
    assert c["constraint_id"] == "sebi_pms_max_weight"
    assert c["constraint_type"] == "max_weight"
    assert "description" in c
    assert "value" in c
    assert "is_binding" in c
    assert "is_violated" in c


# ---------------------------------------------------------------------------
# Tests: 404 for non-existent portfolio
# ---------------------------------------------------------------------------


def test_portfolio_optimize_returns_404_for_missing_portfolio(client: TestClient) -> None:
    """GET /{id}/optimize returns 404 when portfolio not found."""
    portfolio_id = uuid.uuid4()

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = AsyncMock(
            side_effect=ValueError(f"Portfolio {portfolio_id} not found")
        )
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")

    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: Query params
# ---------------------------------------------------------------------------


def test_portfolio_optimize_default_query_params(client: TestClient) -> None:
    """Default query params (models=mean_variance,hrp, max_weight=0.10) are applied."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id)
    captured_kwargs: dict[str, Any] = {}

    async def capture_optimize(**kwargs: Any) -> PortfolioOptimizationResponse:
        captured_kwargs.update(kwargs)
        return expected

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = capture_optimize
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")

    assert resp.status_code == 200
    assert "mean_variance" in captured_kwargs.get("models", [])
    assert "hrp" in captured_kwargs.get("models", [])
    assert captured_kwargs.get("max_weight") == Decimal("0.10")


def test_portfolio_optimize_custom_max_weight(client: TestClient) -> None:
    """Custom max_weight query param is passed to service."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id)
    captured_kwargs: dict[str, Any] = {}

    async def capture_optimize(**kwargs: Any) -> PortfolioOptimizationResponse:
        captured_kwargs.update(kwargs)
        return expected

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = capture_optimize
        MockSvc.return_value = mock_svc

        resp = client.get(
            f"/api/v1/portfolio/{portfolio_id}/optimize",
            params={"max_weight": "0.25"},
        )

    assert resp.status_code == 200
    assert captured_kwargs.get("max_weight") == Decimal("0.25")


def test_portfolio_optimize_single_model_param(client: TestClient) -> None:
    """models=hrp query param results in only HRP being requested."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id, include_mv=False)
    captured_kwargs: dict[str, Any] = {}

    async def capture_optimize(**kwargs: Any) -> PortfolioOptimizationResponse:
        captured_kwargs.update(kwargs)
        return expected

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = capture_optimize
        MockSvc.return_value = mock_svc

        resp = client.get(
            f"/api/v1/portfolio/{portfolio_id}/optimize",
            params={"models": "hrp"},
        )

    assert resp.status_code == 200
    assert captured_kwargs.get("models") == ["hrp"]


def test_portfolio_optimize_data_as_of_param(client: TestClient) -> None:
    """data_as_of query param is passed to service."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id)
    captured_kwargs: dict[str, Any] = {}

    async def capture_optimize(**kwargs: Any) -> PortfolioOptimizationResponse:
        captured_kwargs.update(kwargs)
        return expected

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = capture_optimize
        MockSvc.return_value = mock_svc

        resp = client.get(
            f"/api/v1/portfolio/{portfolio_id}/optimize",
            params={"data_as_of": "2026-01-15"},
        )

    assert resp.status_code == 200
    assert captured_kwargs.get("data_as_of") == datetime.date(2026, 1, 15)


def test_portfolio_optimize_max_positions_param(client: TestClient) -> None:
    """max_positions query param is passed to service."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id)
    captured_kwargs: dict[str, Any] = {}

    async def capture_optimize(**kwargs: Any) -> PortfolioOptimizationResponse:
        captured_kwargs.update(kwargs)
        return expected

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = capture_optimize
        MockSvc.return_value = mock_svc

        resp = client.get(
            f"/api/v1/portfolio/{portfolio_id}/optimize",
            params={"max_positions": "8"},
        )

    assert resp.status_code == 200
    assert captured_kwargs.get("max_positions") == 8


# ---------------------------------------------------------------------------
# Tests: Infeasibility
# ---------------------------------------------------------------------------


def test_portfolio_optimize_infeasible_constraints_in_200_response(client: TestClient) -> None:
    """Infeasible MV constraints returned in 200 with solver_status=infeasible."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id, include_mv=True, mv_status="infeasible")

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")

    assert resp.status_code == 200
    data = resp.json()
    mv = next(m for m in data["models"] if m["model"] == "mean_variance")
    assert mv["solver_status"] == "infeasible"
    assert mv["weights"] == []


# ---------------------------------------------------------------------------
# Tests: Excluded funds
# ---------------------------------------------------------------------------


def test_portfolio_optimize_excluded_funds_in_response(client: TestClient) -> None:
    """Funds excluded due to insufficient data appear in excluded_funds."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id)
    expected.excluded_funds = [
        {
            "mstar_id": "F_short",
            "scheme_name": "Short Fund",
            "reason": "Insufficient NAV history (5 points, need 20)",
        }
    ]

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["excluded_funds"]) == 1
    ef = data["excluded_funds"][0]
    assert ef["mstar_id"] == "F_short"
    assert "reason" in ef


# ---------------------------------------------------------------------------
# Tests: Determinism
# ---------------------------------------------------------------------------


def test_portfolio_optimize_determinism_same_params_same_response(client: TestClient) -> None:
    """Same params return identical weights (service is deterministic)."""
    portfolio_id = uuid.uuid4()
    expected = _make_optimization_response(portfolio_id)

    with patch("backend.routes.portfolio.PortfolioOptimizationService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.optimize_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp1 = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")
        resp2 = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")

    assert resp1.status_code == resp2.status_code == 200
    # Models and weights should be identical
    m1 = resp1.json()["models"]
    m2 = resp2.json()["models"]
    assert m1 == m2
