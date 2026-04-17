"""Route tests for GET /api/v1/sectors/rrg (C-DER-3).

Uses ASGI transport + dependency_overrides[get_db].
Mocks compute_sector_rrg at the route module level.

Also includes non-regression test for GET /api/v1/stocks/sectors to verify
the new /sectors prefix does not shadow the existing stocks/sectors route.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app
from backend.models.schemas import (
    Quadrant,
    ResponseMeta,
    RRGPoint,
    RRGResponse,
    RRGSector,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TODAY = datetime.date(2026, 4, 17)

_RRG_RESPONSE_FIXTURE = RRGResponse(
    sectors=[
        RRGSector(
            sector="Technology",
            rs_score=Decimal("108.5"),
            rs_momentum=Decimal("3.2"),
            quadrant=Quadrant.LEADING,
            pct_above_50dma=Decimal("72.0"),
            breadth_regime="BULL",
            tail=[
                RRGPoint(
                    date=_TODAY,
                    rs_score=Decimal("108.5"),
                    rs_momentum=Decimal("3.2"),
                ),
                RRGPoint(
                    date=_TODAY - datetime.timedelta(days=7),
                    rs_score=Decimal("105.3"),
                    rs_momentum=Decimal("2.1"),
                ),
            ],
        ),
        RRGSector(
            sector="Banking",
            rs_score=Decimal("94.2"),
            rs_momentum=Decimal("-2.1"),
            quadrant=Quadrant.LAGGING,
            pct_above_50dma=Decimal("38.0"),
            breadth_regime="BEAR",
            tail=[],
        ),
    ],
    mean_rs=Decimal("100.0"),
    stddev_rs=Decimal("5.0"),
    as_of=_TODAY,
    meta=ResponseMeta(record_count=2, query_ms=25),
)


def _mock_db_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Test: GET /api/v1/sectors/rrg → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sectors_rrg_route_200() -> None:
    """GET /api/v1/sectors/rrg → 200 with sectors/mean_rs/stddev_rs/as_of/meta."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    try:
        with patch(
            "backend.routes.sectors.compute_sector_rrg",
            new=AsyncMock(return_value=_RRG_RESPONSE_FIXTURE),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/sectors/rrg")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()

    # Required keys
    assert "sectors" in body, "Response must contain 'sectors'"
    assert "mean_rs" in body, "Response must contain 'mean_rs'"
    assert "stddev_rs" in body, "Response must contain 'stddev_rs'"
    assert "as_of" in body, "Response must contain 'as_of'"
    assert "meta" in body, "Response must contain 'meta'"

    # Sectors structure
    assert len(body["sectors"]) == 2

    tech = next(s for s in body["sectors"] if s["sector"] == "Technology")
    assert "rs_score" in tech
    assert "rs_momentum" in tech
    assert "quadrant" in tech
    assert tech["quadrant"] == "LEADING"
    assert len(tech["tail"]) == 2

    # Mean/stddev values
    assert float(body["mean_rs"]) == 100.0
    assert float(body["stddev_rs"]) == 5.0
    assert body["as_of"] == "2026-04-17"


@pytest.mark.asyncio
async def test_sectors_rrg_route_with_benchmark_param() -> None:
    """GET /api/v1/sectors/rrg?benchmark=NIFTY+500 → 200 (parameter is accepted)."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    try:
        with patch(
            "backend.routes.sectors.compute_sector_rrg",
            new=AsyncMock(return_value=_RRG_RESPONSE_FIXTURE),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/v1/sectors/rrg", params={"benchmark": "NIFTY 500"}
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_sectors_rrg_route_503_when_service_raises() -> None:
    """When compute_sector_rrg raises 503, route propagates 503."""
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    try:
        with patch(
            "backend.routes.sectors.compute_sector_rrg",
            new=AsyncMock(side_effect=HTTPException(503, detail="Sector RS data not available")),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/sectors/rrg")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Non-regression: GET /api/v1/stocks/sectors still works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_existing_stocks_sectors_route_still_works() -> None:
    """GET /api/v1/stocks/sectors → 200 (non-regression after adding /api/v1/sectors/rrg).

    Verifies the new sectors router does not shadow or break the existing
    stocks/sectors list route which returns SectorListResponse.
    """
    session = _mock_db_session()
    app.dependency_overrides[get_db] = lambda: session

    # Mock the JIPDataService to avoid real DB calls
    sector_data: list[dict] = [
        {
            "sector": "Technology",
            "stock_count": 45,
            "avg_rs_composite": 1.15,
            "avg_rs_momentum": 0.05,
            "sector_quadrant": "LEADING",
            "pct_above_200dma": 72.0,
            "pct_above_50dma": 68.0,
            "pct_above_ema21": 71.0,
            "avg_rsi_14": 58.0,
            "pct_rsi_overbought": 12.0,
            "pct_rsi_oversold": 3.0,
            "avg_adx": 26.0,
            "pct_adx_trending": 42.0,
            "pct_macd_bullish": 55.0,
            "pct_roc5_positive": 60.0,
            "avg_beta": 1.1,
            "avg_sharpe": 0.8,
            "avg_sortino": None,
            "avg_volatility_20d": None,
            "avg_max_dd": None,
            "avg_calmar": None,
            "avg_mf_holders": 280.0,
            "avg_disparity_20": 2.5,
        }
    ]

    try:
        with patch("backend.routes.stocks.JIPDataService") as MockJIP:
            mock_svc = AsyncMock()
            mock_svc.get_sector_metrics.return_value = sector_data
            MockJIP.return_value = mock_svc

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/stocks/sectors")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, (
        f"stocks/sectors must return 200 (non-regression). "
        f"Got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "sectors" in body, "stocks/sectors must return sectors key"
    assert "meta" in body, "stocks/sectors must return meta key"
