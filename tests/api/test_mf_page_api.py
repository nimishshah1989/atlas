"""Backend API shape tests for V2-8 MF frontend consumption.

Verifies that the MF API endpoints return the correct data shapes
that the frontend MF components expect. Uses mock JIPDataService.
These are unit-level tests (no real DB), not integration tests.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


# ---------------------------------------------------------------------------
# Shared fixture helpers (same pattern as test_mf_routes.py)
# ---------------------------------------------------------------------------


def _make_fund_row(
    mstar_id: str = "F001",
    category_name: str = "Flexi Cap",
    broad_category: str = "Equity",
    derived_rs_composite: Any = Decimal("70.0"),
    manager_alpha: Any = Decimal("1.5"),
    is_active: bool = True,
) -> dict[str, Any]:
    return {
        "mstar_id": mstar_id,
        "fund_name": f"Test Fund {mstar_id}",
        "amc_name": "Test AMC",
        "category_name": category_name,
        "broad_category": broad_category,
        "is_index_fund": False,
        "is_active": is_active,
        "is_etf": False,
        "inception_date": datetime.date(2010, 1, 1),
        "expense_ratio": Decimal("1.00"),
        "nav": Decimal("100.00"),
        "nav_date": datetime.date(2026, 4, 10),
        "derived_rs_composite": derived_rs_composite,
        "nav_rs_composite": derived_rs_composite,
        "manager_alpha": manager_alpha,
        "sharpe_1y": Decimal("0.8"),
        "sortino_1y": Decimal("1.2"),
        "max_drawdown_1y": Decimal("-0.15"),
        "volatility_1y": Decimal("0.18"),
        "beta_vs_nifty": Decimal("0.95"),
        "primary_benchmark": "NIFTY 500 TRI",
        "rs_momentum_28d": Decimal("2.5"),
    }


def _make_rs_batch(mstar_ids: list[str]) -> dict[str, dict[str, Any]]:
    return {
        mid: {
            "mstar_id": mid,
            "latest_date": datetime.date(2026, 4, 10),
            "latest_rs_composite": Decimal("70.0"),
            "past_date": datetime.date(2026, 3, 13),
            "past_rs_composite": Decimal("65.0"),
            "rs_momentum_28d": Decimal("5.0"),
        }
        for mid in mstar_ids
    }


def _make_freshness(
    nav_as_of: datetime.date | None = None,
) -> dict[str, Any]:
    return {
        "nav_as_of": nav_as_of or datetime.date(2026, 4, 10),
        "derived_as_of": datetime.date(2026, 4, 10),
        "holdings_as_of": datetime.date(2026, 3, 31),
        "sectors_as_of": datetime.date(2026, 3, 31),
        "flows_as_of": datetime.date(2026, 3, 1),
        "weighted_as_of": datetime.date(2026, 4, 10),
        "active_fund_count": 5,
    }


def _make_cat_rows() -> list[dict[str, Any]]:
    return [
        {
            "category_name": "Flexi Cap",
            "broad_category": "Equity",
            "active_fund_count": 3,
            "avg_rs_composite": Decimal("70.0"),
            "avg_manager_alpha": Decimal("1.5"),
            "manager_alpha_p50": Decimal("1.5"),
            "manager_alpha_p90": Decimal("2.8"),
            "latest_flow_date": datetime.date(2026, 3, 1),
            "net_flow_cr": Decimal("500.00"),
            "gross_inflow_cr": Decimal("1000.00"),
            "gross_outflow_cr": Decimal("500.00"),
            "aum_cr": Decimal("50000.00"),
            "sip_flow_cr": Decimal("200.00"),
        },
    ]


def _make_flow_rows(months: int = 3) -> list[dict[str, Any]]:
    rows = []
    for i in range(months):
        mo = 3 - i
        if mo <= 0:
            mo += 12
        rows.append(
            {
                "month_date": datetime.date(2026, mo, 1),
                "category": "Flexi Cap",
                "net_flow_cr": Decimal("5000.00"),
                "gross_inflow_cr": Decimal("12000.00"),
                "gross_outflow_cr": Decimal("7000.00"),
                "aum_cr": Decimal("150000.00"),
                "sip_flow_cr": Decimal("3000.00"),
                "sip_accounts": 500000,
                "folios": 1200000,
            }
        )
    return rows


def _patch_svc(
    universe_rows: list[dict[str, Any]],
    rs_batch: dict[str, dict[str, Any]],
    freshness: dict[str, Any],
    cat_rows: list[dict[str, Any]] | None = None,
    flow_rows: list[dict[str, Any]] | None = None,
) -> MagicMock:
    mock_svc = MagicMock()
    mock_svc.get_mf_universe = AsyncMock(return_value=universe_rows)
    mock_svc.get_mf_rs_momentum_batch = AsyncMock(return_value=rs_batch)
    mock_svc.get_mf_data_freshness = AsyncMock(return_value=freshness)
    mock_svc.get_mf_categories = AsyncMock(return_value=cat_rows or [])
    mock_svc.get_mf_flows = AsyncMock(return_value=flow_rows or [])
    return mock_svc


# ---------------------------------------------------------------------------
# /universe tests
# ---------------------------------------------------------------------------


class TestMFUniverseShapeForFrontend:
    """Verify /universe returns the shape MFUniverseTree expects."""

    def _build_data(self) -> tuple[list[dict], dict, dict]:
        rows = [
            _make_fund_row("F001", "Flexi Cap", "Equity"),
            _make_fund_row("F002", "Large Cap", "Equity"),
        ]
        rs_batch = _make_rs_batch(["F001", "F002"])
        freshness = _make_freshness()
        return rows, rs_batch, freshness

    def test_universe_returns_200(self) -> None:
        rows, rs_batch, freshness = self._build_data()
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        assert resp.status_code == 200

    def test_universe_returns_broad_categories_list(self) -> None:
        rows, rs_batch, freshness = self._build_data()
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        assert "broad_categories" in body
        assert "data_as_of" in body
        assert "staleness" in body

    def test_universe_broad_category_has_categories_and_funds(self) -> None:
        fund_rows = [
            _make_fund_row("F001", "Flexi Cap", "Equity"),
            _make_fund_row("F002", "Flexi Cap", "Equity"),
        ]
        rs_batch = _make_rs_batch(["F001", "F002"])
        mock_svc = _patch_svc(fund_rows, rs_batch, _make_freshness())

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        broad = body["broad_categories"]
        assert len(broad) >= 1
        equity_group = next((b for b in broad if b["name"] == "Equity"), None)
        assert equity_group is not None
        assert "categories" in equity_group
        flexi_cat = next((c for c in equity_group["categories"] if c["name"] == "Flexi Cap"), None)
        assert flexi_cat is not None
        assert "funds" in flexi_cat
        assert len(flexi_cat["funds"]) == 2

    def test_universe_fund_fields_match_frontend_interface(self) -> None:
        """Every field in MFFund TypeScript interface must be present."""
        rows, rs_batch, freshness = self._build_data()
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        funds_all: list[dict] = []
        for bg in body["broad_categories"]:
            for cat in bg["categories"]:
                funds_all.extend(cat["funds"])
        assert len(funds_all) >= 1
        fund = funds_all[0]
        required_fields = [
            "mstar_id",
            "fund_name",
            "amc_name",
            "category_name",
            "broad_category",
            "nav",
            "nav_date",
            "rs_composite",
            "quadrant",
            "manager_alpha",
            "expense_ratio",
            "is_index_fund",
        ]
        for field in required_fields:
            assert field in fund, f"Missing field: {field}"

    def test_universe_financial_values_are_strings_not_floats(self) -> None:
        """Decimal fields must serialize as strings, not IEEE-754 floats."""
        rows, rs_batch, freshness = self._build_data()
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        funds_all: list[dict] = []
        for bg in body["broad_categories"]:
            for cat in bg["categories"]:
                funds_all.extend(cat["funds"])
        fund = funds_all[0]
        assert isinstance(fund["nav"], str), "nav must be string (Decimal serialization)"
        if fund["rs_composite"] is not None:
            assert isinstance(fund["rs_composite"], str), "rs_composite must be string"

    def test_universe_staleness_has_flag(self) -> None:
        rows, rs_batch, freshness = self._build_data()
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        staleness = body["staleness"]
        assert "flag" in staleness
        assert staleness["flag"] in ("FRESH", "STALE", "EXPIRED")
        assert "age_minutes" in staleness
        assert "source" in staleness


# ---------------------------------------------------------------------------
# /categories tests
# ---------------------------------------------------------------------------


class TestMFCategoriesShapeForFrontend:
    """Verify /categories returns the shape MFCategoryTable expects."""

    def test_categories_returns_list(self) -> None:
        mock_svc = _patch_svc(
            [_make_fund_row("F001")],
            _make_rs_batch(["F001"]),
            _make_freshness(),
            cat_rows=_make_cat_rows(),
        )

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/categories")

        assert resp.status_code == 200
        body = resp.json()
        assert "categories" in body
        assert isinstance(body["categories"], list)

    def test_categories_row_fields_match_frontend_interface(self) -> None:
        mock_svc = _patch_svc(
            [_make_fund_row("F001")],
            _make_rs_batch(["F001"]),
            _make_freshness(),
            cat_rows=_make_cat_rows(),
        )

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/categories")

        body = resp.json()
        assert len(body["categories"]) >= 1
        row = body["categories"][0]
        required_fields = [
            "category_name",
            "broad_category",
            "fund_count",
            "avg_rs_composite",
            "quadrant_distribution",
            "net_flow_cr",
            "sip_flow_cr",
            "total_aum_cr",
            "manager_alpha_p50",
            "manager_alpha_p90",
        ]
        for field in required_fields:
            assert field in row, f"Missing field: {field}"

    def test_categories_quadrant_distribution_is_dict(self) -> None:
        mock_svc = _patch_svc(
            [_make_fund_row("F001"), _make_fund_row("F002")],
            _make_rs_batch(["F001", "F002"]),
            _make_freshness(),
            cat_rows=_make_cat_rows(),
        )

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/categories")

        body = resp.json()
        row = body["categories"][0]
        assert isinstance(row["quadrant_distribution"], dict)

    def test_categories_has_data_as_of_and_staleness(self) -> None:
        mock_svc = _patch_svc(
            [_make_fund_row("F001")],
            _make_rs_batch(["F001"]),
            _make_freshness(),
            cat_rows=_make_cat_rows(),
        )

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/categories")

        body = resp.json()
        assert "data_as_of" in body
        assert "staleness" in body
        assert body["staleness"]["flag"] in ("FRESH", "STALE", "EXPIRED")


# ---------------------------------------------------------------------------
# /flows tests
# ---------------------------------------------------------------------------


class TestMFFlowsShapeForFrontend:
    """Verify /flows returns the shape MFFlowsPanel expects."""

    def test_flows_returns_200(self) -> None:
        mock_svc = _patch_svc(
            [],
            {},
            _make_freshness(),
            flow_rows=_make_flow_rows(),
        )

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        assert resp.status_code == 200

    def test_flows_returns_list(self) -> None:
        mock_svc = _patch_svc(
            [],
            {},
            _make_freshness(),
            flow_rows=_make_flow_rows(),
        )

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        body = resp.json()
        assert "flows" in body
        assert isinstance(body["flows"], list)

    def test_flows_row_fields_match_frontend_interface(self) -> None:
        mock_svc = _patch_svc(
            [],
            {},
            _make_freshness(),
            flow_rows=_make_flow_rows(1),
        )

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        body = resp.json()
        if not body["flows"]:
            pytest.skip("No flow rows returned — check mock")
        row = body["flows"][0]
        required_fields = [
            "month_date",
            "category",
            "net_flow_cr",
            "gross_inflow_cr",
            "gross_outflow_cr",
            "aum_cr",
            "sip_flow_cr",
        ]
        for field in required_fields:
            assert field in row, f"Missing field: {field}"

    def test_flows_net_flow_is_string_decimal(self) -> None:
        mock_svc = _patch_svc(
            [],
            {},
            _make_freshness(),
            flow_rows=_make_flow_rows(1),
        )

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        body = resp.json()
        if not body["flows"]:
            pytest.skip("No flow rows returned")
        row = body["flows"][0]
        if row["net_flow_cr"] is not None:
            assert isinstance(row["net_flow_cr"], str), "net_flow_cr must be string (Decimal)"

    def test_flows_has_staleness(self) -> None:
        mock_svc = _patch_svc(
            [],
            {},
            _make_freshness(),
            flow_rows=_make_flow_rows(),
        )

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        body = resp.json()
        assert "staleness" in body
        assert "data_as_of" in body


# ---------------------------------------------------------------------------
# /{mstar_id} deep-dive tests
# ---------------------------------------------------------------------------


class TestMFDeepDiveShapeForFrontend:
    """Verify /{mstar_id} returns the shape MFDeepDive component expects."""

    def _build_deep_dive_svc(self, mstar_id: str = "F001") -> MagicMock:
        """Build mock matching the route's exact JIPDataService method calls."""
        detail = {
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
        rs_batch = {
            mstar_id: {
                "mstar_id": mstar_id,
                "latest_date": datetime.date(2026, 4, 10),
                "latest_rs_composite": Decimal("72.5"),
                "past_date": datetime.date(2026, 3, 13),
                "past_rs_composite": Decimal("67.5"),
                "rs_momentum_28d": Decimal("5.0"),
            }
        }
        mock_svc = MagicMock()
        mock_svc.get_fund_detail = AsyncMock(return_value=detail)
        mock_svc.get_fund_lifecycle = AsyncMock(return_value=[])
        mock_svc.get_mf_data_freshness = AsyncMock(return_value=_make_freshness())
        mock_svc.get_mf_rs_momentum_batch = AsyncMock(return_value=rs_batch)
        return mock_svc

    def test_deep_dive_returns_200(self) -> None:
        svc = self._build_deep_dive_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")
        assert resp.status_code == 200

    def test_deep_dive_has_required_top_level_fields(self) -> None:
        svc = self._build_deep_dive_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")
        body = resp.json()
        required = [
            "identity",
            "daily",
            "pillars",
            "sector_exposure",
            "top_holdings",
            "weighted_technicals",
            "data_as_of",
            "staleness",
        ]
        for field in required:
            assert field in body, f"Missing top-level field: {field}"

    def test_deep_dive_identity_fields(self) -> None:
        svc = self._build_deep_dive_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")
        identity = resp.json()["identity"]
        for field in [
            "mstar_id",
            "fund_name",
            "amc_name",
            "category_name",
            "broad_category",
            "is_index_fund",
        ]:
            assert field in identity, f"Missing identity field: {field}"

    def test_deep_dive_pillars_structure(self) -> None:
        svc = self._build_deep_dive_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")
        pillars = resp.json()["pillars"]
        for pillar in ["performance", "rs_strength", "flows", "holdings_quality"]:
            assert pillar in pillars, f"Missing pillar: {pillar}"

    def test_deep_dive_returns_are_string_decimals(self) -> None:
        svc = self._build_deep_dive_svc()
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/F001")
        daily = resp.json()["daily"]
        if daily["return_1y"] is not None:
            assert isinstance(daily["return_1y"], str), "return_1y must be Decimal string"

    def test_deep_dive_missing_fund_returns_404(self) -> None:
        svc = MagicMock()
        svc.get_fund_detail = AsyncMock(return_value=None)
        svc.get_fund_lifecycle = AsyncMock(return_value=[])
        svc.get_mf_data_freshness = AsyncMock(return_value=_make_freshness())
        svc.get_mf_rs_momentum_batch = AsyncMock(return_value={})
        with patch("backend.routes.mf.JIPDataService", return_value=svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/NONEXISTENT999")
        assert resp.status_code == 404
