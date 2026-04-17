"""
Tests for GET /api/etf/{ticker}, /api/etf/{ticker}/chart-data, /api/etf/{ticker}/rs-history.
All JIP calls mocked -- no real DB required.
Tests placed in tests/routes/ (NOT tests/api/) per conftest-integration-marker-trap pattern.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.db.session import get_db

# Module-level patch path aliases
_ROUTE = "backend.routes.etf"
_SINGLE_MASTER = f"{_ROUTE}.etf_single_master"
_CHART_DATA = f"{_ROUTE}.etf_chart_data"
_RS_HISTORY = f"{_ROUTE}.etf_rs_history"
_TECH = f"{_ROUTE}.latest_etf_technicals"
_RS = f"{_ROUTE}.latest_etf_rs"
_GOLD_RS = f"{_ROUTE}._fetch_gold_rs_bulk"


# ---------------------------------------------------------------------------
# DB dependency override -- avoids real DB connection
# ---------------------------------------------------------------------------


async def _fake_db() -> Any:  # type: ignore[return]
    """Return a no-op async session mock."""
    yield MagicMock()


app.dependency_overrides[get_db] = _fake_db


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_MASTER: dict[str, Any] = {
    "ticker": "SPY",
    "name": "SPDR S&P 500 ETF Trust",
    "exchange": "NYSE",
    "country": "US",
    "currency": "USD",
    "sector": "Broad Market",
    "asset_class": "Equity",
    "category": "Blend",
    "benchmark": "S&P 500",
    "expense_ratio": "0.0945",
    "inception_date": datetime.date(1993, 1, 22),
    "is_active": True,
}

SAMPLE_TECH: dict[str, Any] = {
    "SPY": {
        "ticker": "SPY",
        "date": datetime.date(2026, 4, 17),
        "close_price": "525.50",
        "rsi_14": "55.5",
        "macd": "2.1",
        "macd_signal": "1.9",
        "macd_hist": "0.2",
        "bb_upper": "535.0",
        "bb_lower": "515.0",
        "sma_50": "510.0",
        "sma_200": "480.0",
    }
}

SAMPLE_RS: dict[str, Any] = {
    "SPY": {
        "ticker": "SPY",
        "date": datetime.date(2026, 4, 17),
        "rs_composite": "65.2",
        "rs_momentum": "48.7",
        "quadrant": "LEADING",
    }
}

SAMPLE_GOLD_RS: dict[str, Any] = {
    "SPY": {
        "entity_id": "SPY",
        "rs_vs_gold_1m": "3.5",
        "rs_vs_gold_3m": "7.2",
        "rs_vs_gold_6m": "11.0",
        "rs_vs_gold_12m": "15.8",
        "gold_rs_signal": "AMPLIFIES_BULL",
        "gold_series": "LBMA_USD",
        "computed_at": datetime.datetime(2026, 4, 17, 10, 0),
    }
}


def _make_chart_rows(n: int = 10) -> list[dict[str, Any]]:
    base_date = datetime.date(2025, 4, 17)
    rows = []
    for i in range(n):
        rows.append(
            {
                "date": base_date + datetime.timedelta(days=i),
                "open": "520.0",
                "high": "528.0",
                "low": "518.0",
                "close": "525.0",
                "volume": 50_000_000,
                "sma_50": "510.0",
                "sma_200": "480.0",
                "ema_20": "518.0",
                "rsi_14": "55.0",
                "macd_line": "2.1",
                "macd_signal": "1.9",
                "macd_histogram": "0.2",
                "bollinger_upper": "535.0",
                "bollinger_lower": "515.0",
                "adx_14": "28.0",
            }
        )
    return rows


def _make_rs_rows(n: int = 10) -> list[dict[str, Any]]:
    base_date = datetime.date(2025, 4, 17)
    return [
        {
            "date": base_date + datetime.timedelta(days=i * 7),
            "rs_composite": "65.2",
            "rs_momentum": "48.7",
            "quadrant": "LEADING",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# ETF Detail tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_returns_200_with_all_blocks(client: AsyncClient) -> None:
    """Mock master+tech+rs+gold_rs -> 200, check data fields."""
    with (
        patch(_SINGLE_MASTER, new=AsyncMock(return_value=SAMPLE_MASTER)),
        patch(_TECH, new=AsyncMock(return_value=SAMPLE_TECH)),
        patch(_RS, new=AsyncMock(return_value=SAMPLE_RS)),
        patch(_GOLD_RS, new=AsyncMock(return_value=SAMPLE_GOLD_RS)),
    ):
        resp = await client.get("/api/etf/SPY")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "_meta" in body
    data = body["data"]
    assert data["ticker"] == "SPY"
    assert data["name"] == "SPDR S&P 500 ETF Trust"
    assert data["country"] == "US"
    assert data["currency"] == "USD"
    assert data["rs"] is not None
    assert data["technicals"] is not None
    assert data["gold_rs"] is not None


@pytest.mark.asyncio
async def test_detail_returns_404_not_found(client: AsyncClient) -> None:
    """master returns None -> 404, code=ETF_NOT_FOUND."""
    with patch(_SINGLE_MASTER, new=AsyncMock(return_value=None)):
        resp = await client.get("/api/etf/UNKNOWN")

    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"]["code"] == "ETF_NOT_FOUND"


@pytest.mark.asyncio
async def test_detail_jip_error_returns_503(client: AsyncClient) -> None:
    """master raises OSError -> 503, code=JIP_UNAVAILABLE."""
    with patch(_SINGLE_MASTER, new=AsyncMock(side_effect=OSError("Connection refused"))):
        resp = await client.get("/api/etf/SPY")

    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"]["code"] == "JIP_UNAVAILABLE"


@pytest.mark.asyncio
async def test_detail_decimal_fields_not_float(client: AsyncClient) -> None:
    """expense_ratio and rs.rs_composite are serialized as strings (Decimal), not float."""
    with (
        patch(_SINGLE_MASTER, new=AsyncMock(return_value=SAMPLE_MASTER)),
        patch(_TECH, new=AsyncMock(return_value=SAMPLE_TECH)),
        patch(_RS, new=AsyncMock(return_value=SAMPLE_RS)),
        patch(_GOLD_RS, new=AsyncMock(return_value={})),
    ):
        resp = await client.get("/api/etf/SPY")

    assert resp.status_code == 200
    data = resp.json()["data"]
    if data.get("expense_ratio") is not None:
        assert isinstance(data["expense_ratio"], str), (
            f"expense_ratio should be str (Decimal), got {type(data['expense_ratio'])}"
        )
    if data.get("rs") and data["rs"].get("rs_composite") is not None:
        assert isinstance(data["rs"]["rs_composite"], str), "rs_composite should be str"


@pytest.mark.asyncio
async def test_detail_meta_envelope_present(client: AsyncClient) -> None:
    """Response has _meta with record_count=1 and data_as_of."""
    with (
        patch(_SINGLE_MASTER, new=AsyncMock(return_value=SAMPLE_MASTER)),
        patch(_TECH, new=AsyncMock(return_value={})),
        patch(_RS, new=AsyncMock(return_value={})),
        patch(_GOLD_RS, new=AsyncMock(return_value={})),
    ):
        resp = await client.get("/api/etf/SPY")

    assert resp.status_code == 200
    meta = resp.json()["_meta"]
    assert meta["record_count"] == 1
    assert meta["data_as_of"] is not None


# ---------------------------------------------------------------------------
# ETF Chart Data tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chart_data_returns_200_with_points(client: AsyncClient) -> None:
    """Mock chart_data rows -> 200, points list with correct count."""
    chart_rows = _make_chart_rows(10)
    with (
        patch(_SINGLE_MASTER, new=AsyncMock(return_value=SAMPLE_MASTER)),
        patch(_CHART_DATA, new=AsyncMock(return_value=chart_rows)),
    ):
        resp = await client.get(
            "/api/etf/SPY/chart-data",
            params={"from": "2025-04-17", "to": "2026-04-17"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "SPY"
    assert len(body["data"]) == 10
    assert body["_meta"]["record_count"] == 10
    # Check first point has expected fields
    pt = body["data"][0]
    assert "date" in pt
    assert "close" in pt
    assert "rsi_14" in pt


@pytest.mark.asyncio
async def test_chart_data_invalid_date_range(client: AsyncClient) -> None:
    """from >= to -> 400, code=INVALID_DATE_RANGE."""
    resp = await client.get(
        "/api/etf/SPY/chart-data",
        params={"from": "2026-01-01", "to": "2025-01-01"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"]["code"] == "INVALID_DATE_RANGE"


@pytest.mark.asyncio
async def test_chart_data_range_too_large(client: AsyncClient) -> None:
    """6-year range -> 400, code=DATE_RANGE_TOO_LARGE."""
    resp = await client.get(
        "/api/etf/SPY/chart-data",
        params={"from": "2018-01-01", "to": "2026-01-01"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"]["code"] == "DATE_RANGE_TOO_LARGE"


@pytest.mark.asyncio
async def test_chart_data_etf_not_found(client: AsyncClient) -> None:
    """master=None -> 404, code=ETF_NOT_FOUND."""
    with patch(_SINGLE_MASTER, new=AsyncMock(return_value=None)):
        resp = await client.get(
            "/api/etf/UNKNOWN/chart-data",
            params={"from": "2025-04-17", "to": "2026-04-17"},
        )
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"]["code"] == "ETF_NOT_FOUND"


@pytest.mark.asyncio
async def test_chart_data_jip_error_returns_503(client: AsyncClient) -> None:
    """Master raises RuntimeError -> 503, code=JIP_UNAVAILABLE."""
    with patch(_SINGLE_MASTER, new=AsyncMock(side_effect=RuntimeError("DB down"))):
        resp = await client.get(
            "/api/etf/SPY/chart-data",
            params={"from": "2025-04-17", "to": "2026-04-17"},
        )
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"]["code"] == "JIP_UNAVAILABLE"


@pytest.mark.asyncio
async def test_chart_data_default_1y_range(client: AsyncClient) -> None:
    """No from/to -> defaults to 1y range, response includes record_count in meta."""
    chart_rows = _make_chart_rows(252)
    with (
        patch(_SINGLE_MASTER, new=AsyncMock(return_value=SAMPLE_MASTER)),
        patch(_CHART_DATA, new=AsyncMock(return_value=chart_rows)),
    ):
        resp = await client.get("/api/etf/SPY/chart-data")

    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["record_count"] == 252
    assert len(body["data"]) == 252


@pytest.mark.asyncio
async def test_chart_data_decimal_fields_not_float(client: AsyncClient) -> None:
    """OHLCV and technical fields are strings (Decimal), not float."""
    chart_rows = _make_chart_rows(1)
    with (
        patch(_SINGLE_MASTER, new=AsyncMock(return_value=SAMPLE_MASTER)),
        patch(_CHART_DATA, new=AsyncMock(return_value=chart_rows)),
    ):
        resp = await client.get(
            "/api/etf/SPY/chart-data",
            params={"from": "2025-04-17", "to": "2026-04-17"},
        )

    assert resp.status_code == 200
    pt = resp.json()["data"][0]
    if pt.get("close") is not None:
        assert isinstance(pt["close"], str), f"close should be str, got {type(pt['close'])}"
    if pt.get("rsi_14") is not None:
        assert isinstance(pt["rsi_14"], str), "rsi_14 should be str"


# ---------------------------------------------------------------------------
# ETF RS History tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rs_history_returns_200_with_points(client: AsyncClient) -> None:
    """Mock rs rows -> 200, points with quadrant."""
    rs_rows = _make_rs_rows(10)
    with (
        patch(_SINGLE_MASTER, new=AsyncMock(return_value=SAMPLE_MASTER)),
        patch(_RS_HISTORY, new=AsyncMock(return_value=rs_rows)),
    ):
        resp = await client.get("/api/etf/SPY/rs-history?months=12")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "SPY"
    assert body["months"] == 12
    assert len(body["data"]) == 10
    assert body["_meta"]["record_count"] == 10
    # Verify quadrant field present
    pt = body["data"][0]
    assert "date" in pt
    assert "rs_composite" in pt
    assert "quadrant" in pt
    assert pt["quadrant"] == "LEADING"


@pytest.mark.asyncio
async def test_rs_history_etf_not_found(client: AsyncClient) -> None:
    """master=None -> 404, code=ETF_NOT_FOUND."""
    with patch(_SINGLE_MASTER, new=AsyncMock(return_value=None)):
        resp = await client.get("/api/etf/UNKNOWN/rs-history")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"]["code"] == "ETF_NOT_FOUND"


@pytest.mark.asyncio
async def test_rs_history_jip_error_returns_503(client: AsyncClient) -> None:
    """Master raises ConnectionError -> 503, code=JIP_UNAVAILABLE."""
    with patch(_SINGLE_MASTER, new=AsyncMock(side_effect=ConnectionError("Timeout"))):
        resp = await client.get("/api/etf/SPY/rs-history")
    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"]["code"] == "JIP_UNAVAILABLE"


@pytest.mark.asyncio
async def test_rs_history_default_12_months(client: AsyncClient) -> None:
    """No months param -> months=12 in response."""
    rs_rows = _make_rs_rows(5)
    with (
        patch(_SINGLE_MASTER, new=AsyncMock(return_value=SAMPLE_MASTER)),
        patch(_RS_HISTORY, new=AsyncMock(return_value=rs_rows)),
    ):
        resp = await client.get("/api/etf/SPY/rs-history")

    assert resp.status_code == 200
    body = resp.json()
    assert body["months"] == 12


@pytest.mark.asyncio
async def test_rs_history_empty_returns_empty_list(client: AsyncClient) -> None:
    """No RS data -> 200 with empty data list."""
    with (
        patch(_SINGLE_MASTER, new=AsyncMock(return_value=SAMPLE_MASTER)),
        patch(_RS_HISTORY, new=AsyncMock(return_value=[])),
    ):
        resp = await client.get("/api/etf/SPY/rs-history")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["_meta"]["record_count"] == 0


@pytest.mark.asyncio
async def test_rs_history_invalid_quadrant_is_none(client: AsyncClient) -> None:
    """Unknown quadrant value -> quadrant=None (no crash)."""
    rs_rows = [
        {
            "date": datetime.date(2025, 4, 17),
            "rs_composite": "55.0",
            "rs_momentum": "40.0",
            "quadrant": "UNKNOWN_JUNK",
        }
    ]
    with (
        patch(_SINGLE_MASTER, new=AsyncMock(return_value=SAMPLE_MASTER)),
        patch(_RS_HISTORY, new=AsyncMock(return_value=rs_rows)),
    ):
        resp = await client.get("/api/etf/SPY/rs-history")

    assert resp.status_code == 200
    pt = resp.json()["data"][0]
    assert pt["quadrant"] is None
