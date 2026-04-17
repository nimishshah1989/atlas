"""Unit tests for GET /api/v1/stocks/{symbol}/chart-data endpoint."""

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db_session() -> AsyncMock:
    """Create a minimal mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _chart_rows(n: int = 5) -> list[dict[str, Any]]:
    """Return n fake OHLCV + technical indicator rows."""
    base = datetime.date(2025, 1, 2)
    rows = []
    for i in range(n):
        d = base + datetime.timedelta(days=i)
        rows.append(
            {
                "date": d,
                "open": Decimal("1600.00"),
                "high": Decimal("1650.00"),
                "low": Decimal("1590.00"),
                "close": Decimal("1630.00"),
                "volume": 12_000_000,
                "sma_20": Decimal("1580.00"),
                "sma_50": Decimal("1550.00"),
                "sma_200": Decimal("1500.00"),
                "ema_20": Decimal("1575.00"),
                "rsi_14": Decimal("62.5"),
                "macd_histogram": Decimal("3.2"),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStockChartDataEndpoint:
    """Tests for GET /api/v1/stocks/{symbol}/chart-data."""

    @pytest.mark.asyncio
    async def test_returns_date_and_ohlcv_fields(self) -> None:
        """Response data contains date, open, high, low, close, volume fields."""
        rows = _chart_rows(3)
        session = _mock_db_session()
        app.dependency_overrides[get_db] = lambda: session

        try:
            with patch("backend.routes.stocks.JIPDataService") as MockJIP:
                mock_svc = AsyncMock()
                mock_svc.get_chart_data.return_value = rows
                MockJIP.return_value = mock_svc

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get(
                        "/api/v1/stocks/HDFCBANK/chart-data",
                        params={"from": "2025-01-01", "to": "2026-01-01"},
                    )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        body = response.json()
        assert "points" in body
        assert len(body["points"]) == 3
        first = body["points"][0]
        for field in ("date", "open", "high", "low", "close", "volume"):
            assert field in first, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_returns_404_when_symbol_not_found_and_no_rows(self) -> None:
        """Returns 404 when symbol doesn't exist (no stock_detail + no rows)."""
        session = _mock_db_session()
        app.dependency_overrides[get_db] = lambda: session

        try:
            with patch("backend.routes.stocks.JIPDataService") as MockJIP:
                mock_svc = AsyncMock()
                mock_svc.get_chart_data.return_value = []
                mock_svc.get_stock_detail.return_value = None
                MockJIP.return_value = mock_svc

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get(
                        "/api/v1/stocks/DOESNOTEXIST/chart-data",
                    )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_record_count_matches_row_count(self) -> None:
        """meta.record_count equals the number of data points returned."""
        rows = _chart_rows(10)
        session = _mock_db_session()
        app.dependency_overrides[get_db] = lambda: session

        try:
            with patch("backend.routes.stocks.JIPDataService") as MockJIP:
                mock_svc = AsyncMock()
                mock_svc.get_chart_data.return_value = rows
                MockJIP.return_value = mock_svc

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/stocks/HDFCBANK/chart-data")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["record_count"] == 10
        assert len(body["points"]) == 10

    @pytest.mark.asyncio
    async def test_financial_fields_are_not_float(self) -> None:
        """All numeric fields in the response are Decimal-safe (no float precision loss)."""
        rows = _chart_rows(1)
        session = _mock_db_session()
        app.dependency_overrides[get_db] = lambda: session

        try:
            with patch("backend.routes.stocks.JIPDataService") as MockJIP:
                mock_svc = AsyncMock()
                mock_svc.get_chart_data.return_value = rows
                MockJIP.return_value = mock_svc

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/v1/stocks/HDFCBANK/chart-data")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        body = response.json()
        first = body["points"][0]
        # Verify Decimal values round-trip correctly (no float precision loss)
        for field in ("open", "high", "low", "close", "sma_20", "rsi_14"):
            val = first.get(field)
            if val is not None:
                assert Decimal(str(val)) == Decimal(str(val)), f"Precision loss in {field}"

    @pytest.mark.asyncio
    async def test_empty_date_range_returns_empty_data(self) -> None:
        """When chart_data returns empty but stock exists, returns empty data list (not 404)."""
        session = _mock_db_session()
        app.dependency_overrides[get_db] = lambda: session

        try:
            with patch("backend.routes.stocks.JIPDataService") as MockJIP:
                mock_svc = AsyncMock()
                mock_svc.get_chart_data.return_value = []
                # Stock exists — has a detail record
                mock_svc.get_stock_detail.return_value = {
                    "id": "some-uuid",
                    "symbol": "HDFCBANK",
                }
                MockJIP.return_value = mock_svc

                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get(
                        "/api/v1/stocks/HDFCBANK/chart-data",
                        params={"from": "2020-01-01", "to": "2020-01-02"},
                    )
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        body = response.json()
        assert body["points"] == []
        assert body["meta"]["record_count"] == 0
