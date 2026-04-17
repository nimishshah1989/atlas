"""Unit tests for V7-3 global routes: /api/global/ratios, /rs-heatmap, /indices.

Tests live in tests/routes/ (NOT tests/api/) to avoid the conftest
integration marker trap (see bug-patterns/conftest-integration-marker-trap.md).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.session import get_db
from backend.main import app
from backend.routes.global_v7 import _compute_verdict, _safe_decimal
from backend.models.global_v7 import FourBenchVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _override_get_db():
    """FastAPI dependency override — yields a MagicMock session."""
    yield MagicMock()


def _make_macro_row(
    ticker: str,
    sparkline_n: int = 10,
    mom_change: Any = Decimal("0.5"),
) -> dict[str, Any]:
    """Build a single macro ratio row as returned by get_macro_ratios_v7."""
    spark = [
        {"date": datetime.date(2026, 1, i + 1), "value": Decimal(str(i + 1))}
        for i in range(sparkline_n)
    ]
    return {
        "ticker": ticker,
        "name": f"Name {ticker}",
        "unit": "%",
        "latest_value": Decimal("4.5"),
        "latest_date": datetime.date(2026, 4, 15),
        "mom_change": mom_change,
        "sparkline": spark,
    }


def _make_instrument_row(
    entity_id: str,
    instrument_type: str = "indices",
    rs_composite: Any = Decimal("0.5"),
) -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "name": f"Name {entity_id}",
        "instrument_type": instrument_type,
        "country": "US",
        "rs_composite": rs_composite,
        "rs_1m": Decimal("0.3"),
        "rs_3m": Decimal("0.2"),
        "rs_date": datetime.date(2026, 4, 15),
        "close": Decimal("100.0"),
        "price_date": datetime.date(2026, 4, 15),
    }


def _make_index_row(
    entity_id: str,
    rs_composite: Any = Decimal("0.5"),
    rs_1m: Any = Decimal("0.3"),
    rs_3m: Any = Decimal("0.2"),
    gold_rs_signal: Any = "AMPLIFIES_BULL",
) -> dict[str, Any]:
    return {
        "entity_id": entity_id,
        "name": f"Name {entity_id}",
        "country": "US",
        "rs_composite": rs_composite,
        "rs_1m": rs_1m,
        "rs_3m": rs_3m,
        "rs_date": datetime.date(2026, 4, 15),
        "close": Decimal("100.0"),
        "price_date": datetime.date(2026, 4, 15),
        "gold_rs_signal": gold_rs_signal,
    }


# ---------------------------------------------------------------------------
# TestComputeVerdict — pure unit tests (no DB, no HTTP)
# ---------------------------------------------------------------------------


class TestComputeVerdict:
    def test_verdict_4_positives_returns_strong_buy(self):
        result = _compute_verdict(Decimal("1"), Decimal("1"), Decimal("1"), "AMPLIFIES_BULL")
        assert result == FourBenchVerdict.STRONG_BUY

    def test_verdict_3_positives_returns_buy(self):
        result = _compute_verdict(Decimal("1"), Decimal("1"), Decimal("1"), "AMPLIFIES_BEAR")
        assert result == FourBenchVerdict.BUY

    def test_verdict_2_positives_returns_hold(self):
        result = _compute_verdict(Decimal("1"), Decimal("1"), None, None)
        assert result == FourBenchVerdict.HOLD

    def test_verdict_1_positive_returns_caution(self):
        result = _compute_verdict(Decimal("1"), None, None, None)
        assert result == FourBenchVerdict.CAUTION

    def test_verdict_0_positives_returns_avoid(self):
        result = _compute_verdict(None, None, None, None)
        assert result == FourBenchVerdict.AVOID

    def test_verdict_null_rs_composite_counts_as_non_positive(self):
        # Only rs_1m, rs_3m, gold_rs positive → 3 points → BUY (not STRONG_BUY)
        result = _compute_verdict(None, Decimal("0.5"), Decimal("0.5"), "AMPLIFIES_BULL")
        assert result == FourBenchVerdict.BUY

    def test_verdict_null_rs_1m_counts_as_non_positive(self):
        # rs_composite, rs_3m, gold_rs positive → 3 points → BUY
        result = _compute_verdict(Decimal("0.5"), None, Decimal("0.5"), "AMPLIFIES_BULL")
        assert result == FourBenchVerdict.BUY

    def test_verdict_null_rs_3m_counts_as_non_positive(self):
        # rs_composite, rs_1m, gold_rs positive → 3 points → BUY
        result = _compute_verdict(Decimal("0.5"), Decimal("0.5"), None, "AMPLIFIES_BULL")
        assert result == FourBenchVerdict.BUY

    def test_verdict_null_gold_rs_counts_as_non_positive(self):
        # rs_composite, rs_1m, rs_3m positive → 3 points → BUY
        result = _compute_verdict(Decimal("0.5"), Decimal("0.5"), Decimal("0.5"), None)
        assert result == FourBenchVerdict.BUY

    def test_verdict_amplifies_bear_not_positive(self):
        # AMPLIFIES_BEAR does not add a point (only AMPLIFIES_BULL does)
        result = _compute_verdict(Decimal("1"), Decimal("1"), Decimal("1"), "AMPLIFIES_BEAR")
        assert result == FourBenchVerdict.BUY  # 3 not 4

    def test_verdict_neutral_bench_only_not_positive(self):
        result = _compute_verdict(Decimal("1"), Decimal("1"), Decimal("1"), "NEUTRAL_BENCH_ONLY")
        assert result == FourBenchVerdict.BUY  # 3 not 4

    def test_verdict_zero_not_positive(self):
        # Decimal("0") is NOT > 0, so counts as non-positive
        result = _compute_verdict(Decimal("0"), Decimal("0"), Decimal("0"), None)
        assert result == FourBenchVerdict.AVOID

    def test_safe_decimal_none_returns_none(self):
        assert _safe_decimal(None) is None

    def test_safe_decimal_converts_to_decimal(self):
        result = _safe_decimal("3.14")
        assert isinstance(result, Decimal)
        assert result == Decimal("3.14")


# ---------------------------------------------------------------------------
# TestGlobalRatiosRoute — mock JIPMarketService
# ---------------------------------------------------------------------------


TICKERS_9 = [
    "DGS10",
    "VIXCLS",
    "INDIAVIX",
    "DXY",
    "BRENT",
    "GOLD",
    "SP500",
    "USDINR",
    "FEDFUNDS",
]


class TestGlobalRatiosRoute:
    @pytest.mark.asyncio
    async def test_ratios_returns_9_series(self):
        mock_rows = [_make_macro_row(t) for t in TICKERS_9]
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_macro_ratios_v7 = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/ratios")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "ratios" in data
        assert len(data["ratios"]) == 9

    @pytest.mark.asyncio
    async def test_ratios_sparkline_has_10_points(self):
        mock_rows = [_make_macro_row(t, sparkline_n=10) for t in TICKERS_9]
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_macro_ratios_v7 = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/ratios")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        first = data["ratios"][0]
        assert len(first["sparkline"]) == 10

    @pytest.mark.asyncio
    async def test_ratios_mom_change_present(self):
        mock_rows = [_make_macro_row(t, mom_change=Decimal("0.25")) for t in TICKERS_9]
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_macro_ratios_v7 = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/ratios")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        first = data["ratios"][0]
        assert "mom_change" in first
        assert first["mom_change"] is not None

    @pytest.mark.asyncio
    async def test_ratios_meta_present(self):
        mock_rows = [_make_macro_row(t) for t in TICKERS_9]
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_macro_ratios_v7 = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/ratios")
        finally:
            app.dependency_overrides.clear()

        data = response.json()
        # Both meta and _meta should be present (model_serializer pattern)
        assert "meta" in data or "_meta" in data


# ---------------------------------------------------------------------------
# TestRSHeatmapRoute — mock JIPMarketService
# ---------------------------------------------------------------------------


class TestRSHeatmapRoute:
    @pytest.mark.asyncio
    async def test_heatmap_grouped_by_instrument_type(self):
        # 3 different instrument types
        mock_rows = [
            _make_instrument_row("SPX", instrument_type="indices"),
            _make_instrument_row("QQQ", instrument_type="etf"),
            _make_instrument_row("GOLD", instrument_type="commodity"),
        ]
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_global_rs_heatmap_all = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/rs-heatmap")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "by_type" in data
        assert "indices" in data["by_type"]
        assert "etf" in data["by_type"]
        assert "commodity" in data["by_type"]
        assert len(data["by_type"]["indices"]) == 1
        assert len(data["by_type"]["etf"]) == 1

    @pytest.mark.asyncio
    async def test_heatmap_total_reflects_all_rows(self):
        # Simulate 131 rows across various types
        mock_rows = (
            [_make_instrument_row(f"IDX{i}", "indices") for i in range(50)]
            + [_make_instrument_row(f"ETF{i}", "etf") for i in range(40)]
            + [_make_instrument_row(f"CMD{i}", "commodity") for i in range(41)]
        )
        assert len(mock_rows) == 131

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_global_rs_heatmap_all = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/rs-heatmap")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 131

    @pytest.mark.asyncio
    async def test_heatmap_unknown_type_for_null_instrument_type(self):
        """Instruments with NULL instrument_type go to 'unknown' bucket."""
        mock_rows = [
            _make_instrument_row("X1", instrument_type=None),
        ]
        mock_rows[0]["instrument_type"] = None  # explicit NULL

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_global_rs_heatmap_all = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/rs-heatmap")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "unknown" in data["by_type"]


# ---------------------------------------------------------------------------
# TestIndicesRoute — mock JIPMarketService
# ---------------------------------------------------------------------------


class TestIndicesRoute:
    @pytest.mark.asyncio
    async def test_indices_have_four_bench_verdict(self):
        mock_rows = [_make_index_row("SPX"), _make_index_row("NIFTY50")]
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_global_indices = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/indices")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "indices" in data
        for row in data["indices"]:
            assert "four_bench_verdict" in row
            assert row["four_bench_verdict"] in {"STRONG_BUY", "BUY", "HOLD", "CAUTION", "AVOID"}

    @pytest.mark.asyncio
    async def test_indices_have_gold_rs_signal(self):
        mock_rows = [
            _make_index_row("SPX", gold_rs_signal="AMPLIFIES_BULL"),
            _make_index_row("NIFTY50", gold_rs_signal=None),
        ]
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_global_indices = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/indices")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        signals = [r.get("gold_rs_signal") for r in data["indices"]]
        assert "AMPLIFIES_BULL" in signals  # first row has it
        assert None in signals  # second row is null

    @pytest.mark.asyncio
    async def test_indices_verdict_strong_buy_all_positive(self):
        """All 4 benchmarks positive → STRONG_BUY."""
        mock_rows = [
            _make_index_row(
                "SPX",
                rs_composite=Decimal("1.0"),
                rs_1m=Decimal("0.5"),
                rs_3m=Decimal("0.3"),
                gold_rs_signal="AMPLIFIES_BULL",
            )
        ]
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_global_indices = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/indices")
        finally:
            app.dependency_overrides.clear()

        data = response.json()
        assert data["indices"][0]["four_bench_verdict"] == "STRONG_BUY"

    @pytest.mark.asyncio
    async def test_indices_verdict_avoid_all_null(self):
        """All 4 benchmarks null → AVOID."""
        mock_rows = [
            _make_index_row(
                "SPX",
                rs_composite=None,
                rs_1m=None,
                rs_3m=None,
                gold_rs_signal=None,
            )
        ]
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_global_indices = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/indices")
        finally:
            app.dependency_overrides.clear()

        data = response.json()
        assert data["indices"][0]["four_bench_verdict"] == "AVOID"

    @pytest.mark.asyncio
    async def test_indices_meta_present(self):
        mock_rows = [_make_index_row("SPX")]
        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("backend.routes.global_v7.JIPMarketService") as mock_cls:
                mock_svc = MagicMock()
                mock_svc.get_global_indices = AsyncMock(return_value=mock_rows)
                mock_cls.return_value = mock_svc
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/global/indices")
        finally:
            app.dependency_overrides.clear()

        data = response.json()
        assert "meta" in data or "_meta" in data
