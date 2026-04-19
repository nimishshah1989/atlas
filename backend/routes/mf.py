"""ATLAS V2 MF (mutual fund) API — router with wired universe/categories/flows."""

import asyncio
import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.clients.sql_fragments import safe_decimal
from backend.db.session import get_db
from backend.services.uql import engine as uql_engine  # noqa: F401  # API standard §17
from backend.models.mf import (
    CategoriesResponse,
    CategoryRow,
    FlowRow,
    FlowsResponse,
    FundDeepDiveResponse,
    FundHoldingStockEntry,
    FundRSHistoryResponse,
    FundSector,
    FundSectorsResponse,
    HoldingsResponse,
    HoldingStockResponse,
    NAVHistoryResponse,
    OverlapHolding,
    OverlapResponse,
    SectorExposureSummary,
    UniverseResponse,
    WeightedTechnicalsResponse,
)
from backend.routes.mf_helpers import (
    build_deep_dive_daily,
    build_deep_dive_identity,
    build_deep_dive_pillars,
    build_lifecycle_event,
    build_nav_history,
    build_weighted_technicals,
    build_weighted_technicals_response,
    compute_staleness,
    data_as_of_from_freshness,
    fetch_deep_dive_detail,
    fetch_deep_dive_freshness,
    fetch_deep_dive_lifecycle,
    fetch_deep_dive_rs_batch,
    fetch_mf_conviction_series,
    gather_universe_data,
    group_funds_by_broad_category,
    map_holding_row,
    not_implemented,
    parse_as_of_date,
    rs_momentum_or_empty,
)
from backend.services.mf_compute import classify_fund_quadrant, compute_category_rollup

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/mf", tags=["mf"])
# NOTE: /top-rs and /rank routes live in backend.routes.mf_rank (registered separately)


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
    rows, rs_batch, freshness = await gather_universe_data(
        svc,
        db,
        benchmark=benchmark,
        category=category,
        broad_category=broad_category,
        active_only=effective_active_only,
    )
    broad_categories = group_funds_by_broad_category(rows, rs_batch)
    data_as_of = data_as_of_from_freshness(freshness)
    staleness = compute_staleness(freshness)
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
    rs_batch = await rs_momentum_or_empty(svc, db)
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

    data_as_of = data_as_of_from_freshness(freshness)
    staleness = compute_staleness(freshness)

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

    data_as_of = data_as_of_from_freshness(freshness)
    staleness = compute_staleness(freshness)

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
    db: AsyncSession = Depends(get_db),
) -> OverlapResponse:
    """Compute portfolio overlap between exactly two funds.

    Returns overlap_pct (Jaccard-style weight overlap) and common_holdings list.
    Exactly 2 mstar_ids must be supplied; 400 otherwise.
    """
    fund_ids = [f.strip() for f in funds.split(",") if f.strip()]
    if len(fund_ids) != 2:
        raise HTTPException(
            status_code=400,
            detail=f"Exactly 2 fund IDs required (comma-separated), got {len(fund_ids)}",
        )
    fund_a, fund_b = fund_ids[0], fund_ids[1]

    svc = JIPDataService(db)
    overlap_data = await svc.get_fund_overlap(fund_a, fund_b)
    freshness = await svc.get_mf_data_freshness()

    common_holdings = [
        OverlapHolding(
            instrument_id=str(h.get("instrument_id") or ""),
            symbol=str(h.get("holding_name") or ""),
            weight_a=safe_decimal(h.get("weight_pct_a")) or Decimal("0"),
            weight_b=safe_decimal(h.get("weight_pct_b")) or Decimal("0"),
        )
        for h in overlap_data.get("common_holdings", [])
    ]

    data_as_of = data_as_of_from_freshness(freshness)
    staleness = compute_staleness(freshness)

    log.info(
        "mf_overlap_route_complete",
        fund_a=fund_a,
        fund_b=fund_b,
        overlap_pct=str(overlap_data.get("overlap_pct")),
        common_count=overlap_data.get("common_count"),
    )

    return OverlapResponse(
        fund_a=fund_a,
        fund_b=fund_b,
        overlap_pct=overlap_data.get("overlap_pct") or Decimal("0"),
        common_holdings=common_holdings,
        data_as_of=data_as_of,
        staleness=staleness,
    )


