"""
Tests for GET /api/etf/universe.
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

# Module-level path aliases to keep patch() calls under 100 chars
_SVC = "backend.services.etf_service"
_MASTERS = f"{_SVC}.etf_master_rows"
_TECH = f"{_SVC}.latest_etf_technicals"
_RS = f"{_SVC}.latest_etf_rs"
_GOLD_RS = f"{_SVC}._fetch_gold_rs_bulk"


# ---------------------------------------------------------------------------
# DB dependency override -- avoids real DB connection
# ---------------------------------------------------------------------------


async def _fake_db() -> Any:  # type: ignore[return]
    """Return a no-op async session mock."""
    yield MagicMock()


app.dependency_overrides[get_db] = _fake_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_masters() -> list[dict[str, Any]]:
    """100 sample ETF master rows (mocked, no real DB)."""
    rows = []
    for i in range(100):
        rows.append(
            {
                "ticker": f"ETF{i:03d}",
                "name": f"Sample ETF {i}",
                "country": "US",
                "currency": "USD",
                "sector": "Broad Market",
                "category": "Blend",
                "benchmark": "S&P 500",
                "expense_ratio": "0.0945",
                "inception_date": datetime.date(2000, 1, 1),
                "is_active": True,
            }
        )
    return rows


@pytest.fixture
def sample_tech(sample_masters: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        m["ticker"]: {
            "ticker": m["ticker"],
            "date": datetime.date(2026, 4, 17),
            "close_price": "550.00",
            "volume": "1000000",
            "rsi_14": "55.5",
            "macd": "2.1",
            "macd_signal": "1.9",
            "macd_hist": "0.2",
            "bb_upper": "560.0",
            "bb_middle": "540.0",
            "bb_lower": "520.0",
            "bb_width": "40.0",
            "sma_20": "545.0",
            "sma_50": "530.0",
            "sma_200": "500.0",
            "ema_9": "548.0",
            "ema_21": "542.0",
            "adx_14": "25.0",
            "di_plus": "22.0",
            "di_minus": "18.0",
            "stoch_k": "65.0",
            "stoch_d": "60.0",
            "atr_14": "12.5",
            "obv": "50000000",
            "vwap": "548.5",
            "mom_10": "8.5",
            "roc_10": "1.5",
            "cci_20": "95.0",
            "wpr_14": "-35.0",
            "cmf_20": "0.15",
        }
        for m in sample_masters
    }


@pytest.fixture
def sample_rs(sample_masters: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        m["ticker"]: {
            "ticker": m["ticker"],
            "date": datetime.date(2026, 4, 17),
            "rs_composite": "75.5",
            "rs_momentum": "62.3",
            "quadrant": "LEADING",
        }
        for m in sample_masters
    }


@pytest.fixture
def sample_gold_rs(sample_masters: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        m["ticker"]: {
            "entity_id": m["ticker"],
            "rs_vs_gold_1m": "5.2",
            "rs_vs_gold_3m": "8.1",
            "rs_vs_gold_6m": "12.5",
            "rs_vs_gold_12m": "18.7",
            "gold_rs_signal": "AMPLIFIES_BULL",
            "gold_series": "LBMA_USD",
            "computed_at": datetime.datetime(2026, 4, 17, 10, 30),
        }
        for m in sample_masters
    }


@pytest_asyncio.fixture
async def client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_universe_returns_us_etfs(
    client: AsyncClient,
    sample_masters: list[dict[str, Any]],
    sample_tech: dict[str, dict[str, Any]],
) -> None:
    """country=US -> >=100 rows returned."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    with (
        patch(_MASTERS, new=AsyncMock(return_value=sample_masters)),
        patch(_TECH, new=AsyncMock(return_value=sample_tech)),
        patch(_RS, new=AsyncMock(return_value={})),
    ):
        resp = await client.get("/api/etf/universe?country=US")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 100
    assert body["_meta"]["record_count"] >= 100


