"""Route-level tests for GET /api/v1/screener — C-DER-2.

Uses ASGI transport + dependency_overrides[get_db].
Services are mocked to avoid real DB connections.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app


def _mock_db_session() -> AsyncMock:
    """Minimal mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Test 1: Basic 200 response with correct envelope shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_route_returns_200() -> None:
    """GET /api/v1/screener returns 200 with rows + meta envelope."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session
    try:
        with (
            patch("backend.routes.screener.JIPMarketService") as MockJIP,
            patch(
                "backend.routes.screener.compute_screener_bulk",
                new=AsyncMock(return_value=[]),
            ),
        ):
            MockJIP.return_value.get_market_regime = AsyncMock(return_value={"regime": "BULL"})
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/screener")
        assert response.status_code == 200
        data = response.json()
        assert "rows" in data, f"Response missing 'rows': {data}"
        assert "meta" in data, f"Response missing 'meta': {data}"
        assert isinstance(data["rows"], list)
        assert data["meta"]["record_count"] == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 2: Invalid universe → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_route_rejects_invalid_universe() -> None:
    """GET /api/v1/screener?universe=foo → 422 Unprocessable Entity."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/screener?universe=foo")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 3: universe=nifty50 passes through to filters dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_route_filters_universe_nifty50_passes_through() -> None:
    """GET /api/v1/screener?universe=nifty50 → 200, filters['universe']='nifty50'."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session
    captured_filters: dict = {}

    async def mock_compute(filters: dict, db: object) -> list:
        captured_filters.update(filters)
        return []

    try:
        with (
            patch("backend.routes.screener.JIPMarketService") as MockJIP,
            patch("backend.routes.screener.compute_screener_bulk", new=mock_compute),
        ):
            MockJIP.return_value.get_market_regime = AsyncMock(return_value={"regime": "BULL"})
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/screener?universe=nifty50")
        assert response.status_code == 200
        assert captured_filters.get("universe") == "nifty50"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 4: Invalid conviction value → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_route_rejects_invalid_conviction() -> None:
    """GET /api/v1/screener?conviction=UNKNOWN → 422."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/screener?conviction=UNKNOWN")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 5: Invalid action value → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_route_rejects_invalid_action() -> None:
    """GET /api/v1/screener?action=NOTREAL → 422."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/screener?action=NOTREAL")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 6: limit > 200 → 422 (FastAPI Query validation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_route_rejects_limit_over_200() -> None:
    """GET /api/v1/screener?limit=201 → 4xx (FastAPI Query ge/le validation).

    The UQL error handler may convert 422 to 400; either is acceptable.
    """
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/screener?limit=201")
        assert response.status_code in (400, 422), (
            f"Expected 400 or 422 for limit=201, got {response.status_code}"
        )
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 7: Regime fetch failure is handled gracefully (defaults to SIDEWAYS)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screener_route_handles_regime_failure_gracefully() -> None:
    """Regime service raising an exception → 200, regime defaults to SIDEWAYS."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session
    captured_filters: dict = {}

    async def mock_compute(filters: dict, db: object) -> list:
        captured_filters.update(filters)
        return []

    try:
        with (
            patch("backend.routes.screener.JIPMarketService") as MockJIP,
            patch("backend.routes.screener.compute_screener_bulk", new=mock_compute),
        ):
            MockJIP.return_value.get_market_regime = AsyncMock(
                side_effect=OSError("DB connection error")
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/screener")
        assert response.status_code == 200
        assert captured_filters.get("regime") == "SIDEWAYS"
    finally:
        app.dependency_overrides.pop(get_db, None)