@router.get("/holding-stock/{symbol}", response_model=HoldingStockResponse)
async def get_holding_stock(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> HoldingStockResponse:
    """Get all mutual funds that hold a specific stock symbol.

    Returns funds sorted by weight_pct descending.
    """
    svc = JIPDataService(db)
    holder_rows = await svc.get_mf_holders(symbol)
    freshness = await svc.get_mf_data_freshness()

    funds = [
        FundHoldingStockEntry(
            mstar_id=str(row.get("mstar_id") or ""),
            fund_name=str(row.get("fund_name") or ""),
            weight_pct=safe_decimal(row.get("weight_pct")) or Decimal("0"),
        )
        for row in holder_rows
        if row.get("weight_pct") is not None
    ]
    # Sort by weight_pct descending
    funds.sort(key=lambda f: f.weight_pct, reverse=True)

    data_as_of = data_as_of_from_freshness(freshness)
    staleness = compute_staleness(freshness)

    log.info(
        "mf_holding_stock_route_complete",
        symbol=symbol.upper(),
        fund_count=len(funds),
    )

    return HoldingStockResponse(
        symbol=symbol.upper(),
        funds=funds,
        data_as_of=data_as_of,
        staleness=staleness,
    )


@router.get("/{mstar_id}/holdings", response_model=HoldingsResponse)
async def get_fund_holdings(
    mstar_id: str,
    db: AsyncSession = Depends(get_db),
) -> HoldingsResponse:
    """Get latest holdings for a fund with stock RS and technicals."""
    svc = JIPDataService(db)
    holding_rows = await svc.get_fund_holdings(mstar_id)

    holdings = [h for row in holding_rows if (h := map_holding_row(row)) is not None]
    coverage_pct = sum((h.weight_pct for h in holdings), Decimal("0")) if holdings else Decimal("0")
    as_of_date = (
        parse_as_of_date(holding_rows[0].get("as_of_date"))
        if holding_rows
        else datetime.date.today()
    )

    warnings: list[str] = []
    if holdings and (coverage_pct < Decimal("99") or coverage_pct > Decimal("101")):
        warnings.append(f"Holdings coverage {coverage_pct:.2f}% outside 99-101% range")

    log.info(
        "mf_holdings_route_complete",
        mstar_id=mstar_id,
        holding_count=len(holdings),
        coverage_pct=str(coverage_pct),
    )

    return HoldingsResponse(
        holdings=holdings,
        as_of_date=as_of_date,
        coverage_pct=coverage_pct,
        warnings=warnings,
    )


@router.get("/{mstar_id}/sectors", response_model=FundSectorsResponse)
async def get_fund_sectors(
    mstar_id: str,
    db: AsyncSession = Depends(get_db),
) -> FundSectorsResponse:
    """Get sector exposure for a fund at latest as_of_date."""
    svc = JIPDataService(db)
    sector_rows = await svc.get_fund_sectors(mstar_id)

    sectors = []
    for row in sector_rows:
        weight_pct = safe_decimal(row.get("weight_pct"))
        if weight_pct is None:
            continue
        sectors.append(
            FundSector(
                sector=str(row.get("sector") or ""),
                weight_pct=weight_pct,
                stock_count=int(row.get("stock_count") or 0),
                sector_rs_composite=safe_decimal(row.get("sector_rs_composite")),
            )
        )

    as_of_date = (
        parse_as_of_date(sector_rows[0].get("as_of_date")) if sector_rows else datetime.date.today()
    )
    log.info(
        "mf_sectors_route_complete",
        mstar_id=mstar_id,
        sector_count=len(sectors),
    )

    return FundSectorsResponse(sectors=sectors, as_of_date=as_of_date)


@router.get("/{mstar_id}/rs-history", response_model=FundRSHistoryResponse)
async def get_fund_rs_history(
    mstar_id: str,
    months: Optional[int] = Query(12, ge=1, le=120),
) -> FundRSHistoryResponse:
    raise not_implemented()


@router.get("/{mstar_id}/weighted-technicals", response_model=WeightedTechnicalsResponse)
async def get_fund_weighted_technicals(
    mstar_id: str,
    include: Optional[str] = Query(
        None, description="Comma-separated includes e.g. conviction_series"
    ),
    db: AsyncSession = Depends(get_db),
) -> WeightedTechnicalsResponse:
    """Get latest weighted technicals for a fund.

    Optional include=conviction_series adds last 12 months of weekly
    conviction score as a time series (spec §18 include system).
    Returns [] for conviction_series if atlas_gold_rs_cache has no MF rows.
    """
    svc = JIPDataService(db)
    freshness = await svc.get_mf_data_freshness()
    data_as_of = data_as_of_from_freshness(freshness)
    staleness = compute_staleness(freshness)
    wt = await svc.get_fund_weighted_technicals(mstar_id)

    conviction_series: Optional[list[dict[str, Any]]] = None
    if include and "conviction_series" in [t.strip() for t in include.split(",")]:
        conviction_series = await fetch_mf_conviction_series(db, mstar_id)

    return build_weighted_technicals_response(
        mstar_id, wt, data_as_of, staleness, conviction_series
    )


@router.get("/{mstar_id}/nav-history", response_model=NAVHistoryResponse)
async def get_fund_nav_history(
    mstar_id: str,
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> NAVHistoryResponse:
    """Get NAV history for a fund with optional date range.

    coverage_gap_days = total calendar days between first and last point minus
    actual data point count. Surfaces missing days (including weekends/holidays).
    Zero when < 2 data points or no gaps.
    """
    svc = JIPDataService(db)
    nav_rows = await svc.get_fund_nav_history(mstar_id, date_from=date_from, date_to=date_to)
    freshness = await svc.get_mf_data_freshness()
    return build_nav_history(
        nav_rows, mstar_id, data_as_of_from_freshness(freshness), compute_staleness(freshness)
    )


@router.get("/{mstar_id}", response_model=FundDeepDiveResponse)
async def get_fund_deep_dive(mstar_id: str) -> FundDeepDiveResponse:
    """Full deep-dive for one MF.

    Runs the four independent queries in parallel on separate sessions —
    asyncpg can't multiplex one connection, so sequential awaits on a
    shared session produced ~5s cold; parallel cuts it to max(slowest).
    v2-09 budget: 500ms.
    """
    detail, lifecycle_events, freshness, rs_batch = await asyncio.gather(
        fetch_deep_dive_detail(mstar_id),
        fetch_deep_dive_lifecycle(mstar_id),
        fetch_deep_dive_freshness(),
        fetch_deep_dive_rs_batch(),
    )

    if detail is None:
        raise HTTPException(status_code=404, detail="Fund not found")

    momentum_data = rs_batch.get(mstar_id, {})
    rs_momentum_28d = safe_decimal(momentum_data.get("rs_momentum_28d")) if momentum_data else None
    derived_rs = safe_decimal(detail.get("derived_rs_composite"))
    nav_rs = safe_decimal(detail.get("nav_rs_composite"))

    # Verify manager_alpha == derived_rs_composite - nav_rs_composite
    if derived_rs is not None and nav_rs is not None:
        expected_alpha = derived_rs - nav_rs
        stored_alpha = safe_decimal(detail.get("manager_alpha"))
        if stored_alpha is not None and stored_alpha != expected_alpha:
            log.warning(
                "mf_deep_dive.manager_alpha_mismatch",
                mstar_id=mstar_id,
                stored=str(stored_alpha),
                expected=str(expected_alpha),
            )

    quadrant = classify_fund_quadrant(derived_rs, rs_momentum_28d)
    data_as_of = data_as_of_from_freshness(freshness)
    staleness = compute_staleness(freshness)
    is_active = detail.get("is_active")

    log.info(
        "mf_deep_dive_route_complete",
        mstar_id=mstar_id,
        quadrant=quadrant.value if quadrant else None,
        data_as_of=str(data_as_of),
    )

    return FundDeepDiveResponse(
        identity=build_deep_dive_identity(detail),
        daily=build_deep_dive_daily(detail),
        pillars=build_deep_dive_pillars(detail, derived_rs, rs_momentum_28d, quadrant),
        sector_exposure=SectorExposureSummary(
            sector_count=int(detail.get("sector_count") or 0),
        ),
        top_holdings=[],
        weighted_technicals=build_weighted_technicals(detail),
        data_as_of=data_as_of,
        staleness=staleness,
        inactive=True if is_active is False else None,
        mf_lifecycle_event=build_lifecycle_event(lifecycle_events),
    )
