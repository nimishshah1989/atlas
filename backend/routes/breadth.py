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
from backend.services.breadth_divergence_detector import detect_divergences
from backend.services.breadth_zone_detector import detect_zone_events
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
    symbol: Optional[str] = Query("NIFTY", description="Stock symbol"),
    lookback_days: Optional[int] = Query(365, description="Lookback in days"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Zone-crossing events for a symbol vs its moving averages (V2FE-1a).

    Returns events where the stock price crosses above or below its SMA-20
    and SMA-200. Fault-tolerant: returns data=[] with insufficient_data=True
    when JIP returns no data for the symbol.
    """
    import datetime as _dt

    svc = JIPDataService(db)
    resolved_symbol = (symbol or "NIFTY").upper()
    resolved_lookback = lookback_days if lookback_days and lookback_days > 0 else 365

    events: list[dict[str, Any]] = []
    try:
        events = await detect_zone_events(
            jip_svc=svc,
            symbol=resolved_symbol,
            lookback_days=resolved_lookback,
        )
    except Exception as exc:
        log.warning(
            "get_breadth_zone_events_error",
            symbol=resolved_symbol,
            error=str(exc)[:300],
        )

    today_str = _dt.date.today().isoformat()
    data_as_of = today_str

    # Compute staleness_seconds relative to data_as_of (IST midnight)
    try:
        as_of_dt = _dt.datetime.fromisoformat(data_as_of + "T00:00:00+05:30")
        staleness_seconds = int((_dt.datetime.now(tz=_dt.timezone.utc) - as_of_dt).total_seconds())
    except ValueError:
        staleness_seconds = 0

    insufficient = len(events) == 0
    meta: dict[str, Any] = {
        "data_as_of": data_as_of,
        "staleness_seconds": staleness_seconds,
        "source": "jip/bhavcopy_eq",
        "symbol": resolved_symbol,
        "lookback_days": resolved_lookback,
    }
    if insufficient:
        meta["insufficient_data"] = True

    return {"data": events, "_meta": meta}


# ---------------------------------------------------------------------------
# /breadth/divergences — MUST register before /breadth (more specific path)
# ---------------------------------------------------------------------------


@router.get("/breadth/divergences")
async def get_breadth_divergences(
    universe: Optional[str] = Query("nifty500", description="Universe"),
    lookback_days: Optional[int] = Query(180, description="Lookback in days"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Price vs breadth divergence events (V2FE-1a).

    Bullish divergence: index down, breadth (pct above 50-DMA) up.
    Bearish divergence: index up, breadth down.
    Returns insufficient_data=True when price data unavailable.
    """
    import datetime as _dt

    resolved_universe = universe or "nifty500"
    resolved_lookback = lookback_days if lookback_days and lookback_days > 0 else 180

    divergence_payload: dict[str, Any] = {}
    try:
        divergence_payload = await detect_divergences(
            session=db,
            universe=resolved_universe,
            lookback_days=resolved_lookback,
        )
    except Exception as exc:
        log.warning(
            "get_breadth_divergences_error",
            universe=resolved_universe,
            error=str(exc)[:300],
        )

    divergences = divergence_payload.get("divergences", [])
    inner_meta: dict[str, Any] = dict(divergence_payload.get("_meta") or {})

    today_str = _dt.date.today().isoformat()
    data_as_of = str(inner_meta.get("data_as_of") or today_str)

    # Compute staleness_seconds relative to data_as_of (IST midnight)
    try:
        as_of_dt = _dt.datetime.fromisoformat(data_as_of + "T00:00:00+05:30")
        staleness_seconds = int((_dt.datetime.now(tz=_dt.timezone.utc) - as_of_dt).total_seconds())
    except ValueError:
        staleness_seconds = 0

    meta: dict[str, Any] = {
        "data_as_of": data_as_of,
        "staleness_seconds": staleness_seconds,
        "source": "jip/bhavcopy_eq",
        "universe": resolved_universe,
        "lookback_days": resolved_lookback,
    }
    if inner_meta.get("insufficient_data"):
        meta["insufficient_data"] = True

    return {"data": divergences, "_meta": meta}


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
