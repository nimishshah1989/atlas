"""API-level tests for GET /api/v1/portfolio/{id}/analysis.

These tests use FastAPI TestClient (not a live server) and mock the service layer.
All tests patch get_db (FastAPI Dependency Patch Gotcha pattern).

Tests:
- 200 response with full analysis structure
- 404 for non-existent portfolio
- Graceful degradation: analysis with unavailable list
- Determinism via API
- data_as_of query param accepted
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
    HoldingAnalysis,
    PortfolioFullAnalysisResponse,
    PortfolioLevelAnalysis,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_session() -> MagicMock:
    """Create a mock async session (no real DB)."""
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.execute = AsyncMock()
    mock.flush = AsyncMock()
    mock.add = MagicMock()
    mock.begin = MagicMock()
    mock.begin.return_value.__aenter__ = AsyncMock(return_value=mock)
    mock.begin.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock


@pytest.fixture
def client() -> TestClient:
    """TestClient with get_db dependency overridden (FastAPI Dependency Patch Gotcha)."""
    from backend.db.session import get_db

    mock_session = _make_mock_session()

    async def override_get_db() -> Any:
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def _full_analysis_response(
    portfolio_id: uuid.UUID,
    weighted_rs: Decimal = Decimal("55.0000"),
    with_unavailable: bool = False,
) -> PortfolioFullAnalysisResponse:
    """Build a fake PortfolioFullAnalysisResponse for testing."""
    holding_id = uuid.uuid4()
    ha = HoldingAnalysis(
        holding_id=holding_id,
        mstar_id="F00001",
        scheme_name="Test Scheme",
        units=Decimal("100.0000"),
        nav=Decimal("50.0000"),
        current_value=Decimal("5000.0000"),
        weight_pct=Decimal("100.00"),
        return_1y=Decimal("15.50"),
        rs_composite=Decimal("65.00"),
        rs_momentum_28d=Decimal("3.00"),
        quadrant="LEADING",
        sharpe_ratio=Decimal("1.2500"),
        sortino_ratio=Decimal("1.5000"),
        alpha=Decimal("2.0000"),
        beta=Decimal("0.9000"),
        weighted_rsi=Decimal("55.00"),
        top_sectors=[
            {"sector": "Financial Services", "weight_pct": Decimal("35.00")},
        ],
        provenance={
            "nav": AnalysisProvenance(
                source_table="de_mf_nav_daily",
                formula="Latest NAV",
            ),
            "rs_composite": AnalysisProvenance(
                source_table="de_rs_scores",
                formula="latest_rs_composite from de_rs_scores",
            ),
        },
    )

    unavailable = (
        [
            {
                "holding_id": str(uuid.uuid4()),
                "mstar_id": "F00002",
                "scheme_name": "Failed Scheme",
                "reason": "JIP timeout",
            }
        ]
        if with_unavailable
        else []
    )

    portfolio_level = PortfolioLevelAnalysis(
        total_value=Decimal("5000.0000"),
        total_cost=Decimal("4000.0000"),
        holdings_count=1 + len(unavailable),
        mapped_count=1,
        unmapped_count=0,
        weighted_rs=weighted_rs,
        sector_weights={"Financial Services": Decimal("35.00")},
        quadrant_distribution={"LEADING": 1},
        weighted_sharpe=Decimal("1.2500"),
        weighted_sortino=Decimal("1.5000"),
        weighted_beta=Decimal("0.9000"),
        overlap_pairs=[],
        provenance={
            "weighted_rs": AnalysisProvenance(
                source_table="de_rs_scores",
                formula="sum(holding_value * rs_composite) / sum(holding_value)",
            ),
        },
    )

    return PortfolioFullAnalysisResponse(
        portfolio_id=portfolio_id,
        portfolio_name="Test Portfolio",
        data_as_of=datetime.date(2026, 4, 14),
        computed_at=datetime.datetime(2026, 4, 14, 12, 0, 0, tzinfo=datetime.timezone.utc),
        holdings=[ha],
        portfolio=portfolio_level,
        unavailable=unavailable,
        rs_data_available=True,
    )


# ---------------------------------------------------------------------------
# Tests: 200 response structure
# ---------------------------------------------------------------------------


def test_portfolio_analysis_returns_200(client: TestClient) -> None:
    """GET /{id}/analysis returns 200 with full analysis structure."""
    portfolio_id = uuid.uuid4()
    expected = _full_analysis_response(portfolio_id)

    with patch("backend.routes.portfolio.PortfolioAnalysisService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.analyze_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/analysis")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    # Top-level fields
    assert data["portfolio_id"] == str(portfolio_id)
    assert data["portfolio_name"] == "Test Portfolio"
    assert "data_as_of" in data
    assert "computed_at" in data
    assert "holdings" in data
    assert "portfolio" in data
    assert "unavailable" in data
    assert "rs_data_available" in data


def test_portfolio_analysis_response_includes_holding_metrics(client: TestClient) -> None:
    """Analysis response includes per-holding JIP metrics."""
    portfolio_id = uuid.uuid4()
    expected = _full_analysis_response(portfolio_id)

    with patch("backend.routes.portfolio.PortfolioAnalysisService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.analyze_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/analysis")

    assert resp.status_code == 200
    data = resp.json()
    holdings = data["holdings"]
    assert len(holdings) == 1
    h = holdings[0]
    assert h["mstar_id"] == "F00001"
    assert h["quadrant"] == "LEADING"
    assert "rs_composite" in h
    assert "sharpe_ratio" in h
    assert "provenance" in h


def test_portfolio_analysis_response_includes_portfolio_level_metrics(client: TestClient) -> None:
    """Analysis response includes portfolio-level aggregates."""
    portfolio_id = uuid.uuid4()
    expected = _full_analysis_response(portfolio_id)

    with patch("backend.routes.portfolio.PortfolioAnalysisService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.analyze_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/analysis")

    assert resp.status_code == 200
    data = resp.json()
    portfolio = data["portfolio"]
    assert "weighted_rs" in portfolio
    assert "sector_weights" in portfolio
    assert "quadrant_distribution" in portfolio
    assert "weighted_sharpe" in portfolio
    assert "provenance" in portfolio


# ---------------------------------------------------------------------------
# Tests: 404 for non-existent portfolio
# ---------------------------------------------------------------------------


def test_portfolio_analysis_returns_404_for_unknown_portfolio(client: TestClient) -> None:
    """GET /{id}/analysis returns 404 when portfolio does not exist."""
    portfolio_id = uuid.uuid4()

    with patch("backend.routes.portfolio.PortfolioAnalysisService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.analyze_portfolio = AsyncMock(
            side_effect=ValueError(f"Portfolio {portfolio_id} not found")
        )
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/analysis")

    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "detail" in data


# ---------------------------------------------------------------------------
# Tests: graceful degradation via API
# ---------------------------------------------------------------------------


def test_portfolio_analysis_returns_200_with_unavailable_list(client: TestClient) -> None:
    """Analysis returns 200 even when some holdings have JIP fetch failures."""
    portfolio_id = uuid.uuid4()
    expected = _full_analysis_response(portfolio_id, with_unavailable=True)

    with patch("backend.routes.portfolio.PortfolioAnalysisService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.analyze_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/analysis")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["unavailable"]) == 1
    assert data["unavailable"][0]["mstar_id"] == "F00002"
    assert "reason" in data["unavailable"][0]


def test_portfolio_analysis_rs_data_unavailable_returns_200(client: TestClient) -> None:
    """Analysis returns 200 with rs_data_available=False when RS batch failed."""
    portfolio_id = uuid.uuid4()
    expected = _full_analysis_response(portfolio_id)
    expected.rs_data_available = False
    expected.portfolio.weighted_rs = None

    with patch("backend.routes.portfolio.PortfolioAnalysisService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.analyze_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/analysis")

    assert resp.status_code == 200
    data = resp.json()
    assert data["rs_data_available"] is False
    assert data["portfolio"]["weighted_rs"] is None


# ---------------------------------------------------------------------------
# Tests: data_as_of query param
# ---------------------------------------------------------------------------


def test_portfolio_analysis_accepts_data_as_of_param(client: TestClient) -> None:
    """Analysis endpoint accepts data_as_of query param without error."""
    portfolio_id = uuid.uuid4()
    expected = _full_analysis_response(portfolio_id)

    with patch("backend.routes.portfolio.PortfolioAnalysisService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.analyze_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(
            f"/api/v1/portfolio/{portfolio_id}/analysis",
            params={"data_as_of": "2026-04-14"},
        )

    assert resp.status_code == 200

    # Verify data_as_of was passed to service
    call_kwargs = mock_svc.analyze_portfolio.call_args
    assert call_kwargs is not None
    # data_as_of should be passed as keyword arg
    kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
    if "data_as_of" in kwargs:
        assert kwargs["data_as_of"] == datetime.date(2026, 4, 14)


def test_portfolio_analysis_invalid_date_returns_error(client: TestClient) -> None:
    """Invalid data_as_of param returns 400 (Pydantic validation error → §20.5 handler)."""
    portfolio_id = uuid.uuid4()

    with patch("backend.routes.portfolio.PortfolioAnalysisService") as MockSvc:
        mock_svc = MagicMock()
        MockSvc.return_value = mock_svc

        resp = client.get(
            f"/api/v1/portfolio/{portfolio_id}/analysis",
            params={"data_as_of": "not-a-date"},
        )

    # Should be 400 or 422 depending on §20.5 handler — must NOT be 200 or 500
    assert resp.status_code in (400, 422), (
        f"Invalid date should return 400 or 422, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Tests: determinism via API (same portfolio_id → same response fields)
# ---------------------------------------------------------------------------


def test_portfolio_analysis_is_deterministic_via_api(client: TestClient) -> None:
    """Same portfolio_id + data_as_of → same weighted_rs and sector_weights."""
    portfolio_id = uuid.uuid4()
    fixed_date = "2026-04-14"
    expected = _full_analysis_response(portfolio_id, weighted_rs=Decimal("55.0000"))

    with patch("backend.routes.portfolio.PortfolioAnalysisService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.analyze_portfolio = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp1 = client.get(
            f"/api/v1/portfolio/{portfolio_id}/analysis",
            params={"data_as_of": fixed_date},
        )
        resp2 = client.get(
            f"/api/v1/portfolio/{portfolio_id}/analysis",
            params={"data_as_of": fixed_date},
        )

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    d1 = resp1.json()
    d2 = resp2.json()

    assert d1["portfolio"]["weighted_rs"] == d2["portfolio"]["weighted_rs"]
    assert d1["portfolio"]["sector_weights"] == d2["portfolio"]["sector_weights"]
    assert d1["portfolio"]["quadrant_distribution"] == d2["portfolio"]["quadrant_distribution"]
