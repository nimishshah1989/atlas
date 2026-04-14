"""ATLAS V2 MF (mutual fund) API — router with wired universe/categories/flows.

Chunk V2-4 wires /universe, /categories, /flows with real JIP data.
Remaining endpoints (/overlap, deep dive, holdings, sectors, rs-history,
weighted-technicals, nav-history) stay as 501 stubs until later V2 chunks.
"""

import datetime
from collections import defaultdict
from decimal import Decimal
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
    ConvictionPillarsMF,
    FlowRow,
    FlowsResponse,
    Fund,
    FundDailyMetrics,
    FundDeepDiveResponse,
    FundIdentity,
    FundRSHistoryResponse,
    FundSector,
    FundSectorsResponse,
    Holding,
    HoldingsResponse,
    HoldingStockResponse,
    MFLifecycleEvent,
    NAVHistoryResponse,
    OverlapResponse,
    PillarFlows,
    PillarHoldingsQuality,
    PillarPerformance,
    PillarRSStrength,
    SectorExposureSummary,
    Staleness,
    StalenessFlag,
    UniverseResponse,
    WeightedTechnicalsResponse,
    WeightedTechnicalsSummary,
)
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


def _parse_as_of_date(raw: Any) -> datetime.date:
    """Coerce an as_of_date from a DB row to datetime.date, defaulting to today."""
    if isinstance(raw, datetime.datetime):
        return raw.date()
    if isinstance(raw, datetime.date):
        return raw
    return datetime.date.today()


def _map_holding_row(row: dict[str, Any]) -> Optional[Holding]:
    """Convert a JIP holding row to a Holding model. Returns None if weight_pct is missing."""
    weight_pct = safe_decimal(row.get("weight_pct"))
    if weight_pct is None:
        return None
    return Holding(
        instrument_id=str(row.get("instrument_id") or ""),
        symbol=str(row.get("current_symbol") or row.get("symbol") or ""),
        holding_name=str(row.get("holding_name") or ""),
        weight_pct=weight_pct,
        shares_held=safe_decimal(row.get("shares_held")),
        market_value=safe_decimal(row.get("market_value")),
        sector=row.get("sector") or row.get("sector_code"),
        rs_composite=safe_decimal(row.get("rs_composite")),
        above_200dma=row.get("above_200dma"),
    )


