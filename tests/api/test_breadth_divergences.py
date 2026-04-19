"""Tests for GET /api/v1/stocks/breadth/divergences (V2FE-1a).

Uses ASGITransport + AsyncClient so no live backend required.
Mocks detect_divergences and get_db to isolate from DB.
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

_SAMPLE_DIVERGENCE_RESULT: dict[str, Any] = {
    "divergences": [
        {
            "start_date": "2025-01-02",
            "end_date": "2025-01-23",
            "type": "bearish",
            "index_change_pct": Decimal("2.5000"),
            "breadth_change_pct": Decimal("-15.0000"),
        }
    ],
    "_meta": {
        "data_as_of": "2025-01-23",
        "insufficient_data": False,
        "record_count": 1,
        "query_ms": 45,
        "source": "de_bhavcopy_eq",
    },
}

_EMPTY_DIVERGENCE_RESULT: dict[str, Any] = {
    "divergences": [],
    "_meta": {
        "data_as_of": "2025-01-23",
        "insufficient_data": True,
        "record_count": 0,
        "query_ms": 12,
        "source": "de_bhavcopy_eq",
        "reason": "Index price data unavailable from de_index_daily",
    },
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breadth_divergences_returns_200(client: AsyncClient) -> None:
    """Route returns 200 when detect_divergences succeeds."""
    with patch(
        "backend.routes.breadth.detect_divergences",
        new=AsyncMock(return_value=_SAMPLE_DIVERGENCE_RESULT),
    ):
        resp = await client.get("/api/v1/stocks/breadth/divergences")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_breadth_divergences_empty_when_jip_sparse(client: AsyncClient) -> None:
    """Returns 200 with data=[] and insufficient_data=True when JIP has no index data."""
    with patch(
        "backend.routes.breadth.detect_divergences",
        new=AsyncMock(return_value=_EMPTY_DIVERGENCE_RESULT),
    ):
        resp = await client.get("/api/v1/stocks/breadth/divergences?universe=nifty500")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["_meta"]["insufficient_data"] is True


@pytest.mark.asyncio
async def test_breadth_divergences_response_schema(client: AsyncClient) -> None:
    """Response always has 'data' and '_meta' keys with required fields."""
    with patch(
        "backend.routes.breadth.detect_divergences",
        new=AsyncMock(return_value=_SAMPLE_DIVERGENCE_RESULT),
    ):
        resp = await client.get("/api/v1/stocks/breadth/divergences")
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
async def test_breadth_divergences_data_contains_divergence_fields(client: AsyncClient) -> None:
    """When divergences exist, each has start_date, end_date, and type."""
    with patch(
        "backend.routes.breadth.detect_divergences",
        new=AsyncMock(return_value=_SAMPLE_DIVERGENCE_RESULT),
    ):
        resp = await client.get("/api/v1/stocks/breadth/divergences")
    body = resp.json()
    assert len(body["data"]) == 1
    div = body["data"][0]
    assert "start_date" in div
    assert "end_date" in div
    assert "type" in div
    assert div["type"] in ("bullish", "bearish")


@pytest.mark.asyncio
async def test_breadth_divergences_fault_tolerant_on_error(client: AsyncClient) -> None:
    """Never returns 500 even when detect_divergences raises."""
    with patch(
        "backend.routes.breadth.detect_divergences",
        new=AsyncMock(side_effect=RuntimeError("DB connection lost")),
    ):
        resp = await client.get("/api/v1/stocks/breadth/divergences")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert "_meta" in body


@pytest.mark.asyncio
async def test_breadth_divergences_default_universe_is_nifty500(client: AsyncClient) -> None:
    """Default universe is nifty500 when not provided."""
    with patch(
        "backend.routes.breadth.detect_divergences",
        new=AsyncMock(return_value=_EMPTY_DIVERGENCE_RESULT),
    ):
        resp = await client.get("/api/v1/stocks/breadth/divergences")
    body = resp.json()
    assert body["_meta"]["universe"] == "nifty500"


@pytest.mark.asyncio
async def test_breadth_divergences_custom_params_passed_through(client: AsyncClient) -> None:
    """Custom universe and lookback_days params are reflected in _meta."""
    with patch(
        "backend.routes.breadth.detect_divergences",
        new=AsyncMock(return_value=_EMPTY_DIVERGENCE_RESULT),
    ):
        resp = await client.get(
            "/api/v1/stocks/breadth/divergences?universe=nifty50&lookback_days=90"
        )
    body = resp.json()
    meta = body["_meta"]
    assert meta["universe"] == "nifty50"
    assert meta["lookback_days"] == 90
