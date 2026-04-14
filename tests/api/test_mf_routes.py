"""Integration tests for wired MF routes (V2-4): /universe, /categories, /flows.

Uses mock JIPDataService to avoid real DB. Verifies:
- Routes return HTTP 200 with correct Pydantic structure
- /universe fund_count matches active-subset count from JIP
- /categories returns manager_alpha_p50/p90 as Decimal, quadrant_distribution populated
- /flows returns last 12 months, all FlowRow fields present
- All financial values are Decimal (not float)
- Staleness flag logic: FRESH / STALE / EXPIRED thresholds
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.main import app


# ---------------------------------------------------------------------------
# Fixtures — synthetic JIP data that mirrors real schema
# ---------------------------------------------------------------------------


def _make_fund_row(
    mstar_id: str,
    category_name: str = "Flexi Cap",
    broad_category: str = "Equity",
    derived_rs_composite: Any = Decimal("70.0"),
    manager_alpha: Any = Decimal("1.5"),
    is_active: bool = True,
) -> dict[str, Any]:
    return {
        "mstar_id": mstar_id,
        "fund_name": f"Fund {mstar_id}",
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
    }


def _make_rs_batch(mstar_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Build a fake RS momentum batch with positive momentum for all funds."""
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
        {
            "category_name": "Large Cap",
            "broad_category": "Equity",
            "active_fund_count": 2,
            "avg_rs_composite": Decimal("60.0"),
            "avg_manager_alpha": Decimal("0.5"),
            "manager_alpha_p50": Decimal("0.5"),
            "manager_alpha_p90": Decimal("1.2"),
            "latest_flow_date": datetime.date(2026, 3, 1),
            "net_flow_cr": Decimal("300.00"),
            "gross_inflow_cr": Decimal("700.00"),
            "gross_outflow_cr": Decimal("400.00"),
            "aum_cr": Decimal("80000.00"),
            "sip_flow_cr": Decimal("150.00"),
        },
    ]


def _make_flow_rows(months: int = 12) -> list[dict[str, Any]]:
    rows = []
    base = datetime.date(2026, 4, 1)
    for i in range(months):
        if base.month - i <= 0:
            year = base.year - 1
            month_num = 12 + (base.month - i)
        else:
            year = base.year
            month_num = base.month - i
        month_date = datetime.date(year, month_num, 1)
        rows.append(
            {
                "month_date": month_date,
                "category": "Flexi Cap",
                "net_flow_cr": Decimal("100.00"),
                "gross_inflow_cr": Decimal("500.00"),
                "gross_outflow_cr": Decimal("400.00"),
                "aum_cr": Decimal("50000.00"),
                "sip_flow_cr": Decimal("75.00"),
                "sip_accounts": 100000,
                "folios": 500000,
            }
        )
    return rows


def _make_freshness(nav_as_of: datetime.date | None = None) -> dict[str, Any]:
    return {
        "nav_as_of": nav_as_of or datetime.date(2026, 4, 10),
        "derived_as_of": datetime.date(2026, 4, 10),
        "holdings_as_of": datetime.date(2026, 3, 31),
        "sectors_as_of": datetime.date(2026, 3, 31),
        "flows_as_of": datetime.date(2026, 3, 1),
        "weighted_as_of": datetime.date(2026, 4, 10),
        "active_fund_count": 5,
    }


# ---------------------------------------------------------------------------
# Helpers — patch JIPDataService methods
# ---------------------------------------------------------------------------


