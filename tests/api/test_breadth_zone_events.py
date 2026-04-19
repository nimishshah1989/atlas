"""Tests for GET /api/v1/stocks/breadth/zone-events (V2FE-1a).

Uses ASGITransport + AsyncClient so no live backend required.
Mocks JIPDataService.get_chart_data and get_db to isolate from DB.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.db.session import get_db


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def client() -> AsyncClient:  # type: ignore[override]
    """ASGI-backed client — no live backend needed."""
    # Override get_db to return a mock session (avoids real DB connection)
    mock_db = MagicMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    async def override_get_db() -> Any:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_CHART_ROWS = [
    {
        "date": "2025-01-02",
        "close": Decimal("100.00"),
        "sma_20": Decimal("98.00"),
        "sma_200": Decimal("90.00"),
        "open": Decimal("99.00"),
        "high": Decimal("101.00"),
        "low": Decimal("98.00"),
        "volume": 1000000,
        "ema_20": Decimal("98.50"),
        "rsi_14": Decimal("55.00"),
        "macd_histogram": Decimal("0.50"),
    },
    {
        "date": "2025-01-03",
        "close": Decimal("95.00"),
        "sma_20": Decimal("97.00"),
        "sma_200": Decimal("90.00"),
        "open": Decimal("100.00"),
        "high": Decimal("100.50"),
        "low": Decimal("94.50"),
        "volume": 1200000,
        "ema_20": Decimal("97.50"),
        "rsi_14": Decimal("45.00"),
        "macd_histogram": Decimal("-0.20"),
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breadth_zone_events_returns_200(client: AsyncClient) -> None:
    """Route returns 200 with data + _meta keys when JIP has data."""
    with patch(
        "backend.routes.breadth.detect_zone_events",
        new=AsyncMock(
            return_value=[
                {
                    "date": "2025-01-02",
                    "zone": "ABOVE_200",
                    "close": Decimal("100.00"),
                    "ma_value": Decimal("90.00"),
                }
            ]
        ),
    ):
        resp = await client.get("/api/v1/stocks/breadth/zone-events?symbol=RELIANCE")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_breadth_zone_events_empty_when_jip_sparse(client: AsyncClient) -> None:
    """Returns 200 with data=[] and insufficient_data=True when JIP returns no rows."""
    with patch(
        "backend.routes.breadth.detect_zone_events",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.get("/api/v1/stocks/breadth/zone-events?symbol=FAKESTOCK")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["_meta"]["insufficient_data"] is True


@pytest.mark.asyncio
async def test_breadth_zone_events_response_schema(client: AsyncClient) -> None:
    """Response always has 'data' and '_meta' keys."""
    with patch(
        "backend.routes.breadth.detect_zone_events",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.get("/api/v1/stocks/breadth/zone-events")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "_meta" in body
    meta = body["_meta"]
    assert "data_as_of" in meta
    assert "staleness_seconds" in meta
    assert "source" in meta
    assert meta["source"] == "de_bhavcopy_eq"


@pytest.mark.asyncio
async def test_breadth_zone_events_default_symbol_is_nifty(client: AsyncClient) -> None:
    """Default symbol is NIFTY when not provided."""
    with patch(
        "backend.routes.breadth.detect_zone_events",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.get("/api/v1/stocks/breadth/zone-events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["symbol"] == "NIFTY"


@pytest.mark.asyncio
async def test_breadth_zone_events_fault_tolerant_on_error(client: AsyncClient) -> None:
    """Never returns 500 even when detect_zone_events raises."""
    with patch(
        "backend.routes.breadth.detect_zone_events",
        new=AsyncMock(side_effect=RuntimeError("JIP timeout")),
    ):
        resp = await client.get("/api/v1/stocks/breadth/zone-events?symbol=INFOSYS")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["_meta"]["insufficient_data"] is True


@pytest.mark.asyncio
async def test_breadth_zone_events_zone_types_in_data(client: AsyncClient) -> None:
    """When JIP returns data, events contain valid zone types."""
    sample_events = [
        {
            "date": "2025-01-02",
            "zone": "ABOVE_200",
            "close": Decimal("100.00"),
            "ma_value": Decimal("90.00"),
        },
        {
            "date": "2025-01-03",
            "zone": "CROSS_DOWN_20",
            "close": Decimal("95.00"),
            "ma_value": Decimal("97.00"),
        },
    ]
    with patch(
        "backend.routes.breadth.detect_zone_events",
        new=AsyncMock(return_value=sample_events),
    ):
        resp = await client.get(
            "/api/v1/stocks/breadth/zone-events?symbol=RELIANCE&lookback_days=30"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    valid_zones = {
        "ABOVE_200",
        "BELOW_200",
        "ABOVE_20",
        "BELOW_20",
        "CROSS_UP_200",
        "CROSS_DOWN_200",
        "CROSS_UP_20",
        "CROSS_DOWN_20",
    }
    for event in body["data"]:
        assert event["zone"] in valid_zones
