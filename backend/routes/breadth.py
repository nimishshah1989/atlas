"""Breadth sub-routes — V2FE-1.

Routes:
    GET /api/v1/stocks/breadth             — breadth + regime + optional conviction_series
    GET /api/v1/stocks/breadth/zone-events — edge-triggered breadth zone crossings
    GET /api/v1/stocks/breadth/divergences — price vs breadth divergences

These routes MUST be registered before the ``/{symbol}`` path-param routes in
stocks.py (FastAPI static-before-param ordering rule).
"""

import time
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.db.session import async_session_factory, get_db
from backend.models.schemas import (
    BreadthSnapshot,
    MarketBreadthResponse,
    RegimeSnapshot,
    ResponseMeta,
)
from backend.services.breadth_divergence_detector import BreadthDivergenceDetector
from backend.services.breadth_zone_detector import BreadthZoneDetector
from backend.services.regime_service import compute_regime_enrichment

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


def _dec(val: Any) -> Any:
    from decimal import Decimal

    if val is None:
        return None
    return Decimal(str(val))


# ---------------------------------------------------------------------------
# /breadth/zone-events — MUST register before /breadth (more specific path)
# ---------------------------------------------------------------------------


@router.get("/breadth/zone-events")
async def get_breadth_zone_events(
    universe: Optional[str] = Query("nifty500", description="Universe: nifty500 or nifty50"),
    range: Optional[str] = Query("5y", description="Date range: 1y, 5y, all"),
    indicator: Optional[str] = Query("all", description="Indicator: ema21, dma50, dma200, or all"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return breadth zone-crossing events for the given universe and indicator.

    Reads de_breadth_daily time-series and emits edge-triggered events when
    the breadth count crosses OB/midline/OS thresholds.
    """
    detector = BreadthZoneDetector(session=db)
    return await detector.compute(
        universe=universe or "nifty500",
        range_=range or "5y",
        indicator=indicator or "all",
    )


# ---------------------------------------------------------------------------
# /breadth/divergences — MUST register before /breadth (more specific path)
# ---------------------------------------------------------------------------


@router.get("/breadth/divergences")
async def get_breadth_divergences(
    universe: Optional[str] = Query("nifty500", description="Universe: nifty500 or nifty50"),
    window: Optional[int] = Query(20, description="Rolling window in trading days"),
    lookback: Optional[int] = Query(3, description="Lookback period in months"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return price vs breadth divergences.

    Bullish divergence: index down, breadth (pct above 50-DMA) up.
    Bearish divergence: index up, breadth down.
    Returns insufficient_data=True when price data unavailable.
    """
    detector = BreadthDivergenceDetector(session=db)
    return await detector.compute(
        universe=universe or "nifty500",
        window=window or 20,
        lookback=lookback or 3,
    )


# ---------------------------------------------------------------------------
# /breadth — base breadth + regime with optional conviction_series include
# ---------------------------------------------------------------------------


@router.get("/breadth", response_model=MarketBreadthResponse)
async def get_breadth(
    include: Optional[str] = Query(
        None, description="Comma-separated includes e.g. conviction_series"
    ),
    db: AsyncSession = Depends(get_db),
) -> MarketBreadthResponse:
    """Get market breadth and regime data (with regime enrichment).

    Optional include=conviction_series adds per-date Gold RS conviction chip state.
    """
    t0 = time.monotonic()
    svc = JIPDataService(db)

    breadth_data = await svc.get_market_breadth()
    regime_data = await svc.get_market_regime()

    if not breadth_data or not regime_data:
        raise HTTPException(status_code=503, detail="Market data not available")

    # Regime enrichment via isolated sessions (asyncpg cannot multiplex).
    days_val, history_val = await compute_regime_enrichment(async_session_factory)
    breadth = BreadthSnapshot(
        date=breadth_data["date"],
        advance=breadth_data["advance"],
        decline=breadth_data["decline"],
        unchanged=breadth_data["unchanged"],
        total_stocks=breadth_data["total_stocks"],
        ad_ratio=_dec(breadth_data.get("ad_ratio")),
        pct_above_200dma=_dec(breadth_data.get("pct_above_200dma")),
        pct_above_50dma=_dec(breadth_data.get("pct_above_50dma")),
        new_52w_highs=breadth_data.get("new_52w_highs", 0),
        new_52w_lows=breadth_data.get("new_52w_lows", 0),
        mcclellan_oscillator=_dec(breadth_data.get("mcclellan_oscillator")),
        mcclellan_summation=_dec(breadth_data.get("mcclellan_summation")),
    )

    regime = RegimeSnapshot(
        date=regime_data["date"],
        regime=regime_data["regime"],
        confidence=_dec(regime_data.get("confidence")),
        breadth_score=_dec(regime_data.get("breadth_score")),
        momentum_score=_dec(regime_data.get("momentum_score")),
        volume_score=_dec(regime_data.get("volume_score")),
        global_score=_dec(regime_data.get("global_score")),
        fii_score=_dec(regime_data.get("fii_score")),
        days_in_regime=days_val,
        regime_history=history_val,
    )

    # Optional: conviction_series include
    conviction_series: Optional[list[dict[str, Any]]] = None
    if include and "conviction_series" in [t.strip() for t in include.split(",")]:
        try:
            from sqlalchemy import text as sa_text

            cs_result = await db.execute(
                sa_text(
                    """
                    SELECT date::text AS date,
                           gold_rs_signal AS signal,
                           entity_id
                    FROM atlas_gold_rs_cache
                    WHERE entity_type = 'equity'
                    ORDER BY date DESC
                    LIMIT 90
                    """
                )
            )
            cs_rows = cs_result.mappings().all()
            conviction_series = [dict(r) for r in cs_rows]
        except Exception as exc:
            log.warning("breadth_conviction_series_failed", error=str(exc)[:300])
            conviction_series = []

    elapsed = int((time.monotonic() - t0) * 1000)
    return MarketBreadthResponse(
        breadth=breadth,
        regime=regime,
        meta=ResponseMeta(
            data_as_of=breadth_data["date"],
            record_count=1,
            query_ms=elapsed,
        ),
        conviction_series=conviction_series,
    )
