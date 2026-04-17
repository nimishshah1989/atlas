"""Unit tests for conviction pillar_3 TV TA integration in stock deep-dive."""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.core.computations import build_conviction_pillars
from backend.db.session import get_db
from backend.main import app
from backend.models.schemas import PillarExternal
from backend.services.tv.bridge import TVBridgeUnavailableError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_STOCK_DATA: dict[str, Any] = {
    "id": uuid4(),
    "symbol": "HDFCBANK",
    "company_name": "HDFC Bank Ltd",
    "sector": "Banking",
    "industry": "Private Sector Bank",
    "nifty_50": True,
    "nifty_200": True,
    "nifty_500": True,
    "isin": "INE040A01034",
    "listing_date": None,
    "cap_category": "large",
    "close": Decimal("1650.00"),
    "rs_composite": Decimal("1.5"),
    "rs_momentum": Decimal("0.3"),
    "rs_1w": Decimal("0.1"),
    "rs_1m": Decimal("0.4"),
    "rs_3m": Decimal("0.6"),
    "rs_6m": Decimal("0.9"),
    "rs_12m": Decimal("1.2"),
    "rsi_14": Decimal("58.0"),
    "adx_14": Decimal("30.0"),
    "macd_histogram": Decimal("5.0"),
    "above_200dma": True,
    "above_50dma": True,
    "mf_holder_count": 376,
    "delivery_vs_avg": None,
    "sharpe_1y": Decimal("1.2"),
    "relative_volume": None,
    "volatility_20d": None,
    "max_drawdown_1y": None,
    "mfi_14": None,
    "sma_50": None,
    "sma_200": None,
    "ema_20": None,
    "macd_line": None,
    "macd_signal": None,
    "sortino_1y": None,
    "calmar_ratio": None,
    "obv": None,
    "bollinger_upper": None,
    "bollinger_lower": None,
    "disparity_20": None,
    "stochastic_k": None,
    "stochastic_d": None,
    "rs_date": "2026-04-17",
    "tech_date": "2026-04-17",
}

_TV_TA_DATA: dict[str, Any] = {
    "recommendation_1d": "STRONG_BUY",
    "buy_count": 15,
    "sell_count": 2,
    "neutral_count": 3,
}


