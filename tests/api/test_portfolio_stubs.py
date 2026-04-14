"""Tests for V4 Portfolio route stubs.

Verifies:
- Routes are registered (not 404/405)
- Stub routes return 501 Not Implemented
- Wired routes (list, create, get) return 200/201 or appropriate errors
- No 500 server errors on any route
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app


# ---------------------------------------------------------------------------
# Test client setup (no real DB — mock session)
# ---------------------------------------------------------------------------


def _make_mock_session() -> MagicMock:
    """Create a mock async session that doesn't hit real DB."""
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
    """TestClient with get_db dependency overridden."""
    from backend.db.session import get_db

    mock_session = _make_mock_session()

    async def override_get_db() -> Any:
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Stub route tests (501)
# ---------------------------------------------------------------------------


def test_import_cams_returns_501(client: TestClient) -> None:
    """POST /api/v1/portfolio/import-cams must return 501 Not Implemented."""
    resp = client.post("/api/v1/portfolio/import-cams")
    assert resp.status_code == 501, f"Expected 501, got {resp.status_code}: {resp.text}"


def test_update_portfolio_returns_501(client: TestClient) -> None:
    """PUT /api/v1/portfolio/{id} must return 501 Not Implemented."""
    portfolio_id = str(uuid.uuid4())
    resp = client.put(f"/api/v1/portfolio/{portfolio_id}")
    assert resp.status_code == 501, f"Expected 501, got {resp.status_code}: {resp.text}"


def test_get_portfolio_analysis_returns_501(client: TestClient) -> None:
    """GET /api/v1/portfolio/{id}/analysis must return 501 Not Implemented."""
    portfolio_id = str(uuid.uuid4())
    resp = client.get(f"/api/v1/portfolio/{portfolio_id}/analysis")
    assert resp.status_code == 501, f"Expected 501, got {resp.status_code}: {resp.text}"


def test_get_portfolio_attribution_returns_501(client: TestClient) -> None:
    """GET /api/v1/portfolio/{id}/attribution must return 501 Not Implemented."""
    portfolio_id = str(uuid.uuid4())
    resp = client.get(f"/api/v1/portfolio/{portfolio_id}/attribution")
    assert resp.status_code == 501, f"Expected 501, got {resp.status_code}: {resp.text}"


def test_get_portfolio_optimize_returns_501(client: TestClient) -> None:
    """GET /api/v1/portfolio/{id}/optimize must return 501 Not Implemented."""
    portfolio_id = str(uuid.uuid4())
    resp = client.get(f"/api/v1/portfolio/{portfolio_id}/optimize")
    assert resp.status_code == 501, f"Expected 501, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Route registration tests (routes must not 404 or 405)
# ---------------------------------------------------------------------------


def test_routes_not_404() -> None:
    """All portfolio routes must be registered (not 404)."""
    from backend.main import app as _app

    routes = [r.path for r in _app.routes]  # type: ignore[attr-defined]
    portfolio_routes = [r for r in routes if "portfolio" in r]
    assert len(portfolio_routes) >= 5, (
        f"Expected at least 5 portfolio routes, found: {portfolio_routes}"
    )


def test_import_cams_route_registered() -> None:
    """POST /api/v1/portfolio/import-cams route must be in app routes."""
    from backend.main import app as _app

    paths = [r.path for r in _app.routes]  # type: ignore[attr-defined]
    assert "/api/v1/portfolio/import-cams" in paths, f"import-cams not in routes: {paths}"


def test_create_route_registered() -> None:
    """POST /api/v1/portfolio/create route must be in app routes."""
    from backend.main import app as _app

    paths = [r.path for r in _app.routes]  # type: ignore[attr-defined]
    assert "/api/v1/portfolio/create" in paths, f"create not in routes: {paths}"


# ---------------------------------------------------------------------------
# List portfolios — returns empty list when no portfolios exist
# ---------------------------------------------------------------------------


def test_list_portfolios_returns_200_empty(client: TestClient) -> None:
    """GET /api/v1/portfolio/ must return 200 with empty list when no portfolios."""
    # Mock the repo to return empty list
    with patch("backend.routes.portfolio.PortfolioRepo") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.list_portfolios = AsyncMock(return_value=[])
        MockRepo.return_value = mock_repo

        resp = client.get("/api/v1/portfolio/")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "portfolios" in data
    assert data["portfolios"] == []
    assert data["count"] == 0


# ---------------------------------------------------------------------------
# Get portfolio — 404 when not found
# ---------------------------------------------------------------------------


def test_get_portfolio_returns_404_when_not_found(client: TestClient) -> None:
    """GET /api/v1/portfolio/{id} must return 404 when portfolio does not exist."""
    portfolio_id = str(uuid.uuid4())

    with patch("backend.routes.portfolio.PortfolioRepo") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.get_portfolio = AsyncMock(return_value=None)
        MockRepo.return_value = mock_repo

        resp = client.get(f"/api/v1/portfolio/{portfolio_id}")

    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "detail" in data


# ---------------------------------------------------------------------------
# Create portfolio — validation errors
# ---------------------------------------------------------------------------


def test_create_portfolio_invalid_body_returns_400(client: TestClient) -> None:
    """POST /api/v1/portfolio/create must return 400 for invalid request body.

    The global §20.5 error handler converts Pydantic 422 → 400 with an
    INVALID_REQUEST envelope per spec §20.5.
    """
    resp = client.post(
        "/api/v1/portfolio/create",
        json={"portfolio_type": "invalid_type", "owner_type": "retail"},
    )
    # §20.5 error handler converts validation errors to 400
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_REQUEST"


def test_create_portfolio_missing_required_fields_returns_400(client: TestClient) -> None:
    """POST /api/v1/portfolio/create must return 400 when required fields missing.

    The global §20.5 error handler converts Pydantic 422 → 400.
    """
    resp = client.post("/api/v1/portfolio/create", json={})
    # §20.5 error handler converts validation errors to 400
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "error" in data


# ---------------------------------------------------------------------------
# No 500 errors on any stub route
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/portfolio/import-cams"),
        ("GET", "/api/v1/portfolio/"),
        ("GET", f"/api/v1/portfolio/{uuid.uuid4()}/analysis"),
        ("GET", f"/api/v1/portfolio/{uuid.uuid4()}/attribution"),
        ("GET", f"/api/v1/portfolio/{uuid.uuid4()}/optimize"),
        ("PUT", f"/api/v1/portfolio/{uuid.uuid4()}"),
    ],
)
def test_no_500_errors(client: TestClient, method: str, path: str) -> None:
    """No portfolio route must return 500 Internal Server Error."""
    with patch("backend.routes.portfolio.PortfolioRepo") as MockRepo:
        mock_repo = MagicMock()
        mock_repo.list_portfolios = AsyncMock(return_value=[])
        mock_repo.get_portfolio = AsyncMock(return_value=None)
        MockRepo.return_value = mock_repo

        resp = client.request(method, path)

    assert resp.status_code != 500, f"{method} {path} returned 500: {resp.text}"