@pytest.mark.asyncio
async def test_universe_no_duplicate_ticker(
    client: AsyncClient,
    sample_masters: list[dict[str, Any]],
    sample_tech: dict[str, dict[str, Any]],
) -> None:
    """Assert no duplicate tickers in response."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    with (
        patch(_MASTERS, new=AsyncMock(return_value=sample_masters)),
        patch(_TECH, new=AsyncMock(return_value=sample_tech)),
        patch(_RS, new=AsyncMock(return_value={})),
    ):
        resp = await client.get("/api/etf/universe")

    assert resp.status_code == 200
    tickers = [r["ticker"] for r in resp.json()["data"]]
    assert len(tickers) == len(set(tickers)), "Duplicate tickers in response"


@pytest.mark.asyncio
async def test_universe_include_technicals_adds_block(
    client: AsyncClient,
    sample_masters: list[dict[str, Any]],
    sample_tech: dict[str, dict[str, Any]],
) -> None:
    """include=technicals -> technicals block present with RSI/MACD/Bollinger/ADX."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    with (
        patch(_MASTERS, new=AsyncMock(return_value=sample_masters)),
        patch(_TECH, new=AsyncMock(return_value=sample_tech)),
        patch(_RS, new=AsyncMock(return_value={})),
    ):
        resp = await client.get("/api/etf/universe?include=technicals")

    assert resp.status_code == 200
    row = resp.json()["data"][0]
    assert row["technicals"] is not None
    assert "rsi_14" in row["technicals"]
    assert "macd" in row["technicals"]
    assert "bb_upper" in row["technicals"]
    assert "adx_14" in row["technicals"]


@pytest.mark.asyncio
async def test_universe_include_rs_adds_rs_fields(
    client: AsyncClient,
    sample_masters: list[dict[str, Any]],
    sample_tech: dict[str, dict[str, Any]],
    sample_rs: dict[str, dict[str, Any]],
) -> None:
    """include=rs -> rs block with rs_composite (Decimal), quadrant."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    with (
        patch(_MASTERS, new=AsyncMock(return_value=sample_masters)),
        patch(_TECH, new=AsyncMock(return_value={})),
        patch(_RS, new=AsyncMock(return_value=sample_rs)),
    ):
        resp = await client.get("/api/etf/universe?include=rs")

    assert resp.status_code == 200
    row = resp.json()["data"][0]
    assert row["rs"] is not None
    assert row["rs"]["rs_composite"] is not None
    assert row["rs"]["quadrant"] == "LEADING"


@pytest.mark.asyncio
async def test_universe_include_gold_rs_additive(
    client: AsyncClient,
    sample_masters: list[dict[str, Any]],
    sample_gold_rs: dict[str, dict[str, Any]],
) -> None:
    """include=gold_rs is additive -- default shape (no include) stays stable."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    with (
        patch(_MASTERS, new=AsyncMock(return_value=sample_masters)),
        patch(_TECH, new=AsyncMock(return_value={})),
        patch(_RS, new=AsyncMock(return_value={})),
        patch(_GOLD_RS, new=AsyncMock(return_value=sample_gold_rs)),
    ):
        resp_with = await client.get("/api/etf/universe?include=gold_rs")

    svc._etf_universe_cache.clear()

    with (
        patch(_MASTERS, new=AsyncMock(return_value=sample_masters)),
        patch(_TECH, new=AsyncMock(return_value={})),
        patch(_RS, new=AsyncMock(return_value={})),
    ):
        resp_without = await client.get("/api/etf/universe")

    assert resp_with.status_code == 200
    assert resp_without.status_code == 200

    row_with = resp_with.json()["data"][0]
    row_without = resp_without.json()["data"][0]

    # gold_rs present when included
    assert row_with["gold_rs"] is not None
    # gold_rs absent when not included -- default shape stable
    assert row_without["gold_rs"] is None
    # Core fields identical in both
    assert row_with["ticker"] == row_without["ticker"]
    assert row_with["name"] == row_without["name"]
    assert row_with["country"] == row_without["country"]


