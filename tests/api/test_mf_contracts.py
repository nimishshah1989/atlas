"""Contract tests for V2 MF API skeleton (chunk V2-1).

Verifies:
- Every endpoint declared in `specs/001-mf-slice/contracts/mf-api.md`
  is mounted on the FastAPI app under `/api/v1/mf/...`.
- Each route is annotated with its Pydantic `response_model`.
- The skeleton refuses to serve synthetic data: every endpoint returns
  HTTP 501 until V2-2+ wire the JIP client + computations.
- Pydantic models construct cleanly from spec-shaped fixtures using
  `Decimal` for every numeric field (no `float` anywhere).
- The source modules `backend/models/mf.py` and `backend/routes/mf.py`
  contain zero `float` occurrences.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import mf as mf_models
from backend.models.mf import (
    BroadCategoryGroup,
    CategoriesResponse,
    CategoryGroup,
    CategoryRow,
    ConvictionPillarsMF,
    FlowRow,
    FlowsResponse,
    Fund,
    FundDailyMetrics,
    FundDeepDiveResponse,
    FundHoldingStockEntry,
    FundIdentity,
    FundRSHistoryResponse,
    FundSector,
    FundSectorsResponse,
    Holding,
    HoldingsResponse,
    HoldingStockResponse,
    NAVHistoryResponse,
    NAVPoint,
    OverlapHolding,
    OverlapResponse,
    PillarFlows,
    PillarHoldingsQuality,
    PillarPerformance,
    PillarRSStrength,
    RSHistoryPoint,
    SectorExposureSummary,
    Staleness,
    StalenessFlag,
    TopHoldingSummary,
    UniverseResponse,
    WeightedTechnicalsResponse,
    WeightedTechnicalsSummary,
)
from backend.models.schemas import Quadrant
from backend.routes import mf as mf_routes

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_PATH = REPO_ROOT / "backend" / "models" / "mf.py"
ROUTES_PATH = REPO_ROOT / "backend" / "routes" / "mf.py"

EXPECTED_ROUTES: list[tuple[str, str, type]] = [
    ("GET", "/api/v1/mf/universe", UniverseResponse),
    ("GET", "/api/v1/mf/categories", CategoriesResponse),
    ("GET", "/api/v1/mf/flows", FlowsResponse),
    ("GET", "/api/v1/mf/overlap", OverlapResponse),
    ("GET", "/api/v1/mf/holding-stock/{symbol}", HoldingStockResponse),
    ("GET", "/api/v1/mf/{mstar_id}", FundDeepDiveResponse),
    ("GET", "/api/v1/mf/{mstar_id}/holdings", HoldingsResponse),
    ("GET", "/api/v1/mf/{mstar_id}/sectors", FundSectorsResponse),
    ("GET", "/api/v1/mf/{mstar_id}/rs-history", FundRSHistoryResponse),
    ("GET", "/api/v1/mf/{mstar_id}/weighted-technicals", WeightedTechnicalsResponse),
    ("GET", "/api/v1/mf/{mstar_id}/nav-history", NAVHistoryResponse),
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# --- Router mounted ----------------------------------------------------


def _route_index() -> dict[tuple[str, str], object]:
    idx: dict[tuple[str, str], object] = {}
    for r in app.routes:
        methods = getattr(r, "methods", None) or set()
        path = getattr(r, "path", None)
        if not path:
            continue
        for m in methods:
            idx[(m, path)] = r
    return idx


def test_router_is_mounted_on_app() -> None:
    """The MF router is included in the FastAPI app and uses the /api/v1/mf prefix."""
    assert mf_routes.router.prefix == "/api/v1/mf"
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.startswith("/api/v1/mf") for p in paths), "mf router not mounted on app"


@pytest.mark.parametrize("method,path,model", EXPECTED_ROUTES)
def test_endpoint_declared_with_response_model(method: str, path: str, model: type) -> None:
    """Every contract endpoint exists and binds to the right Pydantic response_model."""
    idx = _route_index()
    route = idx.get((method, path))
    assert route is not None, f"missing route: {method} {path}"
    declared = getattr(route, "response_model", None)
    assert declared is model, f"{method} {path}: response_model={declared!r}, want {model!r}"


# --- Skeleton refuses to serve synthetic data --------------------------


SKELETON_CALLS: list[tuple[str, str]] = [
    # /universe, /categories, /flows wired in V2-4 — removed from 501 list
    # /{mstar_id}, /{mstar_id}/holdings, /{mstar_id}/sectors wired in V2-5 — removed from 501 list
    # /overlap, /holding-stock, /nav-history wired in V2-7 — removed from 501 list
    ("GET", "/api/v1/mf/F00000ABCD/rs-history"),
    ("GET", "/api/v1/mf/F00000ABCD/weighted-technicals"),
]


@pytest.mark.parametrize("method,url", SKELETON_CALLS)
def test_skeleton_returns_501(client: TestClient, method: str, url: str) -> None:
    """Endpoints not yet wired must still 501 (no synthetic data)."""
    resp = client.request(method, url)
    assert resp.status_code == 501, f"{method} {url} → {resp.status_code} body={resp.text}"
    body = resp.json()
    assert "not yet wired" in body.get("detail", "").lower()


# --- Pydantic models construct from Decimal-only fixtures --------------


def _staleness() -> Staleness:
    return Staleness(source="jip", age_minutes=15, flag=StalenessFlag.FRESH)


def test_universe_model_constructs_from_decimal_fixture() -> None:
    fund = Fund(
        mstar_id="F00000ABCD",
        fund_name="Sample Equity Fund",
        amc_name="Sample AMC",
        category_name="Flexi Cap",
        broad_category="Equity",
        nav=Decimal("123.4500"),
        nav_date=date(2026, 4, 10),
        rs_composite=Decimal("82.50"),
        rs_momentum_28d=Decimal("4.10"),
        quadrant=Quadrant.LEADING,
        manager_alpha=Decimal("2.30"),
        expense_ratio=Decimal("0.65"),
        is_index_fund=False,
        primary_benchmark="NIFTY 500 TRI",
    )
    resp = UniverseResponse(
        broad_categories=[
            BroadCategoryGroup(
                name="Equity",
                categories=[CategoryGroup(name="Flexi Cap", funds=[fund])],
            )
        ],
        data_as_of=date(2026, 4, 10),
        staleness=_staleness(),
    )
    assert resp.broad_categories[0].categories[0].funds[0].nav == Decimal("123.4500")
    assert isinstance(resp.broad_categories[0].categories[0].funds[0].rs_composite, Decimal)


def test_categories_model_constructs() -> None:
    row = CategoryRow(
        category_name="Flexi Cap",
        broad_category="Equity",
        fund_count=42,
        avg_rs_composite=Decimal("71.20"),
        quadrant_distribution={"LEADING": 10, "IMPROVING": 12, "WEAKENING": 8, "LAGGING": 12},
        net_flow_cr=Decimal("1234.50"),
        sip_flow_cr=Decimal("567.80"),
        total_aum_cr=Decimal("123456.78"),
        manager_alpha_p50=Decimal("1.20"),
        manager_alpha_p90=Decimal("3.40"),
    )
    resp = CategoriesResponse(
        categories=[row], data_as_of=date(2026, 4, 10), staleness=_staleness()
    )
    assert isinstance(resp.categories[0].total_aum_cr, Decimal)


def test_flows_model_constructs() -> None:
    row = FlowRow(
        month_date=date(2026, 3, 1),
        category="Flexi Cap",
        net_flow_cr=Decimal("100.50"),
        gross_inflow_cr=Decimal("500.00"),
        gross_outflow_cr=Decimal("399.50"),
        aum_cr=Decimal("12345.67"),
        sip_flow_cr=Decimal("75.25"),
        sip_accounts=123456,
        folios=987654,
    )
    resp = FlowsResponse(flows=[row], data_as_of=date(2026, 4, 10), staleness=_staleness())
    assert isinstance(resp.flows[0].net_flow_cr, Decimal)


def test_fund_deep_dive_model_constructs() -> None:
    pillars = ConvictionPillarsMF(
        performance=PillarPerformance(
            manager_alpha=Decimal("2.10"),
            information_ratio=Decimal("0.85"),
            capture_up=Decimal("105.20"),
            capture_down=Decimal("88.40"),
        ),
        rs_strength=PillarRSStrength(
            rs_composite=Decimal("80.10"),
            rs_momentum_28d=Decimal("3.40"),
            quadrant=Quadrant.LEADING,
        ),
        flows=PillarFlows(
            net_flow_cr_3m=Decimal("250.40"),
            sip_flow_cr_3m=Decimal("90.10"),
            folio_growth_pct=Decimal("4.20"),
        ),
        holdings_quality=PillarHoldingsQuality(
            holdings_avg_rs=Decimal("72.30"),
            pct_above_200dma=Decimal("78.00"),
            concentration_top10_pct=Decimal("48.20"),
        ),
    )
    resp = FundDeepDiveResponse(
        identity=FundIdentity(
            mstar_id="F00000ABCD",
            fund_name="Sample Equity Fund",
            amc_name="Sample AMC",
            category_name="Flexi Cap",
            broad_category="Equity",
            primary_benchmark="NIFTY 500 TRI",
            inception_date=date(2010, 1, 1),
        ),
        daily=FundDailyMetrics(
            nav=Decimal("123.4500"),
            nav_date=date(2026, 4, 10),
            aum_cr=Decimal("12345.67"),
            expense_ratio=Decimal("0.65"),
            return_1y=Decimal("18.40"),
        ),
        pillars=pillars,
        sector_exposure=SectorExposureSummary(
            top_sector="Financial Services",
            top_sector_weight_pct=Decimal("28.40"),
            sector_count=11,
        ),
        top_holdings=[
            TopHoldingSummary(
                symbol="HDFCBANK", holding_name="HDFC Bank", weight_pct=Decimal("8.20")
            )
        ],
        weighted_technicals=WeightedTechnicalsSummary(
            weighted_rsi=Decimal("58.20"),
            weighted_breadth_pct_above_200dma=Decimal("72.00"),
            weighted_macd_bullish_pct=Decimal("66.50"),
            as_of_date=date(2026, 4, 10),
        ),
        data_as_of=date(2026, 4, 10),
        staleness=_staleness(),
    )
    assert isinstance(resp.daily.nav, Decimal)
    assert isinstance(resp.pillars.performance.manager_alpha, Decimal)


def test_holdings_model_constructs() -> None:
    h = Holding(
        instrument_id="INE040A01034",
        symbol="HDFCBANK",
        holding_name="HDFC Bank",
        weight_pct=Decimal("8.20"),
        shares_held=Decimal("123456.0000"),
        market_value=Decimal("9876543.21"),
        sector="Financial Services",
        rs_composite=Decimal("75.40"),
        above_200dma=True,
    )
    resp = HoldingsResponse(
        holdings=[h], as_of_date=date(2026, 4, 10), coverage_pct=Decimal("98.50"), warnings=[]
    )
    assert isinstance(resp.coverage_pct, Decimal)


def test_fund_sectors_model_constructs() -> None:
    resp = FundSectorsResponse(
        sectors=[
            FundSector(
                sector="Financial Services",
                weight_pct=Decimal("28.40"),
                stock_count=8,
                sector_rs_composite=Decimal("72.10"),
            )
        ],
        as_of_date=date(2026, 4, 10),
    )
    assert isinstance(resp.sectors[0].weight_pct, Decimal)


def test_rs_history_model_constructs() -> None:
    resp = FundRSHistoryResponse(
        mstar_id="F00000ABCD",
        points=[RSHistoryPoint(as_of_date=date(2026, 4, 10), rs_composite=Decimal("80.10"))],
        data_as_of=date(2026, 4, 10),
        staleness=_staleness(),
    )
    assert isinstance(resp.points[0].rs_composite, Decimal)


def test_weighted_technicals_model_constructs() -> None:
    resp = WeightedTechnicalsResponse(
        mstar_id="F00000ABCD",
        weighted_rsi=Decimal("58.20"),
        weighted_breadth_pct_above_200dma=Decimal("72.00"),
        weighted_macd_bullish_pct=Decimal("66.50"),
        as_of_date=date(2026, 4, 10),
        data_as_of=date(2026, 4, 10),
        staleness=_staleness(),
    )
    assert isinstance(resp.weighted_rsi, Decimal)


def test_nav_history_model_constructs() -> None:
    resp = NAVHistoryResponse(
        mstar_id="F00000ABCD",
        points=[NAVPoint(nav_date=date(2026, 4, 10), nav=Decimal("123.4500"))],
        coverage_gap_days=0,
        data_as_of=date(2026, 4, 10),
        staleness=_staleness(),
    )
    assert isinstance(resp.points[0].nav, Decimal)


def test_overlap_model_constructs() -> None:
    resp = OverlapResponse(
        fund_a="F0001",
        fund_b="F0002",
        overlap_pct=Decimal("42.50"),
        common_holdings=[
            OverlapHolding(
                instrument_id="INE040A01034",
                symbol="HDFCBANK",
                weight_a=Decimal("8.20"),
                weight_b=Decimal("6.40"),
            )
        ],
        data_as_of=date(2026, 4, 10),
        staleness=_staleness(),
    )
    assert isinstance(resp.overlap_pct, Decimal)


def test_holding_stock_model_constructs() -> None:
    resp = HoldingStockResponse(
        symbol="HDFCBANK",
        instrument_id="INE040A01034",
        funds=[
            FundHoldingStockEntry(
                mstar_id="F0001", fund_name="Sample Equity Fund", weight_pct=Decimal("8.20")
            )
        ],
        data_as_of=date(2026, 4, 10),
        staleness=_staleness(),
    )
    assert isinstance(resp.funds[0].weight_pct, Decimal)


# --- Zero-float invariant ----------------------------------------------


_FLOAT_TOKEN = re.compile(r"\bfloat\b")


@pytest.mark.parametrize("path", [MODELS_PATH, ROUTES_PATH])
def test_no_float_in_mf_source(path: Path) -> None:
    """`float` MUST NOT appear in models/mf.py or routes/mf.py — Decimal only."""
    text = path.read_text(encoding="utf-8")
    matches = _FLOAT_TOKEN.findall(text)
    assert matches == [], f"{path.name} contains forbidden 'float' occurrences: {matches}"


def test_models_module_exports_all_response_types() -> None:
    """Sanity: every contract response model is importable from the module."""
    for name in (
        "UniverseResponse",
        "CategoriesResponse",
        "FlowsResponse",
        "FundDeepDiveResponse",
        "HoldingsResponse",
        "FundSectorsResponse",
        "FundRSHistoryResponse",
        "WeightedTechnicalsResponse",
        "NAVHistoryResponse",
        "OverlapResponse",
        "HoldingStockResponse",
    ):
        assert hasattr(mf_models, name), f"backend.models.mf missing {name}"