def _patch_svc(
    universe_rows: list[dict[str, Any]],
    rs_batch: dict[str, dict[str, Any]],
    freshness: dict[str, Any],
    cat_rows: list[dict[str, Any]] | None = None,
    flow_rows: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock JIPDataService with pre-wired return values."""
    mock_svc = MagicMock()
    mock_svc.get_mf_universe = AsyncMock(return_value=universe_rows)
    mock_svc.get_mf_rs_momentum_batch = AsyncMock(return_value=rs_batch)
    mock_svc.get_mf_data_freshness = AsyncMock(return_value=freshness)
    mock_svc.get_mf_categories = AsyncMock(return_value=cat_rows or [])
    mock_svc.get_mf_flows = AsyncMock(return_value=flow_rows or [])
    return mock_svc


# ---------------------------------------------------------------------------
# /universe
# ---------------------------------------------------------------------------


class TestUniverseRoute:
    """Tests for GET /api/v1/mf/universe."""

    def _build_data(self) -> tuple[list[dict], dict, dict]:
        mstar_ids = ["F001", "F002", "F003", "F004", "F005"]
        rows = [
            _make_fund_row("F001", category_name="Flexi Cap", broad_category="Equity"),
            _make_fund_row("F002", category_name="Flexi Cap", broad_category="Equity"),
            _make_fund_row("F003", category_name="Large Cap", broad_category="Equity"),
            _make_fund_row("F004", category_name="Liquid", broad_category="Debt"),
            _make_fund_row("F005", category_name="Liquid", broad_category="Debt"),
        ]
        rs_batch = _make_rs_batch(mstar_ids)
        freshness = _make_freshness()
        return rows, rs_batch, freshness

    def test_universe_returns_200(self) -> None:
        rows, rs_batch, freshness = self._build_data()
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_universe_structure(self) -> None:
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
        assert isinstance(body["broad_categories"], list)

    def test_universe_fund_count_matches_jip_rows(self) -> None:
        """fund_count in response must equal len(rows returned by JIP)."""
        rows, rs_batch, freshness = self._build_data()
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        total_funds = sum(
            len(cg["funds"]) for bg in body["broad_categories"] for cg in bg["categories"]
        )
        assert total_funds == len(rows), f"Expected {len(rows)} funds, got {total_funds}"

    def test_universe_broad_category_grouping(self) -> None:
        rows, rs_batch, freshness = self._build_data()
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        bc_names = {bc["name"] for bc in body["broad_categories"]}
        assert "Equity" in bc_names
        assert "Debt" in bc_names

    def test_universe_quadrant_set_on_funds(self) -> None:
        rows, rs_batch, freshness = self._build_data()
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        funds = [
            f for bg in body["broad_categories"] for cg in bg["categories"] for f in cg["funds"]
        ]
        # All funds have positive rs_composite and positive momentum → LEADING
        quadrants = {f["quadrant"] for f in funds if f.get("quadrant")}
        assert "LEADING" in quadrants

    def test_universe_no_float_in_financial_fields(self) -> None:
        """rs_composite, manager_alpha, nav, expense_ratio must be strings (Decimal-serialised)."""
        rows, rs_batch, freshness = self._build_data()
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        funds = [
            f for bg in body["broad_categories"] for cg in bg["categories"] for f in cg["funds"]
        ]
        assert funds, "Expected at least one fund in response"
        for fund in funds:
            for field in ("nav", "rs_composite", "manager_alpha", "expense_ratio"):
                val = fund.get(field)
                if val is not None:
                    assert isinstance(val, str), (
                        f"Field '{field}' must be Decimal (str), got {type(val)}: {val}"
                    )

    def test_universe_staleness_fresh(self) -> None:
        rows, rs_batch, _ = self._build_data()
        freshness = _make_freshness(nav_as_of=datetime.date.today())
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        assert body["staleness"]["flag"] == "FRESH"

    def test_universe_staleness_expired(self) -> None:
        rows, rs_batch, _ = self._build_data()
        stale_date = datetime.date.today() - datetime.timedelta(days=5)
        freshness = _make_freshness(nav_as_of=stale_date)
        mock_svc = _patch_svc(rows, rs_batch, freshness)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        body = resp.json()
        assert body["staleness"]["flag"] == "EXPIRED"

    def test_universe_empty_returns_200(self) -> None:
        """Empty universe (filtered out) should return 200 with empty broad_categories."""
        mock_svc = _patch_svc([], {}, _make_freshness())

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/universe")

        assert resp.status_code == 200
        body = resp.json()
        assert body["broad_categories"] == []


# ---------------------------------------------------------------------------
# /categories
# ---------------------------------------------------------------------------


class TestCategoriesRoute:
    """Tests for GET /api/v1/mf/categories."""

    def _make_data(self) -> tuple[list[dict], list[dict], dict, dict]:
        universe = [
            _make_fund_row("F001", category_name="Flexi Cap", broad_category="Equity"),
            _make_fund_row("F002", category_name="Flexi Cap", broad_category="Equity"),
            _make_fund_row("F003", category_name="Flexi Cap", broad_category="Equity"),
            _make_fund_row("F004", category_name="Large Cap", broad_category="Equity"),
            _make_fund_row("F005", category_name="Large Cap", broad_category="Equity"),
        ]
        rs_batch = _make_rs_batch(["F001", "F002", "F003", "F004", "F005"])
        cat_rows = _make_cat_rows()
        freshness = _make_freshness()
        return universe, cat_rows, rs_batch, freshness

    def test_categories_returns_200(self) -> None:
        universe, cat_rows, rs_batch, freshness = self._make_data()
        mock_svc = _patch_svc(universe, rs_batch, freshness, cat_rows=cat_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/categories")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_categories_structure(self) -> None:
        universe, cat_rows, rs_batch, freshness = self._make_data()
        mock_svc = _patch_svc(universe, rs_batch, freshness, cat_rows=cat_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/categories")

        body = resp.json()
        assert "categories" in body
        assert "data_as_of" in body
        assert "staleness" in body
        assert len(body["categories"]) == 2

    def test_categories_p50_p90_are_decimal_strings(self) -> None:
        """manager_alpha_p50 and p90 must be Decimal (JSON string)."""
        universe, cat_rows, rs_batch, freshness = self._make_data()
        mock_svc = _patch_svc(universe, rs_batch, freshness, cat_rows=cat_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/categories")

        body = resp.json()
        flexi = next(c for c in body["categories"] if c["category_name"] == "Flexi Cap")
        assert flexi["manager_alpha_p50"] is not None
        assert flexi["manager_alpha_p90"] is not None
        # Pydantic serialises Decimal as string
        assert isinstance(flexi["manager_alpha_p50"], str)
        assert isinstance(flexi["manager_alpha_p90"], str)
        # Verify values match fixture
        assert Decimal(flexi["manager_alpha_p50"]) == Decimal("1.5")
        assert Decimal(flexi["manager_alpha_p90"]) == Decimal("2.8")

    def test_categories_quadrant_distribution_populated(self) -> None:
        universe, cat_rows, rs_batch, freshness = self._make_data()
        mock_svc = _patch_svc(universe, rs_batch, freshness, cat_rows=cat_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/categories")

        body = resp.json()
        flexi = next(c for c in body["categories"] if c["category_name"] == "Flexi Cap")
        # rs_composite=70 (>0) and rs_momentum_28d=5 (>0) → LEADING for all 3 funds
        qdist = flexi["quadrant_distribution"]
        assert isinstance(qdist, dict)
        assert qdist.get("LEADING", 0) == 3

    def test_categories_fund_count_matches_sql_active_count(self) -> None:
        """fund_count must equal active_fund_count from SQL (not universe row count)."""
        universe, cat_rows, rs_batch, freshness = self._make_data()
        mock_svc = _patch_svc(universe, rs_batch, freshness, cat_rows=cat_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/categories")

        body = resp.json()
        flexi = next(c for c in body["categories"] if c["category_name"] == "Flexi Cap")
        # cat_rows fixture has active_fund_count=3 for Flexi Cap
        assert flexi["fund_count"] == 3

    def test_categories_total_aum_is_decimal_string(self) -> None:
        universe, cat_rows, rs_batch, freshness = self._make_data()
        mock_svc = _patch_svc(universe, rs_batch, freshness, cat_rows=cat_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/categories")

        body = resp.json()
        for cat in body["categories"]:
            if cat.get("total_aum_cr") is not None:
                assert isinstance(cat["total_aum_cr"], str), (
                    f"total_aum_cr must be Decimal string, got {type(cat['total_aum_cr'])}"
                )


# ---------------------------------------------------------------------------
# /flows
# ---------------------------------------------------------------------------


class TestFlowsRoute:
    """Tests for GET /api/v1/mf/flows."""

    def test_flows_returns_200(self) -> None:
        flow_rows = _make_flow_rows(12)
        freshness = _make_freshness()
        mock_svc = _patch_svc([], {}, freshness, flow_rows=flow_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_flows_default_12_months(self) -> None:
        """Default months=12 must request 12 months from JIP service."""
        flow_rows = _make_flow_rows(12)
        freshness = _make_freshness()
        mock_svc = _patch_svc([], {}, freshness, flow_rows=flow_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        body = resp.json()
        assert len(body["flows"]) == 12
        mock_svc.get_mf_flows.assert_awaited_once_with(months=12)

    def test_flows_custom_months(self) -> None:
        flow_rows = _make_flow_rows(6)
        freshness = _make_freshness()
        mock_svc = _patch_svc([], {}, freshness, flow_rows=flow_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows?months=6")

        body = resp.json()
        assert len(body["flows"]) == 6
        mock_svc.get_mf_flows.assert_awaited_once_with(months=6)

    def test_flows_structure(self) -> None:
        flow_rows = _make_flow_rows(3)
        freshness = _make_freshness()
        mock_svc = _patch_svc([], {}, freshness, flow_rows=flow_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        body = resp.json()
        assert "flows" in body
        assert "data_as_of" in body
        assert "staleness" in body
        flow = body["flows"][0]
        for field in ("month_date", "category", "net_flow_cr", "aum_cr", "sip_flow_cr"):
            assert field in flow, f"Expected field '{field}' in FlowRow"

    def test_flows_financial_fields_are_decimal_strings(self) -> None:
        flow_rows = _make_flow_rows(3)
        freshness = _make_freshness()
        mock_svc = _patch_svc([], {}, freshness, flow_rows=flow_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        body = resp.json()
        for flow in body["flows"]:
            for field in (
                "net_flow_cr",
                "gross_inflow_cr",
                "gross_outflow_cr",
                "aum_cr",
                "sip_flow_cr",
            ):
                val = flow.get(field)
                if val is not None:
                    assert isinstance(val, str), (
                        f"Field '{field}' must be Decimal (str), got {type(val)}: {val}"
                    )

    def test_flows_empty_returns_200(self) -> None:
        freshness = _make_freshness()
        mock_svc = _patch_svc([], {}, freshness, flow_rows=[])

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        assert resp.status_code == 200
        body = resp.json()
        assert body["flows"] == []

    def test_flows_sip_accounts_and_folios_are_ints(self) -> None:
        flow_rows = _make_flow_rows(2)
        freshness = _make_freshness()
        mock_svc = _patch_svc([], {}, freshness, flow_rows=flow_rows)

        with patch("backend.routes.mf.JIPDataService", return_value=mock_svc):
            with patch("backend.routes.mf.get_db"):
                client = TestClient(app)
                resp = client.get("/api/v1/mf/flows")

        body = resp.json()
        for flow in body["flows"]:
            if flow.get("sip_accounts") is not None:
                assert isinstance(flow["sip_accounts"], int)
            if flow.get("folios") is not None:
                assert isinstance(flow["folios"], int)


# ---------------------------------------------------------------------------
# compute_category_rollup unit tests
# ---------------------------------------------------------------------------


class TestComputeCategoryRollup:
    """Unit tests for the compute_category_rollup helper."""

    def test_rollup_maps_fields_correctly(self) -> None:
        from backend.services.mf_compute import compute_category_rollup

        cat_rows = [
            {
                "category_name": "Flexi Cap",
                "broad_category": "Equity",
                "active_fund_count": 5,
                "avg_rs_composite": Decimal("70.0"),
                "manager_alpha_p50": Decimal("1.5"),
                "manager_alpha_p90": Decimal("2.8"),
                "net_flow_cr": Decimal("500.0"),
                "sip_flow_cr": Decimal("200.0"),
                "aum_cr": Decimal("50000.0"),
            }
        ]
        universe_rows: list[dict] = []

        result = compute_category_rollup(universe_rows, cat_rows)
        assert len(result) == 1
        row = result[0]
        assert row["fund_count"] == 5
        assert row["total_aum_cr"] == Decimal("50000.0")
        assert row["manager_alpha_p50"] == Decimal("1.5")
        assert row["manager_alpha_p90"] == Decimal("2.8")
        assert row["quadrant_distribution"] == {}

    def test_rollup_computes_quadrant_distribution(self) -> None:
        from backend.models.schemas import Quadrant
        from backend.services.mf_compute import compute_category_rollup

        universe = [
            {"category_name": "Flexi Cap", "quadrant": Quadrant.LEADING},
            {"category_name": "Flexi Cap", "quadrant": Quadrant.LEADING},
            {"category_name": "Flexi Cap", "quadrant": Quadrant.IMPROVING},
            {"category_name": "Large Cap", "quadrant": Quadrant.LAGGING},
        ]
        cat_rows = [
            {
                "category_name": "Flexi Cap",
                "broad_category": "Equity",
                "active_fund_count": 3,
                "avg_rs_composite": Decimal("70.0"),
                "manager_alpha_p50": None,
                "manager_alpha_p90": None,
                "net_flow_cr": None,
                "sip_flow_cr": None,
                "aum_cr": None,
            },
            {
                "category_name": "Large Cap",
                "broad_category": "Equity",
                "active_fund_count": 1,
                "avg_rs_composite": None,
                "manager_alpha_p50": None,
                "manager_alpha_p90": None,
                "net_flow_cr": None,
                "sip_flow_cr": None,
                "aum_cr": None,
            },
        ]

        result = compute_category_rollup(universe, cat_rows)
        flexi = next(r for r in result if r["category_name"] == "Flexi Cap")
        large = next(r for r in result if r["category_name"] == "Large Cap")

        assert flexi["quadrant_distribution"]["LEADING"] == 2
        assert flexi["quadrant_distribution"]["IMPROVING"] == 1
        assert large["quadrant_distribution"]["LAGGING"] == 1

    def test_rollup_empty_cat_rows_returns_empty(self) -> None:
        from backend.services.mf_compute import compute_category_rollup

        result = compute_category_rollup([], [])
        assert result == []

    def test_rollup_null_active_fund_count_defaults_to_zero(self) -> None:
        from backend.services.mf_compute import compute_category_rollup

        cat_rows = [
            {
                "category_name": "Flexi Cap",
                "broad_category": "Equity",
                "active_fund_count": None,  # NULL from DB
                "avg_rs_composite": None,
                "manager_alpha_p50": None,
                "manager_alpha_p90": None,
                "net_flow_cr": None,
                "sip_flow_cr": None,
                "aum_cr": None,
            }
        ]
        result = compute_category_rollup([], cat_rows)
        assert result[0]["fund_count"] == 0

    def test_rollup_fund_with_none_quadrant_excluded_from_distribution(self) -> None:
        from backend.services.mf_compute import compute_category_rollup

        universe = [
            {"category_name": "Flexi Cap", "quadrant": None},  # no RS data
            {"category_name": "Flexi Cap", "quadrant": None},
        ]
        cat_rows = [
            {
                "category_name": "Flexi Cap",
                "broad_category": "Equity",
                "active_fund_count": 2,
                "avg_rs_composite": None,
                "manager_alpha_p50": None,
                "manager_alpha_p90": None,
                "net_flow_cr": None,
                "sip_flow_cr": None,
                "aum_cr": None,
            }
        ]
        result = compute_category_rollup(universe, cat_rows)
        assert result[0]["quadrant_distribution"] == {}


# ---------------------------------------------------------------------------
# Staleness logic unit tests
# ---------------------------------------------------------------------------


class TestStalenessLogic:
    """Unit tests for _compute_staleness helper."""

    def test_fresh_when_today(self) -> None:
        from backend.routes.mf import _compute_staleness

        freshness = {"nav_as_of": datetime.date.today()}
        s = _compute_staleness(freshness)
        assert s.flag.value == "FRESH"
        assert s.age_minutes == 0

    def test_stale_when_1_day_old(self) -> None:
        from backend.routes.mf import _compute_staleness

        freshness = {"nav_as_of": datetime.date.today() - datetime.timedelta(days=1)}
        s = _compute_staleness(freshness)
        assert s.flag.value == "STALE"
        assert s.age_minutes == 1440

    def test_expired_when_2_days_old(self) -> None:
        from backend.routes.mf import _compute_staleness

        freshness = {"nav_as_of": datetime.date.today() - datetime.timedelta(days=2)}
        s = _compute_staleness(freshness)
        assert s.flag.value == "EXPIRED"

    def test_expired_when_no_nav_as_of(self) -> None:
        from backend.routes.mf import _compute_staleness

        freshness: dict = {}
        s = _compute_staleness(freshness)
        assert s.flag.value == "EXPIRED"
