"""Tests for GET /api/v1/mf/{mstar_id}/weighted-technicals?include=conviction_series (V2FE-1c).

Tests: include=conviction_series adds the conviction_series key; without include,
conviction_series is absent.

Uses ASGITransport + mocked JIPDataService to avoid live DB.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app

_JIP_MOD = "backend.routes.mf.JIPDataService"
_MF_ID = "F00000XYZZ"


def _fresh_freshness() -> dict[str, Any]:
    return {"nav_as_of": datetime.date.today()}


def _weighted_technicals_row() -> dict[str, Any]:
    return {
        "mstar_id": _MF_ID,
        "as_of_date": datetime.date.today(),
        "weighted_rsi": Decimal("55.0"),
        "weighted_breadth_pct_above_200dma": Decimal("60.0"),
        "weighted_macd_bullish_pct": Decimal("45.0"),
    }


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


def _mock_svc(conviction_rows: list[dict[str, Any]] | None = None) -> MagicMock:
    """Build a mock JIPDataService that returns canned data."""
    svc = MagicMock()
    svc.get_mf_data_freshness = AsyncMock(return_value=_fresh_freshness())
    svc.get_fund_weighted_technicals = AsyncMock(return_value=_weighted_technicals_row())
    return svc


# ---------------------------------------------------------------------------
# Tests: basic response shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weighted_technicals_returns_200(client: AsyncClient) -> None:
    """GET weighted-technicals returns 200."""
    with patch(_JIP_MOD, return_value=_mock_svc()):
        resp = await client.get(f"/api/v1/mf/{_MF_ID}/weighted-technicals")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_weighted_technicals_has_mstar_id(client: AsyncClient) -> None:
    """Response contains mstar_id field."""
    with patch(_JIP_MOD, return_value=_mock_svc()):
        resp = await client.get(f"/api/v1/mf/{_MF_ID}/weighted-technicals")
    body = resp.json()
    assert body["mstar_id"] == _MF_ID


@pytest.mark.asyncio
async def test_weighted_technicals_no_include_omits_conviction_series(client: AsyncClient) -> None:
    """Without include param, conviction_series is absent from response."""
    with patch(_JIP_MOD, return_value=_mock_svc()):
        resp = await client.get(f"/api/v1/mf/{_MF_ID}/weighted-technicals")
    body = resp.json()
    assert "conviction_series" not in body or body["conviction_series"] is None


@pytest.mark.asyncio
async def test_weighted_technicals_has_staleness(client: AsyncClient) -> None:
    """Response always contains staleness block."""
    with patch(_JIP_MOD, return_value=_mock_svc()):
        resp = await client.get(f"/api/v1/mf/{_MF_ID}/weighted-technicals")
    body = resp.json()
    assert "staleness" in body


@pytest.mark.asyncio
async def test_weighted_technicals_has_data_as_of(client: AsyncClient) -> None:
    """Response contains data_as_of field."""
    with patch(_JIP_MOD, return_value=_mock_svc()):
        resp = await client.get(f"/api/v1/mf/{_MF_ID}/weighted-technicals")
    body = resp.json()
    assert "data_as_of" in body


# ---------------------------------------------------------------------------
# Tests: include=conviction_series
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weighted_technicals_include_conviction_series_key_present(
    client: AsyncClient,
) -> None:
    """include=conviction_series adds conviction_series key to response."""
    mock_db = MagicMock()
    # Mock the db.execute for conviction_series query
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [
        {"date": "2026-04-12", "signal": "BULLISH", "entity_id": _MF_ID}
    ]
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def override_get_db() -> Any:
        yield mock_db

    # Re-override dependency on the app directly (fixture overrides basic mock_db)
    app.dependency_overrides[get_db] = override_get_db

    with patch(_JIP_MOD, return_value=_mock_svc()):
        resp = await client.get(
            f"/api/v1/mf/{_MF_ID}/weighted-technicals?include=conviction_series"
        )
    body = resp.json()
    assert resp.status_code == 200
    assert "conviction_series" in body


@pytest.mark.asyncio
async def test_weighted_technicals_conviction_series_empty_when_no_rows(
    client: AsyncClient,
) -> None:
    """conviction_series is [] when atlas_gold_rs_cache has no MF rows."""
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def override_get_db() -> Any:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    with patch(_JIP_MOD, return_value=_mock_svc()):
        resp = await client.get(
            f"/api/v1/mf/{_MF_ID}/weighted-technicals?include=conviction_series"
        )
    body = resp.json()
    assert resp.status_code == 200
    assert body.get("conviction_series") == []


@pytest.mark.asyncio
async def test_weighted_technicals_conviction_series_fault_tolerant(
    client: AsyncClient,
) -> None:
    """conviction_series returns [] even if DB query raises an exception."""
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=Exception("table does not exist"))

    async def override_get_db() -> Any:
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    with patch(_JIP_MOD, return_value=_mock_svc()):
        resp = await client.get(
            f"/api/v1/mf/{_MF_ID}/weighted-technicals?include=conviction_series"
        )
    body = resp.json()
    assert resp.status_code == 200
    assert body.get("conviction_series") == []
