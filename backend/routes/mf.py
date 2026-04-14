"""ATLAS V2 MF (mutual fund) API — router with wired universe/categories/flows.

Chunk V2-4 wires /universe, /categories, /flows with real JIP data.
Remaining endpoints (/overlap, deep dive, holdings, sectors, rs-history,
weighted-technicals, nav-history) stay as 501 stubs until later V2 chunks.
"""

import datetime
from collections import defaultdict
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.clients.sql_fragments import safe_decimal
from backend.db.session import get_db
from backend.models.mf import (
    BroadCategoryGroup,
    CategoriesResponse,
    CategoryGroup,
    CategoryRow,
    FlowRow,
    FlowsResponse,
    FundDeepDiveResponse,
    FundRSHistoryResponse,
    FundSectorsResponse,
    HoldingsResponse,
    HoldingStockResponse,
    NAVHistoryResponse,
    OverlapResponse,
    Staleness,
    StalenessFlag,
    UniverseResponse,
    WeightedTechnicalsResponse,
)
from backend.models.mf import Fund
from backend.services.mf_compute import classify_fund_quadrant, compute_category_rollup
from backend.services.uql import engine as uql_engine

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/mf", tags=["mf"])


_NOT_IMPL = "MF endpoint not yet wired (V2-1 contract skeleton)"

LEGACY_ENDPOINT_IDS: tuple[str, ...] = (
    "mf.universe",
    "mf.categories",
    "mf.flows",
    "mf.overlap",
    "mf.holding_stock",
    "mf.deep_dive",
    "mf.holdings",
    "mf.sectors",
    "mf.rs_history",
    "mf.weighted_technicals",
    "mf.nav_history",
)


def build_uql_request(endpoint_id: str, params: dict[str, Any]) -> Any:
    """Translate a legacy mf endpoint call into a UQLRequest.

    Thin shim onto :func:`uql_engine.build_from_legacy`. Per spec §17/§20
    every fixed endpoint must be expressible as a UQL request; the engine
    grows one branch per id. Currently delegates straight through — when a
    later V2 chunk wires real data, route handlers swap their JIPDataService
    calls for ``await uql_engine.execute(build_uql_request(...))`` without
    changing this seam.
    """
    return uql_engine.build_from_legacy(endpoint_id, params)


def _not_implemented() -> HTTPException:
    return HTTPException(status_code=501, detail=_NOT_IMPL)


def _compute_staleness(freshness: dict[str, Any], source: str = "jip") -> Staleness:
    """Compute staleness from JIP freshness data.

    Uses nav_as_of as the primary staleness signal.
    age < 1440 min (24h) → FRESH
    age < 2880 min (48h) → STALE
    else → EXPIRED
    """
    nav_as_of = freshness.get("nav_as_of")
    if nav_as_of is None:
        return Staleness(source=source, age_minutes=99999, flag=StalenessFlag.EXPIRED)

    if isinstance(nav_as_of, datetime.datetime):
        nav_date = nav_as_of.date()
    elif isinstance(nav_as_of, datetime.date):
        nav_date = nav_as_of
    else:
        try:
            nav_date = datetime.date.fromisoformat(str(nav_as_of))
        except (ValueError, TypeError):
            return Staleness(source=source, age_minutes=99999, flag=StalenessFlag.EXPIRED)

    today = datetime.date.today()
    age_days = (today - nav_date).days
    age_minutes = age_days * 24 * 60

    if age_minutes < 1440:
        flag = StalenessFlag.FRESH
    elif age_minutes < 2880:
        flag = StalenessFlag.STALE
    else:
        flag = StalenessFlag.EXPIRED

    return Staleness(source=source, age_minutes=age_minutes, flag=flag)


def _data_as_of_from_freshness(freshness: dict[str, Any]) -> datetime.date:
    """Extract data_as_of date from freshness dict, defaulting to today."""
    nav_as_of = freshness.get("nav_as_of")
    if nav_as_of is None:
        return datetime.date.today()
    if isinstance(nav_as_of, datetime.datetime):
        return nav_as_of.date()
    if isinstance(nav_as_of, datetime.date):
        return nav_as_of
    try:
        return datetime.date.fromisoformat(str(nav_as_of))
    except (ValueError, TypeError):
        return datetime.date.today()


