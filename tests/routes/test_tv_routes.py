"""Route unit tests for GET /api/tv/ta/{symbol}, /screener/{symbol}, /fundamentals/{symbol}.

Uses ASGITransport + AsyncClient against the FastAPI app — no live server needed.
DB session is overridden via dependency_overrides.
TVCacheService.get_or_fetch is patched so no real DB or bridge calls occur.

Pattern follows tests/routes/test_tv_webhook.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app
from backend.models.tv import TvCacheEntry
from backend.services.tv.bridge import TVBridgeUnavailableError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_db_session() -> AsyncMock:
    """Return an AsyncMock suitable as an injected DB session."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    return session


def _fresh_ta_entry(symbol: str = "HDFCBANK") -> TvCacheEntry:
    """Return a fresh (non-stale) TvCacheEntry with TA data."""
    return TvCacheEntry(
        symbol=symbol,
        exchange="NSE",
        data_type="ta_summary",
        interval="1D",
        tv_data={
            "RECOMMENDATION": "STRONG_BUY",
            "COMPUTE": {
                "OSCILLATORS": {"RECOMMENDATION": "BUY"},
                "MA": {"RECOMMENDATION": "STRONG_BUY"},
            },
            "BUY": 15,
            "SELL": 2,
            "NEUTRAL": 3,
        },
        fetched_at=datetime.now(tz=UTC),
        is_stale=False,
    )


def _stale_ta_entry(symbol: str = "HDFCBANK") -> TvCacheEntry:
    """Return a stale TvCacheEntry with TA data."""
    entry = _fresh_ta_entry(symbol)
    return entry.model_copy(update={"is_stale": True})


def _screener_entry(symbol: str = "RELIANCE") -> TvCacheEntry:
    """Return a fresh screener TvCacheEntry."""
    return TvCacheEntry(
        symbol=symbol,
        exchange="NSE",
        data_type="screener",
        interval="none",
        tv_data={"close": "1234.50", "volume": "5000000"},
        fetched_at=datetime.now(tz=UTC),
        is_stale=False,
    )


def _fundamentals_entry(symbol: str = "RELIANCE") -> TvCacheEntry:
    """Return a fresh fundamentals TvCacheEntry."""
    return TvCacheEntry(
        symbol=symbol,
        exchange="NSE",
        data_type="fundamentals",
        interval="none",
        tv_data={"pe_ratio": "22.5", "eps": "50.1"},
        fetched_at=datetime.now(tz=UTC),
        is_stale=False,
    )


