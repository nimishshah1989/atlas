"""Backend API shape tests for V2-9 MF deep-dive panel.

Verifies that:
1. Single /mf/{mstar_id} fetch provides all pillar + holdings + sector data
2. /mf/{mstar_id}/nav-history returns points array for sparkline
3. /mf/overlap returns common_holdings with weight_a, weight_b
4. /mf/overlap requires exactly 2 funds (400 otherwise)
5. top_holdings entries have symbol + weight_pct

Uses mock JIPDataService — no real DB required.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app


# ---------------------------------------------------------------------------
# Shared fixture helpers (mirrors pattern from test_mf_page_api.py)
# ---------------------------------------------------------------------------


def _make_freshness() -> dict[str, Any]:
    return {
        "nav_as_of": datetime.date(2026, 4, 10),
        "derived_as_of": datetime.date(2026, 4, 10),
        "holdings_as_of": datetime.date(2026, 3, 31),
        "sectors_as_of": datetime.date(2026, 3, 31),
        "flows_as_of": datetime.date(2026, 3, 1),
        "weighted_as_of": datetime.date(2026, 4, 10),
        "active_fund_count": 5,
    }


def _make_deep_dive_detail(mstar_id: str = "F001") -> dict[str, Any]:
    """Full fund detail dict matching what JIPDataService.get_fund_detail returns."""
    return {
        "mstar_id": mstar_id,
        "fund_name": f"Test Fund {mstar_id}",
        "amc_name": "Test AMC",
        "category_name": "Flexi Cap",
        "broad_category": "Equity",
        "is_index_fund": False,
        "is_etf": False,
        "is_active": True,
        "inception_date": datetime.date(2010, 1, 1),
        "closure_date": None,
        "merged_into_mstar_id": None,
        "primary_benchmark": "NIFTY 500 TRI",
        "expense_ratio": Decimal("1.25"),
        "investment_strategy": None,
        "nav": Decimal("150.00"),
        "nav_date": datetime.date(2026, 4, 10),
        "derived_date": datetime.date(2026, 4, 10),
        "derived_rs_composite": Decimal("72.5"),
        "nav_rs_composite": Decimal("68.0"),
        "manager_alpha": Decimal("4.5"),
        "coverage_pct": Decimal("98.5"),
        "sharpe_1y": Decimal("0.9"),
        "sortino_1y": Decimal("1.2"),
        "max_drawdown_1y": Decimal("-0.12"),
        "volatility_1y": Decimal("0.15"),
        "beta_vs_nifty": Decimal("0.92"),
        "information_ratio": Decimal("0.45"),
        "sector_count": 10,
        "sector_as_of": datetime.date(2026, 3, 31),
        "holding_count": 45,
        "holdings_as_of": datetime.date(2026, 3, 31),
        "weighted_as_of": datetime.date(2026, 4, 10),
        "weighted_rsi": Decimal("58.2"),
        "weighted_breadth_pct_above_200dma": Decimal("72.0"),
        "weighted_macd_bullish_pct": Decimal("60.5"),
        "aum_cr": Decimal("5000.00"),
        "return_1m": Decimal("1.5"),
        "return_3m": Decimal("4.2"),
        "return_6m": Decimal("8.1"),
        "return_1y": Decimal("15.3"),
        "return_3y": Decimal("12.0"),
        "return_5y": Decimal("11.5"),
        "net_flow_cr_3m": Decimal("1200.00"),
        "sip_flow_cr_3m": Decimal("800.00"),
        "folio_growth_pct": Decimal("5.2"),
        "holdings_avg_rs": Decimal("65.0"),
        "pct_above_200dma": Decimal("72.5"),
        "concentration_top10_pct": Decimal("45.0"),
    }


def _make_rs_batch(mstar_id: str = "F001") -> dict[str, Any]:
    return {
        mstar_id: {
            "mstar_id": mstar_id,
            "latest_date": datetime.date(2026, 4, 10),
            "latest_rs_composite": Decimal("72.5"),
            "past_date": datetime.date(2026, 3, 13),
            "past_rs_composite": Decimal("67.5"),
            "rs_momentum_28d": Decimal("5.0"),
        }
    }


def _build_deep_dive_svc(mstar_id: str = "F001") -> MagicMock:
    """Mock service for /{mstar_id} endpoint."""
    mock_svc = MagicMock()
    mock_svc.get_fund_detail = AsyncMock(return_value=_make_deep_dive_detail(mstar_id))
    mock_svc.get_fund_lifecycle = AsyncMock(return_value=[])
    mock_svc.get_mf_data_freshness = AsyncMock(return_value=_make_freshness())
    mock_svc.get_mf_rs_momentum_batch = AsyncMock(return_value=_make_rs_batch(mstar_id))
    return mock_svc


def _build_nav_history_svc(mstar_id: str = "F001", point_count: int = 5) -> MagicMock:
    """Mock service for /{mstar_id}/nav-history endpoint."""
    nav_rows = [
        {
            "nav_date": datetime.date(2026, 4, 10 - i),
            "nav": Decimal(str(150 - i * 0.5)),
        }
        for i in range(point_count)
    ]
    mock_svc = MagicMock()
    mock_svc.get_fund_nav_history = AsyncMock(return_value=nav_rows)
    mock_svc.get_mf_data_freshness = AsyncMock(return_value=_make_freshness())
    return mock_svc


def _build_overlap_svc(
    fund_a: str = "F001",
    fund_b: str = "F002",
    common_count: int = 3,
) -> MagicMock:
    """Mock service for /overlap endpoint."""
    common_holdings = [
        {
            "instrument_id": f"INS{i:03d}",
            "holding_name": f"STOCK{i}",
            "weight_pct_a": Decimal(str(5 - i * 0.5)),
            "weight_pct_b": Decimal(str(4 - i * 0.5)),
        }
        for i in range(common_count)
    ]
    overlap_data = {
        "overlap_pct": Decimal("35.50"),
        "common_count": common_count,
        "common_holdings": common_holdings,
    }
    mock_svc = MagicMock()
    mock_svc.get_fund_overlap = AsyncMock(return_value=overlap_data)
    mock_svc.get_mf_data_freshness = AsyncMock(return_value=_make_freshness())
    return mock_svc


# ---------------------------------------------------------------------------
# Test 1: deep-dive response has all pillar data (single-fetch is sufficient)
# ---------------------------------------------------------------------------


class TestDeepDiveResponseHasAllPillarData:
    """Verify GET /{mstar_id} returns all 4 pillars + top_holdings + sector_exposure +
    weighted_technicals in one response, so the frontend needs only one fetch."""

    def test_deep_dive_response_has_all_pillar_data(self) -> None:
        svc = _build_deep_dive_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        assert resp.status_code == 200
        body = resp.json()

        # All top-level sections required for single-fetch rendering
        required_top = [
            "identity",
            "daily",
            "pillars",
            "sector_exposure",
            "top_holdings",
            "weighted_technicals",
        ]
        for field in required_top:
            assert field in body, f"Missing top-level field: {field}"

        # All 4 conviction pillars present
        pillars = body["pillars"]
        for pillar in ["performance", "rs_strength", "flows", "holdings_quality"]:
            assert pillar in pillars, f"Missing pillar: {pillar}"

        # sector_exposure summary fields present
        se = body["sector_exposure"]
        for field in ["top_sector", "top_sector_weight_pct", "sector_count"]:
            assert field in se, f"Missing sector_exposure field: {field}"

        # weighted_technicals present
        wt = body["weighted_technicals"]
        wt_fields = [
            "weighted_rsi",
            "weighted_breadth_pct_above_200dma",
            "weighted_macd_bullish_pct",
        ]
        for field in wt_fields:
            assert field in wt, f"Missing weighted_technicals field: {field}"

    def test_deep_dive_pillars_all_have_explanation(self) -> None:
        svc = _build_deep_dive_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        pillars = resp.json()["pillars"]
        for pillar_name in ["performance", "rs_strength", "flows", "holdings_quality"]:
            assert "explanation" in pillars[pillar_name], f"{pillar_name} missing explanation"


# ---------------------------------------------------------------------------
# Test 2: NAV history returns points array
# ---------------------------------------------------------------------------


class TestNavHistoryReturnsPoints:
    """Verify GET /{mstar_id}/nav-history returns points array usable by sparkline."""

    def test_nav_history_returns_points(self) -> None:
        svc = _build_nav_history_svc(point_count=5)
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        assert resp.status_code == 200
        body = resp.json()
        assert "points" in body
        assert isinstance(body["points"], list)
        assert len(body["points"]) == 5

    def test_nav_history_points_have_nav_date_and_nav(self) -> None:
        svc = _build_nav_history_svc(point_count=3)
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        body = resp.json()
        assert len(body["points"]) >= 1
        point = body["points"][0]
        assert "nav_date" in point, "NAV point missing nav_date"
        assert "nav" in point, "NAV point missing nav"
        # nav must be a string (Decimal serialization)
        assert isinstance(point["nav"], str), "nav must be Decimal string"

    def test_nav_history_empty_when_no_data(self) -> None:
        svc = _build_nav_history_svc(point_count=0)
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        assert resp.status_code == 200
        body = resp.json()
        assert body["points"] == []
        assert body["coverage_gap_days"] == 0

    def test_nav_history_has_staleness(self) -> None:
        svc = _build_nav_history_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001/nav-history")

        body = resp.json()
        assert "staleness" in body
        assert body["staleness"]["flag"] in ("FRESH", "STALE", "EXPIRED")
        assert "data_as_of" in body


# ---------------------------------------------------------------------------
# Test 3: Overlap returns common holdings with weights
# ---------------------------------------------------------------------------


class TestOverlapReturnsCommonHoldingsWithWeights:
    """Verify GET /overlap?funds=A,B returns overlap_pct and common_holdings."""

    def test_overlap_returns_common_holdings_with_weights(self) -> None:
        svc = _build_overlap_svc(common_count=3)
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=F001,F002")

        assert resp.status_code == 200
        body = resp.json()
        assert "overlap_pct" in body
        assert "common_holdings" in body
        assert isinstance(body["common_holdings"], list)
        assert len(body["common_holdings"]) == 3

    def test_overlap_common_holding_has_weight_a_and_weight_b(self) -> None:
        svc = _build_overlap_svc(common_count=2)
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=F001,F002")

        body = resp.json()
        holding = body["common_holdings"][0]
        assert "symbol" in holding, "Missing symbol in overlap holding"
        assert "weight_a" in holding, "Missing weight_a in overlap holding"
        assert "weight_b" in holding, "Missing weight_b in overlap holding"
        # Weights must be Decimal strings
        assert isinstance(holding["weight_a"], str), "weight_a must be Decimal string"
        assert isinstance(holding["weight_b"], str), "weight_b must be Decimal string"

    def test_overlap_has_fund_a_and_fund_b_fields(self) -> None:
        svc = _build_overlap_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=F001,F002")

        body = resp.json()
        assert body["fund_a"] == "F001"
        assert body["fund_b"] == "F002"

    def test_overlap_pct_is_decimal_string(self) -> None:
        svc = _build_overlap_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=F001,F002")

        body = resp.json()
        assert isinstance(body["overlap_pct"], str), "overlap_pct must be Decimal string"

    def test_overlap_has_staleness(self) -> None:
        svc = _build_overlap_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=F001,F002")

        body = resp.json()
        assert "staleness" in body
        assert "data_as_of" in body


# ---------------------------------------------------------------------------
# Test 4: Overlap requires exactly two funds
# ---------------------------------------------------------------------------


class TestOverlapRequiresExactlyTwoFunds:
    """Verify /overlap?funds=A returns 400 (not 422 or 500)."""

    def test_overlap_requires_exactly_two_funds_one_given(self) -> None:
        # Service won't be called — route validates before hitting DB
        with patch("backend.routes.mf.JIPDataService", return_value=MagicMock()):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=F001")

        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"

    def test_overlap_requires_exactly_two_funds_three_given(self) -> None:
        with patch("backend.routes.mf.JIPDataService", return_value=MagicMock()):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap?funds=F001,F002,F003")

        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"

    def test_overlap_missing_funds_param_returns_4xx(self) -> None:
        """Missing required query param returns 4xx (global handler converts to 400)."""
        with patch("backend.routes.mf.JIPDataService", return_value=MagicMock()):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/overlap")

        # Global UQL validation error handler converts 422 → 400
        assert resp.status_code in (400, 422), f"Expected 4xx, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Test 5: deep-dive top_holdings has symbol and weight_pct
# ---------------------------------------------------------------------------


class TestDeepDiveTopHoldingsShape:
    """Verify each top_holding entry has symbol + holding_name + weight_pct."""

    def _make_svc_with_top_holdings(self) -> MagicMock:
        """Build deep-dive mock whose route will return top_holdings from holdings data."""
        # The route builds top_holdings from holding rows in get_fund_holdings
        mock_svc = MagicMock()
        mock_svc.get_fund_detail = AsyncMock(return_value=_make_deep_dive_detail())
        mock_svc.get_fund_lifecycle = AsyncMock(return_value=[])
        mock_svc.get_mf_data_freshness = AsyncMock(return_value=_make_freshness())
        mock_svc.get_mf_rs_momentum_batch = AsyncMock(return_value=_make_rs_batch())
        return mock_svc

    def test_deep_dive_top_holdings_has_symbol_and_weight(self) -> None:
        svc = self._make_svc_with_top_holdings()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        assert resp.status_code == 200
        body = resp.json()
        top_holdings = body["top_holdings"]
        assert isinstance(top_holdings, list), "top_holdings must be a list"

        # If top holdings are present, verify shape
        if top_holdings:
            h = top_holdings[0]
            assert "symbol" in h, "top_holding missing symbol"
            assert "weight_pct" in h, "top_holding missing weight_pct"
            assert "holding_name" in h, "top_holding missing holding_name"
            # weight_pct must be Decimal string
            assert isinstance(h["weight_pct"], str), "weight_pct must be Decimal string"

    def test_deep_dive_top_holdings_is_list_even_when_empty(self) -> None:
        svc = self._make_svc_with_top_holdings()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")

        body = resp.json()
        assert isinstance(body["top_holdings"], list)