def _enrich_universe_row_to_fund(
    universe_row: dict[str, Any],
    rs_batch: dict[str, dict[str, Any]],
) -> Fund:
    """Build a Fund model from a JIP universe row, enriched with RS momentum + quadrant."""
    mstar_id = universe_row.get("mstar_id", "")
    momentum_data = rs_batch.get(mstar_id, {})
    rs_composite = safe_decimal(
        universe_row.get("derived_rs_composite") or universe_row.get("rs_composite")
    )
    rs_momentum_28d = momentum_data.get("rs_momentum_28d") if momentum_data else None
    return Fund(
        mstar_id=mstar_id,
        fund_name=universe_row.get("fund_name", ""),
        amc_name=universe_row.get("amc_name", ""),
        category_name=universe_row.get("category_name", ""),
        broad_category=universe_row.get("broad_category", ""),
        nav=safe_decimal(universe_row.get("nav")),
        nav_date=universe_row.get("nav_date"),
        rs_composite=rs_composite,
        rs_momentum_28d=rs_momentum_28d,
        quadrant=classify_fund_quadrant(rs_composite, rs_momentum_28d),
        manager_alpha=safe_decimal(universe_row.get("manager_alpha")),
        expense_ratio=safe_decimal(universe_row.get("expense_ratio")),
        is_index_fund=bool(universe_row.get("is_index_fund", False)),
        primary_benchmark=universe_row.get("primary_benchmark"),
    )


def _group_funds_by_broad_category(
    universe_rows: list[dict[str, Any]],
    rs_batch: dict[str, dict[str, Any]],
) -> list[BroadCategoryGroup]:
    """Group flat JIP universe rows into BroadCategoryGroup → CategoryGroup → Fund hierarchy."""
    funds_by_broad: dict[str, dict[str, list[Fund]]] = defaultdict(lambda: defaultdict(list))
    for universe_row in universe_rows:
        fund = _enrich_universe_row_to_fund(universe_row, rs_batch)
        bc = universe_row.get("broad_category") or "Unknown"
        cn = universe_row.get("category_name") or "Unknown"
        funds_by_broad[bc][cn].append(fund)
    return [
        BroadCategoryGroup(
            name=bc,
            categories=[CategoryGroup(name=cn, funds=funds) for cn, funds in cat_map.items()],
        )
        for bc, cat_map in funds_by_broad.items()
    ]


@router.get("/universe", response_model=UniverseResponse)
async def get_universe(
    benchmark: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    broad_category: Optional[str] = Query(None),
    active_only: Optional[bool] = Query(True),
    db: AsyncSession = Depends(get_db),
) -> UniverseResponse:
    """Get MF universe grouped by broad_category → category → funds.

    Wires real JIP data. ETFs are always excluded (enforced by JIP service).
    """
    svc = JIPDataService(db)
    effective_active_only = active_only if active_only is not None else True
    rows, rs_batch, freshness = await _gather_universe_data(
        svc,
        benchmark=benchmark,
        category=category,
        broad_category=broad_category,
        active_only=effective_active_only,
    )
    broad_categories = _group_funds_by_broad_category(rows, rs_batch)
    data_as_of = _data_as_of_from_freshness(freshness)
    staleness = _compute_staleness(freshness)
    total_funds = sum(len(cg.funds) for bg in broad_categories for cg in bg.categories)
    log.info(
        "mf_universe_route_complete",
        broad_categories=len(broad_categories),
        total_funds=total_funds,
        data_as_of=str(data_as_of),
    )
    return UniverseResponse(
        broad_categories=broad_categories,
        data_as_of=data_as_of,
        staleness=staleness,
    )