@router.get("/{mstar_id}/holdings", response_model=HoldingsResponse)
async def get_fund_holdings(
    mstar_id: str,
    db: AsyncSession = Depends(get_db),
) -> HoldingsResponse:
    """Get latest holdings for a fund with stock RS and technicals."""
    svc = JIPDataService(db)
    holding_rows = await svc.get_fund_holdings(mstar_id)

    holdings = [h for row in holding_rows if (h := _map_holding_row(row)) is not None]
    coverage_pct = sum((h.weight_pct for h in holdings), Decimal("0")) if holdings else Decimal("0")
    as_of_date = (
        _parse_as_of_date(holding_rows[0].get("as_of_date"))
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
        _parse_as_of_date(sector_rows[0].get("as_of_date"))
        if sector_rows
        else datetime.date.today()
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


def _build_deep_dive_identity(detail: dict[str, Any]) -> FundIdentity:
    """Extract FundIdentity from JIP fund detail row."""
    return FundIdentity(
        mstar_id=detail["mstar_id"],
        fund_name=detail.get("fund_name", ""),
        amc_name=detail.get("amc_name", ""),
        category_name=detail.get("category_name", ""),
        broad_category=detail.get("broad_category", ""),
        primary_benchmark=detail.get("primary_benchmark"),
        inception_date=detail.get("inception_date"),
        is_index_fund=bool(detail.get("is_index_fund", False)),
    )


def _build_deep_dive_daily(detail: dict[str, Any]) -> FundDailyMetrics:
    """Extract FundDailyMetrics from JIP fund detail row."""
    return FundDailyMetrics(
        nav=safe_decimal(detail.get("nav")),
        nav_date=detail.get("nav_date"),
        expense_ratio=safe_decimal(detail.get("expense_ratio")),
    )


def _build_deep_dive_pillars(
    detail: dict[str, Any],
    derived_rs: Optional[Decimal],
    rs_momentum_28d: Optional[Decimal],
    quadrant: Optional[Any],
) -> ConvictionPillarsMF:
    """Build conviction pillars from detail + computed RS values."""
    return ConvictionPillarsMF(
        performance=PillarPerformance(
            manager_alpha=safe_decimal(detail.get("manager_alpha")),
            information_ratio=safe_decimal(detail.get("information_ratio")),
        ),
        rs_strength=PillarRSStrength(
            rs_composite=derived_rs,
            rs_momentum_28d=rs_momentum_28d,
            quadrant=quadrant,
        ),
        flows=PillarFlows(),
        holdings_quality=PillarHoldingsQuality(),
    )


def _build_weighted_technicals(detail: dict[str, Any]) -> WeightedTechnicalsSummary:
    """Extract weighted technicals summary from JIP fund detail row."""
    weighted_as_of = detail.get("weighted_as_of")
    if isinstance(weighted_as_of, datetime.datetime):
        as_of_date: Optional[datetime.date] = weighted_as_of.date()
    elif isinstance(weighted_as_of, datetime.date):
        as_of_date = weighted_as_of
    else:
        as_of_date = None
    return WeightedTechnicalsSummary(
        weighted_rsi=safe_decimal(detail.get("weighted_rsi")),
        weighted_breadth_pct_above_200dma=safe_decimal(
            detail.get("weighted_breadth_pct_above_200dma")
        ),
        weighted_macd_bullish_pct=safe_decimal(detail.get("weighted_macd_bullish_pct")),
        as_of_date=as_of_date,
    )


def _build_lifecycle_event(
    lifecycle_events: list[dict[str, Any]],
) -> Optional[MFLifecycleEvent]:
    """Build MFLifecycleEvent from first lifecycle row, if any."""
    if not lifecycle_events:
        return None
    first = lifecycle_events[0]
    effective_date = first.get("effective_date")
    if isinstance(effective_date, datetime.datetime):
        effective_date = effective_date.date()
    if effective_date is None:
        return None
    return MFLifecycleEvent(
        event_type=str(first.get("event_type", "")),
        effective_date=effective_date,
        detail=first.get("detail"),
    )


@router.get("/{mstar_id}", response_model=FundDeepDiveResponse)
async def get_fund_deep_dive(
    mstar_id: str,
    db: AsyncSession = Depends(get_db),
) -> FundDeepDiveResponse:
    """Full deep-dive for a single mutual fund.

    Wires JIP fund_detail, lifecycle events, freshness, and RS momentum batch
    into a FundDeepDiveResponse. manager_alpha is passed through from JIP's
    MF derived daily table (derived_rs_composite - nav_rs_composite).
    """
    svc = JIPDataService(db)
    detail = await svc.get_fund_detail(mstar_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Fund not found")

    lifecycle_events = await svc.get_fund_lifecycle(mstar_id)
    freshness = await svc.get_mf_data_freshness()
    rs_batch = await svc.get_mf_rs_momentum_batch()

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
    data_as_of = _data_as_of_from_freshness(freshness)
    staleness = _compute_staleness(freshness)
    is_active = detail.get("is_active")

    log.info(
        "mf_deep_dive_route_complete",
        mstar_id=mstar_id,
        quadrant=quadrant.value if quadrant else None,
        data_as_of=str(data_as_of),
    )

    return FundDeepDiveResponse(
        identity=_build_deep_dive_identity(detail),
        daily=_build_deep_dive_daily(detail),
        pillars=_build_deep_dive_pillars(detail, derived_rs, rs_momentum_28d, quadrant),
        sector_exposure=SectorExposureSummary(
            sector_count=int(detail.get("sector_count") or 0),
        ),
        top_holdings=[],
        weighted_technicals=_build_weighted_technicals(detail),
        data_as_of=data_as_of,
        staleness=staleness,
        inactive=True if is_active is False else None,
        mf_lifecycle_event=_build_lifecycle_event(lifecycle_events),
    )