@pytest.mark.asyncio
async def test_universe_invalid_include_returns_400_envelope(
    client: AsyncClient,
) -> None:
    """include=foo -> 400 with INVALID_INCLUDE error envelope."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    resp = await client.get("/api/etf/universe?include=foo")
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body["detail"]
    assert body["detail"]["error"]["code"] == "INVALID_INCLUDE"


@pytest.mark.asyncio
async def test_universe_jip_down_returns_503_envelope(
    client: AsyncClient,
) -> None:
    """When JIP raises, route returns 503 with JIP_UNAVAILABLE envelope."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    with patch(
        _MASTERS,
        new=AsyncMock(side_effect=OSError("Connection refused")),
    ):
        resp = await client.get("/api/etf/universe")

    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"]["code"] == "JIP_UNAVAILABLE"


@pytest.mark.asyncio
async def test_universe_decimal_types_not_float(
    client: AsyncClient,
    sample_masters: list[dict[str, Any]],
    sample_tech: dict[str, dict[str, Any]],
    sample_rs: dict[str, dict[str, Any]],
) -> None:
    """No float in serialized JSON -- financial fields must be strings or null."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    with (
        patch(_MASTERS, new=AsyncMock(return_value=sample_masters)),
        patch(_TECH, new=AsyncMock(return_value=sample_tech)),
        patch(_RS, new=AsyncMock(return_value=sample_rs)),
    ):
        resp = await client.get("/api/etf/universe?include=rs,technicals")

    assert resp.status_code == 200
    row = resp.json()["data"][0]

    # Pydantic serializes Decimal as string in JSON mode
    if row.get("expense_ratio") is not None:
        assert isinstance(row["expense_ratio"], str), (
            f"expense_ratio should be str, got {type(row['expense_ratio'])}"
        )
    if row.get("rs") and row["rs"].get("rs_composite") is not None:
        assert isinstance(row["rs"]["rs_composite"], str), "rs_composite should be str"
    if row.get("technicals") and row["technicals"].get("rsi_14") is not None:
        assert isinstance(row["technicals"]["rsi_14"], str), "rsi_14 should be str"


@pytest.mark.asyncio
async def test_universe_invalid_country_returns_400(
    client: AsyncClient,
) -> None:
    """country=ZZ -> 400 with INVALID_COUNTRY error envelope."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    resp = await client.get("/api/etf/universe?country=ZZ")
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"]["code"] == "INVALID_COUNTRY"


@pytest.mark.asyncio
async def test_universe_empty_masters_returns_empty_data(
    client: AsyncClient,
) -> None:
    """Empty ETF master -> 200 with data=[] and record_count=0."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    with patch(_MASTERS, new=AsyncMock(return_value=[])):
        resp = await client.get("/api/etf/universe")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["_meta"]["record_count"] == 0


@pytest.mark.asyncio
async def test_universe_cache_hit_flag(
    client: AsyncClient,
    sample_masters: list[dict[str, Any]],
    sample_tech: dict[str, dict[str, Any]],
) -> None:
    """Second request within TTL returns cache_hit=True."""
    import backend.services.etf_service as svc

    svc._etf_universe_cache.clear()

    with (
        patch(_MASTERS, new=AsyncMock(return_value=sample_masters)),
        patch(_TECH, new=AsyncMock(return_value=sample_tech)),
        patch(_RS, new=AsyncMock(return_value={})),
    ):
        resp1 = await client.get("/api/etf/universe")
        resp2 = await client.get("/api/etf/universe")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # First call: cache miss (cache_hit=False)
    assert resp1.json()["_meta"]["cache_hit"] is False
    # Second call: cache hit (cache_hit=True)
    assert resp2.json()["_meta"]["cache_hit"] is True