def _make_client() -> AsyncClient:
    app.dependency_overrides[get_db] = _mock_db_session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.tv_bridge_url = "http://127.0.0.1:7100"
    settings.tv_cache_ttl_seconds = 900
    return settings


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ta_fresh_cache_hit_returns_200_with_fields() -> None:
    """GET /api/tv/ta/HDFCBANK with a fresh cache hit returns 200.

    Asserts recommendation_1d, oscillator_score, ma_score present and
    _meta.is_stale is False.
    """
    entry = _fresh_ta_entry("HDFCBANK")
    with patch("backend.routes.tv.TVCacheService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_or_fetch = AsyncMock(return_value=entry)
        with patch("backend.routes.tv.get_settings", return_value=_mock_settings()):
            async with _make_client() as ac:
                resp = await ac.get("/api/tv/ta/HDFCBANK")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["data"]["recommendation_1d"] == "STRONG_BUY"
    assert body["data"]["oscillator_score"] == "BUY"
    assert body["data"]["ma_score"] == "STRONG_BUY"
    assert body["data"]["buy"] == 15
    assert "_meta" in body
    assert body["_meta"]["is_stale"] is False
    assert body["_meta"]["data_layer"] == "near_realtime"


@pytest.mark.asyncio
async def test_ta_stale_cache_hit_returns_meta_is_stale_true() -> None:
    """GET /api/tv/ta/HDFCBANK with a stale cache entry sets _meta.is_stale=True."""
    entry = _stale_ta_entry("HDFCBANK")
    with patch("backend.routes.tv.TVCacheService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_or_fetch = AsyncMock(return_value=entry)
        with patch("backend.routes.tv.get_settings", return_value=_mock_settings()):
            async with _make_client() as ac:
                resp = await ac.get("/api/tv/ta/HDFCBANK")

    assert resp.status_code == 200
    body = resp.json()
    assert body["_meta"]["is_stale"] is True


@pytest.mark.asyncio
async def test_ta_bridge_unavailable_returns_503() -> None:
    """GET /api/tv/ta/HDFCBANK returns 503 when TVBridgeUnavailableError is raised."""
    with patch("backend.routes.tv.TVCacheService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_or_fetch = AsyncMock(
            side_effect=TVBridgeUnavailableError("sidecar not running")
        )
        with patch("backend.routes.tv.get_settings", return_value=_mock_settings()):
            async with _make_client() as ac:
                resp = await ac.get("/api/tv/ta/HDFCBANK")

    assert resp.status_code == 503
    body = resp.json()
    assert "TV bridge unavailable" in body.get("detail", "")


@pytest.mark.asyncio
async def test_screener_returns_200() -> None:
    """GET /api/tv/screener/RELIANCE returns 200 with data.symbol."""
    entry = _screener_entry("RELIANCE")
    with patch("backend.routes.tv.TVCacheService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_or_fetch = AsyncMock(return_value=entry)
        with patch("backend.routes.tv.get_settings", return_value=_mock_settings()):
            async with _make_client() as ac:
                resp = await ac.get("/api/tv/screener/RELIANCE")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["data"]["symbol"] == "RELIANCE"
    assert "raw" in body["data"]
    assert "_meta" in body


@pytest.mark.asyncio
async def test_fundamentals_returns_200() -> None:
    """GET /api/tv/fundamentals/RELIANCE returns 200 with data.symbol."""
    entry = _fundamentals_entry("RELIANCE")
    with patch("backend.routes.tv.TVCacheService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_or_fetch = AsyncMock(return_value=entry)
        with patch("backend.routes.tv.get_settings", return_value=_mock_settings()):
            async with _make_client() as ac:
                resp = await ac.get("/api/tv/fundamentals/RELIANCE")

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["data"]["symbol"] == "RELIANCE"
    assert "raw" in body["data"]
    assert "_meta" in body


@pytest.mark.asyncio
async def test_ta_exchange_query_param_passed_to_service() -> None:
    """GET /api/tv/ta/HDFCBANK?exchange=BSE passes exchange=BSE to get_or_fetch."""
    entry = _fresh_ta_entry("HDFCBANK")
    with patch("backend.routes.tv.TVCacheService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_or_fetch = AsyncMock(return_value=entry)
        with patch("backend.routes.tv.get_settings", return_value=_mock_settings()):
            async with _make_client() as ac:
                resp = await ac.get("/api/tv/ta/HDFCBANK?exchange=BSE")

    assert resp.status_code == 200
    call_kwargs = instance.get_or_fetch.call_args
    assert call_kwargs.kwargs["exchange"] == "BSE"


@pytest.mark.asyncio
async def test_ta_empty_tv_data_returns_none_fields() -> None:
    """GET /api/tv/ta with empty tv_data returns None for all optional TA fields."""
    entry = TvCacheEntry(
        symbol="TATASTEEL",
        exchange="NSE",
        data_type="ta_summary",
        interval="1D",
        tv_data={},
        fetched_at=datetime.now(tz=UTC),
        is_stale=False,
    )
    with patch("backend.routes.tv.TVCacheService") as MockSvc:
        instance = MockSvc.return_value
        instance.get_or_fetch = AsyncMock(return_value=entry)
        with patch("backend.routes.tv.get_settings", return_value=_mock_settings()):
            async with _make_client() as ac:
                resp = await ac.get("/api/tv/ta/TATASTEEL")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["recommendation_1d"] is None
    assert body["data"]["oscillator_score"] is None
    assert body["data"]["ma_score"] is None
