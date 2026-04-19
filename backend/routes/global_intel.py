"""Global Intelligence API routes — 7 read-only routes (V5-9 + V2FE-1).

Routes:
    GET /api/v1/global/briefing   — latest LLM briefing from atlas_briefings
    GET /api/v1/global/ratios     — key macro ratios with sparklines
    GET /api/v1/global/rs-heatmap — global instruments RS + price
    GET /api/v1/global/regime     — current regime + breadth summary
    GET /api/v1/global/patterns   — inter-market patterns from atlas_intelligence
    GET /api/v1/global/events     — key market events (V2FE-1)
    GET /api/v1/global/flows      — FII/DII flow data (V2FE-1)
"""

import time
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.db.session import get_db
from backend.services.event_marker_service import EventMarkerService
from backend.services.flows_service import FlowsService
from backend.models.global_intel import (
    BreadthSummary,
    BriefingDetail,
    BriefingResponse,
    GlobalPatternsResponse,
    GlobalRSEntry,
    GlobalRegimeResponse,
    MacroRatioItem,
    MacroRatiosResponse,
    MacroSparkItem,
    PatternFinding,
    RSHeatmapResponse,
    RegimeSummary,
)
from backend.models.schemas import ResponseMeta

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/global", tags=["global"])

# Finding types considered "inter-market patterns" for the /patterns route
_PATTERN_FINDING_TYPES = [
    "inter_market",
    "cross_market",
    "correlation",
    "regime",
    "macro_signal",
    "global_pattern",
    "market_pattern",
]


@router.get("/briefing", response_model=BriefingResponse)
async def get_global_briefing(
    db: AsyncSession = Depends(get_db),
) -> BriefingResponse:
    """Return the latest market briefing from atlas_briefings.

    If no briefing exists, returns data=null with stale=True in _meta.
    """
    from backend.db.models import AtlasBriefing

    t0 = time.monotonic()
    briefing_detail: Optional[BriefingDetail] = None

    try:
        stmt = (
            select(AtlasBriefing)
            .where(AtlasBriefing.scope == "market")
            .where(AtlasBriefing.is_deleted.is_(False))
            .order_by(AtlasBriefing.date.desc())
            .limit(1)
        )
        query_result = await db.execute(stmt)
        row = query_result.scalar_one_or_none()

        if row is not None:
            briefing_detail = BriefingDetail(
                id=row.id,
                date=row.date,
                scope=row.scope,
                scope_key=row.scope_key,
                headline=row.headline,
                narrative=row.narrative,
                key_signals=row.key_signals,
                theses=row.theses,
                patterns=row.patterns,
                india_implication=row.india_implication,
                risk_scenario=row.risk_scenario,
                conviction=row.conviction,
                model_used=row.model_used,
                staleness_flags=row.staleness_flags,
                generated_at=row.generated_at,
            )
    except Exception as exc:
        log.warning("get_global_briefing_failed", error=str(exc)[:300])

    elapsed = int((time.monotonic() - t0) * 1000)
    stale = briefing_detail is None
    log.info(
        "get_global_briefing",
        found=briefing_detail is not None,
        stale=stale,
        query_ms=elapsed,
    )
    return BriefingResponse(
        briefing=briefing_detail,
        meta=ResponseMeta(
            record_count=1 if briefing_detail else 0,
            query_ms=elapsed,
            stale=stale,
        ),
    )