def _mock_db_session() -> AsyncMock:
    """Create a minimal mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests for build_conviction_pillars (pure computation — no DB/HTTP)
# ---------------------------------------------------------------------------


class TestBuildConvictionPillarsWithTvTa:
    """Tests for the updated build_conviction_pillars function."""

    def test_pillar_3_none_when_tv_ta_data_is_none(self) -> None:
        """pillar_3 should be None when tv_ta_data is not provided."""
        result = build_conviction_pillars(_BASE_STOCK_DATA, tv_ta_data=None)
        assert result.pillar_3 is None

    def test_pillar_3_none_when_tv_ta_data_omitted(self) -> None:
        """pillar_3 should be None when tv_ta_data argument is omitted (default)."""
        result = build_conviction_pillars(_BASE_STOCK_DATA)
        assert result.pillar_3 is None

    def test_pillar_3_present_when_tv_ta_data_provided(self) -> None:
        """pillar_3 should be a PillarExternal instance when tv_ta_data is given."""
        result = build_conviction_pillars(_BASE_STOCK_DATA, tv_ta_data=_TV_TA_DATA)
        assert result.pillar_3 is not None
        assert isinstance(result.pillar_3, PillarExternal)

    def test_pillar_3_tv_ta_contains_source_data(self) -> None:
        """pillar_3.tv_ta should be the dict passed in as tv_ta_data."""
        result = build_conviction_pillars(_BASE_STOCK_DATA, tv_ta_data=_TV_TA_DATA)
        assert result.pillar_3 is not None
        assert result.pillar_3.tv_ta == _TV_TA_DATA

    def test_pillar_3_explanation_includes_recommendation(self) -> None:
        """pillar_3.explanation should reference the TV recommendation."""
        result = build_conviction_pillars(_BASE_STOCK_DATA, tv_ta_data=_TV_TA_DATA)
        assert result.pillar_3 is not None
        assert "STRONG_BUY" in result.pillar_3.explanation

    def test_pillar_3_explanation_fallback_when_no_recommendation(self) -> None:
        """explanation should be generic when tv_ta_data has no recommendation key."""
        tv_ta_no_rec: dict[str, Any] = {"buy_count": 10}
        result = build_conviction_pillars(_BASE_STOCK_DATA, tv_ta_data=tv_ta_no_rec)
        assert result.pillar_3 is not None
        assert result.pillar_3.explanation == "TV TA data available"

    def test_existing_pillars_unaffected_by_tv_ta(self) -> None:
        """rs, technical, and institutional pillars must not change with tv_ta_data."""
        without = build_conviction_pillars(_BASE_STOCK_DATA, tv_ta_data=None)
        with_ta = build_conviction_pillars(_BASE_STOCK_DATA, tv_ta_data=_TV_TA_DATA)
        assert without.rs == with_ta.rs
        assert without.technical == with_ta.technical
        assert without.institutional == with_ta.institutional


# ---------------------------------------------------------------------------
# Tests for the HTTP route (mocked DB + TV)
# ---------------------------------------------------------------------------


class TestStockDeepDiveWithTvTa:
    """HTTP-level tests for GET /api/v1/stocks/{symbol} with TV TA."""

    @pytest.mark.asyncio
    async def test_pillar_3_present_when_tv_bridge_up(self) -> None:
        """conviction.pillar_3.tv_ta is populated when TV bridge is available."""
        mock_entry = MagicMock()
        mock_entry.tv_data = _TV_TA_DATA

        session = _mock_db_session()
        app.dependency_overrides[get_db] = lambda: session

        try:
            with (
                patch("backend.routes.stocks.JIPDataService") as MockJIP,
                patch("backend.routes.stocks.TVCacheService") as MockTVCache,
                patch("backend.routes.stocks.TVBridgeClient"),
                patch("backend.routes.stocks.get_settings"),
            ):
                mock_svc = AsyncMock()
                mock_svc.get_stock_detail.return_value = _BASE_STOCK_DATA
                MockJIP.return_value = mock_svc

                mock_cache_inst = AsyncMock()
                mock_cache_inst.get_or_fetch.return_value = mock_entry
                MockTVCache.return_value = mock_cache_inst

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/stocks/HDFCBANK")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        body = response.json()
        pillar_3 = body["stock"]["conviction"]["pillar_3"]
        assert pillar_3 is not None
        assert pillar_3["tv_ta"] == _TV_TA_DATA

    @pytest.mark.asyncio
    async def test_pillar_3_tv_ta_none_when_tv_bridge_down(self) -> None:
        """conviction.pillar_3 is None when TVBridgeUnavailableError is raised."""
        session = _mock_db_session()
        app.dependency_overrides[get_db] = lambda: session

        try:
            with (
                patch("backend.routes.stocks.JIPDataService") as MockJIP,
                patch("backend.routes.stocks.TVCacheService") as MockTVCache,
                patch("backend.routes.stocks.TVBridgeClient"),
                patch("backend.routes.stocks.get_settings"),
            ):
                mock_svc = AsyncMock()
                mock_svc.get_stock_detail.return_value = _BASE_STOCK_DATA
                MockJIP.return_value = mock_svc

                mock_cache_inst = AsyncMock()
                mock_cache_inst.get_or_fetch.side_effect = TVBridgeUnavailableError("bridge down")
                MockTVCache.return_value = mock_cache_inst

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/stocks/HDFCBANK")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        body = response.json()
        assert body["stock"]["conviction"]["pillar_3"] is None

    @pytest.mark.asyncio
    async def test_meta_partial_data_true_when_tv_bridge_down(self) -> None:
        """meta.partial_data is True when TVBridgeUnavailableError is raised."""
        session = _mock_db_session()
        app.dependency_overrides[get_db] = lambda: session

        try:
            with (
                patch("backend.routes.stocks.JIPDataService") as MockJIP,
                patch("backend.routes.stocks.TVCacheService") as MockTVCache,
                patch("backend.routes.stocks.TVBridgeClient"),
                patch("backend.routes.stocks.get_settings"),
            ):
                mock_svc = AsyncMock()
                mock_svc.get_stock_detail.return_value = _BASE_STOCK_DATA
                MockJIP.return_value = mock_svc

                mock_cache_inst = AsyncMock()
                mock_cache_inst.get_or_fetch.side_effect = TVBridgeUnavailableError("bridge down")
                MockTVCache.return_value = mock_cache_inst

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/stocks/HDFCBANK")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["partial_data"] is True

    @pytest.mark.asyncio
    async def test_meta_partial_data_false_when_tv_bridge_up(self) -> None:
        """meta.partial_data is False when TV TA data is successfully fetched."""
        mock_entry = MagicMock()
        mock_entry.tv_data = _TV_TA_DATA

        session = _mock_db_session()
        app.dependency_overrides[get_db] = lambda: session

        try:
            with (
                patch("backend.routes.stocks.JIPDataService") as MockJIP,
                patch("backend.routes.stocks.TVCacheService") as MockTVCache,
                patch("backend.routes.stocks.TVBridgeClient"),
                patch("backend.routes.stocks.get_settings"),
            ):
                mock_svc = AsyncMock()
                mock_svc.get_stock_detail.return_value = _BASE_STOCK_DATA
                MockJIP.return_value = mock_svc

                mock_cache_inst = AsyncMock()
                mock_cache_inst.get_or_fetch.return_value = mock_entry
                MockTVCache.return_value = mock_cache_inst

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/stocks/HDFCBANK")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["partial_data"] is False
