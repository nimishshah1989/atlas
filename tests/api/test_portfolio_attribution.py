"""API-level tests for GET /api/v1/portfolio/{id}/attribution.

Tests:
- 200 response with full attribution structure
- 404 for non-existent portfolio
- Brinson effects present in response
- data_as_of query param accepted
- returns_available=False degrades gracefully
- Determinism: same portfolio → same response
- Response includes formula + tolerance + data_as_of (traceability)
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
    BrinsonAttributionSummary,
    BrinsonCategoryEffect,
    PortfolioAttributionResponse,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_session() -> MagicMock:
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
    from backend.db.session import get_db

    mock_session = _make_mock_session()

    async def override_get_db() -> Any:
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def _make_attribution_response(
    portfolio_id: uuid.UUID,
    returns_available: bool = True,
    with_effects: bool = True,
) -> PortfolioAttributionResponse:
    alloc = Decimal("0.0196") if with_effects else None
    selec = Decimal("-0.0120") if with_effects else None
    inter = Decimal("0.0084") if with_effects else None
    total = Decimal("0.0160") if with_effects else None

    prov = AnalysisProvenance(
        source_table="de_mf_nav_daily, de_mf_derived_daily, de_mf_master",
        formula="alloc=(w_p-w_b)*(R_b_sector-R_b_total)",
    )

    cat = BrinsonCategoryEffect(
        category_name="Large Cap",
        portfolio_weight=Decimal("0.6000"),
        benchmark_weight=Decimal("0.3000"),
        portfolio_return=Decimal("2.5000") if with_effects else None,
        benchmark_return=Decimal("12.0000") if with_effects else None,
        allocation_effect=alloc,
        selection_effect=selec,
        interaction_effect=inter,
        total_effect=total,
        holding_count=2,
        provenance=prov,
    )

    summary = BrinsonAttributionSummary(
        total_allocation_effect=alloc,
        total_selection_effect=selec,
        total_interaction_effect=inter,
        total_active_return=total,
        benchmark_total_return=Decimal("12.0000") if returns_available else None,
    )

    return PortfolioAttributionResponse(
        portfolio_id=portfolio_id,
        portfolio_name="Test Portfolio",
        data_as_of=datetime.date(2026, 4, 14),
        computed_at=datetime.datetime(2026, 4, 14, 12, 0, 0, tzinfo=datetime.timezone.utc),
        categories=[cat],
        summary=summary,
        returns_available=returns_available,
        benchmark_description="Equal-weighted by active fund count per category from JIP",
        unavailable_holdings=[],
    )


# ---------------------------------------------------------------------------
# Tests: 200 response structure
# ---------------------------------------------------------------------------


def test_portfolio_attribution_returns_200(client: TestClient) -> None:
    """GET /{id}/attribution returns 200 with full attribution structure."""
    portfolio_id = uuid.uuid4()
    expected = _make_attribution_response(portfolio_id)

    with patch("backend.routes.portfolio.BrinsonAttributionService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.compute_attribution = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/attribution")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert data["portfolio_id"] == str(portfolio_id)
    assert data["portfolio_name"] == "Test Portfolio"
    assert "data_as_of" in data
    assert "computed_at" in data
    assert "categories" in data
    assert "summary" in data
    assert "returns_available" in data
    assert "benchmark_description" in data


def test_portfolio_attribution_response_includes_category_effects(client: TestClient) -> None:
    """Attribution response includes per-category Brinson effects."""
    portfolio_id = uuid.uuid4()
    expected = _make_attribution_response(portfolio_id)

    with patch("backend.routes.portfolio.BrinsonAttributionService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.compute_attribution = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/attribution")

    assert resp.status_code == 200
    data = resp.json()
    cats = data["categories"]
    assert len(cats) == 1
    cat = cats[0]
    assert cat["category_name"] == "Large Cap"
    assert "portfolio_weight" in cat
    assert "benchmark_weight" in cat
    assert "allocation_effect" in cat
    assert "selection_effect" in cat
    assert "interaction_effect" in cat
    assert "total_effect" in cat
    assert "provenance" in cat


def test_portfolio_attribution_response_includes_summary(client: TestClient) -> None:
    """Attribution response includes portfolio-level summary."""
    portfolio_id = uuid.uuid4()
    expected = _make_attribution_response(portfolio_id)

    with patch("backend.routes.portfolio.BrinsonAttributionService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.compute_attribution = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/attribution")

    assert resp.status_code == 200
    data = resp.json()
    summary = data["summary"]
    assert "total_allocation_effect" in summary
    assert "total_selection_effect" in summary
    assert "total_interaction_effect" in summary
    assert "total_active_return" in summary
    assert "formula" in summary
    assert "tolerance" in summary


def test_portfolio_attribution_response_includes_traceability_fields(
    client: TestClient,
) -> None:
    """Response must include formula + tolerance + data_as_of for traceability."""
    portfolio_id = uuid.uuid4()
    expected = _make_attribution_response(portfolio_id)

    with patch("backend.routes.portfolio.BrinsonAttributionService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.compute_attribution = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/attribution")

    assert resp.status_code == 200
    data = resp.json()

    # data_as_of must be present
    assert data["data_as_of"] is not None

    # formula and tolerance in summary
    summary = data["summary"]
    assert summary["formula"]
    assert "Brinson" in summary["formula"] or "brinson" in summary["formula"].lower()
    assert summary["tolerance"]


# ---------------------------------------------------------------------------
# Tests: 404
# ---------------------------------------------------------------------------


def test_portfolio_attribution_returns_404_for_unknown_portfolio(client: TestClient) -> None:
    """GET /{id}/attribution returns 404 when portfolio not found."""
    portfolio_id = uuid.uuid4()

    with patch("backend.routes.portfolio.BrinsonAttributionService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.compute_attribution = AsyncMock(
            side_effect=ValueError(f"Portfolio {portfolio_id} not found")
        )
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/attribution")

    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# Tests: graceful degradation
# ---------------------------------------------------------------------------


def test_portfolio_attribution_returns_available_false_when_no_nav_returns(
    client: TestClient,
) -> None:
    """When NAV returns unavailable, response still returns 200 with returns_available=False."""
    portfolio_id = uuid.uuid4()
    expected = _make_attribution_response(portfolio_id, returns_available=False, with_effects=False)

    with patch("backend.routes.portfolio.BrinsonAttributionService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.compute_attribution = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}/attribution")

    assert resp.status_code == 200
    data = resp.json()
    assert data["returns_available"] is False
    assert data["summary"]["total_active_return"] is None


# ---------------------------------------------------------------------------
# Tests: data_as_of query param
# ---------------------------------------------------------------------------


def test_portfolio_attribution_accepts_data_as_of_param(client: TestClient) -> None:
    """Attribution endpoint accepts data_as_of query param without error."""
    portfolio_id = uuid.uuid4()
    expected = _make_attribution_response(portfolio_id)

    with patch("backend.routes.portfolio.BrinsonAttributionService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.compute_attribution = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp = client.get(
            f"/api/v1/portfolio/{portfolio_id}/attribution",
            params={"data_as_of": "2026-04-14"},
        )

    assert resp.status_code == 200


def test_portfolio_attribution_invalid_date_returns_error(client: TestClient) -> None:
    """Invalid data_as_of returns 400 or 422 (validation error)."""
    portfolio_id = uuid.uuid4()

    resp = client.get(
        f"/api/v1/portfolio/{portfolio_id}/attribution",
        params={"data_as_of": "not-a-date"},
    )
    assert resp.status_code in (400, 422), (
        f"Invalid date should return 400 or 422, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Tests: determinism via API
# ---------------------------------------------------------------------------


def test_portfolio_attribution_is_deterministic_via_api(client: TestClient) -> None:
    """Same portfolio_id + data_as_of → same response."""
    portfolio_id = uuid.uuid4()
    expected = _make_attribution_response(portfolio_id)

    with patch("backend.routes.portfolio.BrinsonAttributionService") as MockSvc:
        mock_svc = MagicMock()
        mock_svc.compute_attribution = AsyncMock(return_value=expected)
        MockSvc.return_value = mock_svc

        resp1 = client.get(
            f"/api/v1/portfolio/{portfolio_id}/attribution",
            params={"data_as_of": "2026-04-14"},
        )
        resp2 = client.get(
            f"/api/v1/portfolio/{portfolio_id}/attribution",
            params={"data_as_of": "2026-04-14"},
        )

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    d1 = resp1.json()
    d2 = resp2.json()

    assert d1["summary"]["total_active_return"] == d2["summary"]["total_active_return"]
    assert d1["returns_available"] == d2["returns_available"]
    assert len(d1["categories"]) == len(d2["categories"])