@router.get("/ratios", response_model=MacroRatiosResponse)
async def get_macro_ratios(
    tickers: Optional[str] = Query(None, description="Comma-separated ticker list"),
    sparkline_n: Optional[int] = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> MacroRatiosResponse:
    """Return key macro ratios with sparklines from JIP macro tables."""
    t0 = time.monotonic()

    ticker_list: Optional[list[str]] = None
    if tickers:
        ticker_list = [t.strip() for t in tickers.split(",") if t.strip()]

    svc = JIPDataService(db)
    raw_rows = await svc.get_macro_ratios(tickers=ticker_list, sparkline_n=sparkline_n or 10)

    items: list[MacroRatioItem] = []
    for row in raw_rows:
        sparkline_raw = row.get("sparkline") or []
        spark_items = []
        for sp in sparkline_raw:
            if isinstance(sp, dict) and sp.get("date") is not None:
                spark_items.append(
                    MacroSparkItem(
                        date=sp["date"],
                        value=Decimal(str(sp["value"])) if sp.get("value") is not None else None,
                    )
                )
        latest_value = row.get("latest_value")
        items.append(
            MacroRatioItem(
                ticker=row["ticker"],
                name=row.get("name"),
                unit=row.get("unit"),
                latest_value=Decimal(str(latest_value)) if latest_value is not None else None,
                latest_date=row.get("latest_date"),
                sparkline=spark_items,
            )
        )

    elapsed = int((time.monotonic() - t0) * 1000)
    log.info("get_macro_ratios", count=len(items), query_ms=elapsed)
    return MacroRatiosResponse(
        ratios=items,
        meta=ResponseMeta(record_count=len(items), query_ms=elapsed),
    )


@router.get("/rs-heatmap", response_model=RSHeatmapResponse)
async def get_global_rs_heatmap(
    db: AsyncSession = Depends(get_db),
) -> RSHeatmapResponse:
    """Return all global instruments with RS, momentum, and latest price."""
    t0 = time.monotonic()

    svc = JIPDataService(db)
    raw_rows = await svc.get_global_rs_heatmap()

    entries: list[GlobalRSEntry] = []
    for row in raw_rows:
        close_val = row.get("close")
        rs_comp = row.get("rs_composite")
        rs_1m = row.get("rs_1m")
        rs_3m = row.get("rs_3m")
        entries.append(
            GlobalRSEntry(
                entity_id=row["entity_id"],
                name=row.get("name"),
                instrument_type=row.get("instrument_type"),
                country=row.get("country"),
                rs_composite=Decimal(str(rs_comp)) if rs_comp is not None else None,
                rs_1m=Decimal(str(rs_1m)) if rs_1m is not None else None,
                rs_3m=Decimal(str(rs_3m)) if rs_3m is not None else None,
                rs_date=row.get("rs_date"),
                close=Decimal(str(close_val)) if close_val is not None else None,
                price_date=row.get("price_date"),
            )
        )

    elapsed = int((time.monotonic() - t0) * 1000)
    log.info("get_global_rs_heatmap", count=len(entries), query_ms=elapsed)
    return RSHeatmapResponse(
        heatmap=entries,
        meta=ResponseMeta(record_count=len(entries), query_ms=elapsed),
    )


@router.get("/regime", response_model=GlobalRegimeResponse)
async def get_global_regime(
    db: AsyncSession = Depends(get_db),
) -> GlobalRegimeResponse:
    """Return current market regime + breadth summary."""
    t0 = time.monotonic()

    svc = JIPDataService(db)
    regime_raw = await svc.get_market_regime()
    breadth_raw = await svc.get_market_breadth()

    regime: Optional[RegimeSummary] = None
    if regime_raw:
        conf = regime_raw.get("confidence")
        breadth_score = regime_raw.get("breadth_score")
        momentum_score = regime_raw.get("momentum_score")
        volume_score = regime_raw.get("volume_score")
        global_score = regime_raw.get("global_score")
        fii_score = regime_raw.get("fii_score")
        regime = RegimeSummary(
            date=regime_raw.get("date"),
            regime=regime_raw.get("regime"),
            confidence=Decimal(str(conf)) if conf is not None else None,
            breadth_score=Decimal(str(breadth_score)) if breadth_score is not None else None,
            momentum_score=Decimal(str(momentum_score)) if momentum_score is not None else None,
            volume_score=Decimal(str(volume_score)) if volume_score is not None else None,
            global_score=Decimal(str(global_score)) if global_score is not None else None,
            fii_score=Decimal(str(fii_score)) if fii_score is not None else None,
        )

    breadth: Optional[BreadthSummary] = None
    if breadth_raw:
        ad_ratio = breadth_raw.get("ad_ratio")
        pct_200 = breadth_raw.get("pct_above_200dma")
        pct_50 = breadth_raw.get("pct_above_50dma")
        breadth = BreadthSummary(
            date=breadth_raw.get("date"),
            advance=breadth_raw.get("advance"),
            decline=breadth_raw.get("decline"),
            unchanged=breadth_raw.get("unchanged"),
            total_stocks=breadth_raw.get("total_stocks"),
            ad_ratio=Decimal(str(ad_ratio)) if ad_ratio is not None else None,
            pct_above_200dma=Decimal(str(pct_200)) if pct_200 is not None else None,
            pct_above_50dma=Decimal(str(pct_50)) if pct_50 is not None else None,
            new_52w_highs=breadth_raw.get("new_52w_highs"),
            new_52w_lows=breadth_raw.get("new_52w_lows"),
        )

    elapsed = int((time.monotonic() - t0) * 1000)
    has_data = regime is not None or breadth is not None
    log.info(
        "get_global_regime",
        has_regime=regime is not None,
        has_breadth=breadth is not None,
        query_ms=elapsed,
    )
    return GlobalRegimeResponse(
        regime=regime,
        breadth=breadth,
        meta=ResponseMeta(
            record_count=1 if has_data else 0,
            query_ms=elapsed,
            stale=not has_data,
        ),
    )


@router.get("/patterns", response_model=GlobalPatternsResponse)
async def get_global_patterns(
    finding_type: Optional[str] = Query(None, description="Filter by finding type"),
    limit: Optional[int] = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> GlobalPatternsResponse:
    """Return recent inter-market patterns from atlas_intelligence."""
    from backend.db.models import AtlasIntelligence

    t0 = time.monotonic()
    patterns: list[PatternFinding] = []

    try:
        # Build type filter: use provided type or default to known pattern types
        if finding_type:
            type_filter = [finding_type]
        else:
            type_filter = _PATTERN_FINDING_TYPES

        stmt = (
            select(AtlasIntelligence)
            .where(AtlasIntelligence.finding_type.in_(type_filter))
            .where(AtlasIntelligence.is_deleted.is_(False))
            .order_by(AtlasIntelligence.created_at.desc())
            .limit(limit or 50)
        )
        query_result = await db.execute(stmt)
        rows = query_result.scalars().all()

        for row in rows:
            patterns.append(
                PatternFinding(
                    id=row.id,
                    finding_type=row.finding_type,
                    title=row.title,
                    content=row.content,
                    entity=row.entity,
                    entity_type=row.entity_type,
                    confidence=row.confidence,
                    tags=row.tags,
                    data_as_of=row.data_as_of,
                    created_at=row.created_at,
                )
            )
    except Exception as exc:
        log.warning("get_global_patterns_failed", error=str(exc)[:300])

    elapsed = int((time.monotonic() - t0) * 1000)
    log.info("get_global_patterns", count=len(patterns), query_ms=elapsed)
    return GlobalPatternsResponse(
        patterns=patterns,
        meta=ResponseMeta(record_count=len(patterns), query_ms=elapsed),
    )


@router.get("/events")
async def get_global_events(
    scope: Optional[str] = Query(None, description="Comma-separated scopes e.g. india,global"),
    range: Optional[str] = Query("5y", description="Date range: 1y, 5y, all"),
    categories: Optional[str] = Query(None, description="Comma-separated category filter"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return key market events filtered by scope, date range, and category.

    Reads from atlas_key_events. Supports scope filter (india, global, etc),
    date range, and category filter.
    """
    svc = EventMarkerService(session=db)
    resolved_scope = scope or "india,global"
    resolved_range = range or "5y"
    return await svc.get_events(
        scope=resolved_scope,
        range_=resolved_range,
        categories=categories,
    )


@router.get("/flows")
async def get_global_flows(
    scope: Optional[str] = Query(
        None,
        description="Comma-separated scopes: fii_equity,dii_equity,fii_debt,dii_debt",
    ),
    range: Optional[str] = Query("1y", description="Date range: 1m, 3m, 6m, 1y, 2y, 5y"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return FII/DII flow series from de_fii_dii_daily.

    Returns insufficient_data=True in _meta if de_fii_dii_daily has 0 rows.
    Financial values in INR crore as Decimal.
    """
    svc = FlowsService(session=db)
    resolved_range = range or "1y"
    return await svc.get_flows(scope=scope, range_=resolved_range)