async def _gather_universe_data(
    svc: JIPDataService,
    *,
    benchmark: Optional[str],
    category: Optional[str],
    broad_category: Optional[str],
    active_only: bool,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Fetch universe rows, RS batch, and freshness concurrently (sequential for now)."""
    rows = await svc.get_mf_universe(
        benchmark=benchmark,
        category=category,
        broad_category=broad_category,
        active_only=active_only,
    )
    rs_batch = await svc.get_mf_rs_momentum_batch()
    freshness = await svc.get_mf_data_freshness()
    return rows, rs_batch, freshness


@router.get("/categories", response_model=CategoriesResponse)
async def get_categories(
    db: AsyncSession = Depends(get_db),
) -> CategoriesResponse:
    """Get category-level rollup: fund counts, RS composite, flows, quadrant distribution.

    p50/p90 manager_alpha computed in SQL via PERCENTILE_CONT.
    Quadrant distribution computed from enriched universe rows.
    """
    svc = JIPDataService(db)

    cat_rows = await svc.get_mf_categories()
    universe_rows = await svc.get_mf_universe(active_only=True)
    rs_batch = await svc.get_mf_rs_momentum_batch()
    freshness = await svc.get_mf_data_freshness()

    # Enrich universe rows with quadrant for quadrant_distribution computation
    enriched_universe: list[dict[str, Any]] = []
    for row in universe_rows:
        mstar_id = row.get("mstar_id", "")
        momentum_data = rs_batch.get(mstar_id, {})
        rs_composite = safe_decimal(row.get("derived_rs_composite") or row.get("rs_composite"))
        rs_momentum_28d = momentum_data.get("rs_momentum_28d") if momentum_data else None
        enriched = dict(row)
        enriched["quadrant"] = classify_fund_quadrant(rs_composite, rs_momentum_28d)
        enriched_universe.append(enriched)

    rollup = compute_category_rollup(enriched_universe, cat_rows)

    categories = [
        CategoryRow(
            category_name=r["category_name"],
            broad_category=r["broad_category"],
            fund_count=r["fund_count"],
            avg_rs_composite=r.get("avg_rs_composite"),
            quadrant_distribution=r.get("quadrant_distribution", {}),
            net_flow_cr=r.get("net_flow_cr"),
            sip_flow_cr=r.get("sip_flow_cr"),
            total_aum_cr=r.get("total_aum_cr"),
            manager_alpha_p50=r.get("manager_alpha_p50"),
            manager_alpha_p90=r.get("manager_alpha_p90"),
        )
        for r in rollup
    ]

    data_as_of = _data_as_of_from_freshness(freshness)
    staleness = _compute_staleness(freshness)

    log.info(
        "mf_categories_route_complete",
        category_count=len(categories),
        data_as_of=str(data_as_of),
    )

    return CategoriesResponse(
        categories=categories,
        data_as_of=data_as_of,
        staleness=staleness,
    )


@router.get("/flows", response_model=FlowsResponse)
async def get_flows(
    months: Optional[int] = Query(12, ge=1, le=120),
    db: AsyncSession = Depends(get_db),
) -> FlowsResponse:
    """Get category-level flows for the last N months (default 12)."""
    svc = JIPDataService(db)
    effective_months = months if months is not None else 12

    flow_rows = await svc.get_mf_flows(months=effective_months)
    freshness = await svc.get_mf_data_freshness()

    flows = [
        FlowRow(
            month_date=row["month_date"],
            category=row.get("category", ""),
            net_flow_cr=safe_decimal(row.get("net_flow_cr")),
            gross_inflow_cr=safe_decimal(row.get("gross_inflow_cr")),
            gross_outflow_cr=safe_decimal(row.get("gross_outflow_cr")),
            aum_cr=safe_decimal(row.get("aum_cr")),
            sip_flow_cr=safe_decimal(row.get("sip_flow_cr")),
            sip_accounts=row.get("sip_accounts"),
            folios=row.get("folios"),
        )
        for row in flow_rows
    ]

    data_as_of = _data_as_of_from_freshness(freshness)
    staleness = _compute_staleness(freshness)

    log.info(
        "mf_flows_route_complete",
        flow_count=len(flows),
        months=effective_months,
        data_as_of=str(data_as_of),
    )

    return FlowsResponse(
        flows=flows,
        data_as_of=data_as_of,
        staleness=staleness,
    )


@router.get("/overlap", response_model=OverlapResponse)
async def get_overlap(
    funds: str = Query(..., description="Comma-separated mstar_ids: A,B"),
) -> OverlapResponse:
    raise _not_implemented()


@router.get("/holding-stock/{symbol}", response_model=HoldingStockResponse)
async def get_holding_stock(symbol: str) -> HoldingStockResponse:
    raise _not_implemented()


@router.get("/{mstar_id}/holdings", response_model=HoldingsResponse)
async def get_fund_holdings(mstar_id: str) -> HoldingsResponse:
    raise _not_implemented()


@router.get("/{mstar_id}/sectors", response_model=FundSectorsResponse)
async def get_fund_sectors(mstar_id: str) -> FundSectorsResponse:
    raise _not_implemented()


@router.get("/{mstar_id}/rs-history", response_model=FundRSHistoryResponse)
async def get_fund_rs_history(
    mstar_id: str,
    months: Optional[int] = Query(12, ge=1, le=120),
) -> FundRSHistoryResponse:
    raise _not_implemented()


@router.get("/{mstar_id}/weighted-technicals", response_model=WeightedTechnicalsResponse)
async def get_fund_weighted_technicals(mstar_id: str) -> WeightedTechnicalsResponse:
    raise _not_implemented()


@router.get("/{mstar_id}/nav-history", response_model=NAVHistoryResponse)
async def get_fund_nav_history(
    mstar_id: str,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
) -> NAVHistoryResponse:
    raise _not_implemented()


@router.get("/{mstar_id}", response_model=FundDeepDiveResponse)
async def get_fund_deep_dive(mstar_id: str) -> FundDeepDiveResponse:
    raise _not_implemented()
