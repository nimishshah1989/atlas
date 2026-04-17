"""TV routes — read-through cache endpoints for TradingView data.

GET /api/tv/ta/bulk                 Bulk cache-only TA lookup (registered BEFORE /{symbol})
GET /api/tv/ta/{symbol}             Technical analysis summary
GET /api/tv/screener/{symbol}       Screener data
GET /api/tv/fundamentals/{symbol}   Fundamentals data

All routes return a §20.4 envelope:
    {"data": {...}, "_meta": {"data_as_of": "...", "is_stale": bool, "data_layer": "near_realtime"}}

On bridge unavailability (sidecar down / timeout) a 503 is returned.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.services.tv.bridge import TVBridgeClient, TVBridgeUnavailableError
from backend.services.tv.cache_service import TVCacheService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/tv", tags=["tv"])


@router.get("/ta/bulk")
async def get_ta_bulk_cache(
    symbols: str,
    exchange: Optional[str] = "NSE",
    interval: Optional[str] = "1D",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Pure-cache lookup for 1D TA across many symbols. No bridge calls, no background refresh.

    Returns a §20.4 envelope with an `items` array — one entry per requested symbol.
    Uncached symbols yield {symbol, tv_ta: null, fetched_at: null}.

    Query params:
        symbols  : comma-separated, case-insensitive, upper-cased. Hard cap 500; 400 otherwise.
        exchange : informational (cache PK is (symbol, data_type, interval)).
        interval : '1D' by default.
    """
    from backend.db.tv_models import AtlasTvCache
    from sqlalchemy import select

    resolved_interval = interval or "1D"

    raw = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not raw:
        raise HTTPException(status_code=400, detail="symbols required")
    if len(raw) > 500:
        raise HTTPException(status_code=400, detail="max 500 symbols per call")
    # Dedupe while preserving order so response array mirrors request
    seen: set[str] = set()
    requested: list[str] = []
    for s in raw:
        if s not in seen:
            seen.add(s)
            requested.append(s)

    stmt = select(AtlasTvCache).where(
        AtlasTvCache.symbol.in_(requested),
        AtlasTvCache.data_type == "ta_summary",
        AtlasTvCache.interval == resolved_interval,
    )
    rows = (await db.execute(stmt)).scalars().all()
    by_symbol = {r.symbol: r for r in rows}

    items: list[dict[str, Any]] = []
    latest: Optional[datetime] = None
    for sym in requested:
        row = by_symbol.get(sym)
        if row is None:
            items.append({"symbol": sym, "tv_ta": None, "fetched_at": None})
            continue
        if latest is None or row.fetched_at > latest:
            latest = row.fetched_at
        items.append(
            {
                "symbol": sym,
                "tv_ta": row.tv_data,
                "fetched_at": row.fetched_at.isoformat(),
            }
        )

    log.info(
        "tv_ta_bulk_cache",
        requested=len(requested),
        cached=sum(1 for it in items if it["tv_ta"] is not None),
    )

    return {
        "data": {"items": items},
        "_meta": {
            "data_as_of": latest.isoformat() if latest else None,
            "data_layer": "near_realtime",
            "cached_count": sum(1 for it in items if it["tv_ta"] is not None),
            "requested_count": len(requested),
        },
    }


def _build_meta(fetched_at: datetime, is_stale: bool) -> dict[str, Any]:
    """Build the standard _meta block for TV responses."""
    return {
        "data_as_of": fetched_at.isoformat(),
        "is_stale": is_stale,
        "data_layer": "near_realtime",
    }


def _extract_ta_fields(
    tv_data: dict[str, Any],
    symbol: str,
    exchange: str,
    interval: str,
) -> dict[str, Any]:
    """Extract TA summary fields from the raw tv_data blob.

    Defensive: external bridge can return any structure; all keys are
    optional with None as the default.
    """
    compute = tv_data.get("COMPUTE") or {}
    oscillators = compute.get("OSCILLATORS") or {}
    ma = compute.get("MA") or {}

    recommendation_1d = tv_data.get("RECOMMENDATION") or tv_data.get("recommendation")
    oscillator_score = oscillators.get("RECOMMENDATION") or tv_data.get("oscillator_score")
    ma_score = ma.get("RECOMMENDATION") or tv_data.get("ma_score")
    buy = tv_data.get("BUY") or tv_data.get("buy")
    sell = tv_data.get("SELL") or tv_data.get("sell")
    neutral = tv_data.get("NEUTRAL") or tv_data.get("neutral")

    return {
        "symbol": symbol,
        "exchange": exchange,
        "interval": interval,
        "recommendation_1d": recommendation_1d,
        "oscillator_score": oscillator_score,
        "ma_score": ma_score,
        "buy": buy,
        "sell": sell,
        "neutral": neutral,
    }


@router.get("/ta/{symbol}")
async def get_ta_summary(
    symbol: str,
    exchange: Optional[str] = "NSE",
    interval: Optional[str] = "1D",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return cached TradingView technical analysis summary for a symbol.

    Delegates to TVCacheService which applies a read-through cache with
    stale-while-revalidate semantics.

    Returns:
        §20.4 envelope with `data` containing TA fields and `_meta` with
        staleness information.

    Raises:
        HTTPException 503: If the TV bridge sidecar is unreachable.
    """
    bridge = TVBridgeClient()
    cache_svc = TVCacheService()

    resolved_exchange = exchange or "NSE"
    resolved_interval = interval or "1D"

    log.info(
        "tv_ta_request",
        symbol=symbol,
        exchange=resolved_exchange,
        interval=resolved_interval,
    )

    try:
        entry = await cache_svc.get_or_fetch(
            session=db,
            symbol=symbol,
            exchange=resolved_exchange,
            data_type="ta_summary",
            interval=resolved_interval,
            bridge=bridge,
        )
    except TVBridgeUnavailableError as exc:
        log.warning(
            "tv_ta_bridge_unavailable",
            symbol=symbol,
            exchange=resolved_exchange,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="TV bridge unavailable") from exc

    tv_data = entry.tv_data or {}
    ta_fields = _extract_ta_fields(tv_data, symbol, resolved_exchange, resolved_interval)
    ta_fields["tv_ta"] = tv_data if tv_data else None  # additive raw field

    return {
        "data": ta_fields,
        "_meta": _build_meta(entry.fetched_at, entry.is_stale),
    }


@router.get("/screener/{symbol}")
async def get_screener(
    symbol: str,
    exchange: Optional[str] = "NSE",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return cached TradingView screener data for a symbol.

    Returns:
        §20.4 envelope with `data.raw` containing the full screener blob.

    Raises:
        HTTPException 503: If the TV bridge sidecar is unreachable.
    """
    bridge = TVBridgeClient()
    cache_svc = TVCacheService()

    resolved_exchange = exchange or "NSE"

    log.info("tv_screener_request", symbol=symbol, exchange=resolved_exchange)

    try:
        entry = await cache_svc.get_or_fetch(
            session=db,
            symbol=symbol,
            exchange=resolved_exchange,
            data_type="screener",
            interval="none",
            bridge=bridge,
        )
    except TVBridgeUnavailableError as exc:
        log.warning(
            "tv_screener_bridge_unavailable",
            symbol=symbol,
            exchange=resolved_exchange,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="TV bridge unavailable") from exc

    return {
        "data": {
            "symbol": symbol,
            "exchange": resolved_exchange,
            "raw": entry.tv_data or {},
        },
        "_meta": _build_meta(entry.fetched_at, entry.is_stale),
    }


@router.get("/fundamentals/{symbol}")
async def get_fundamentals(
    symbol: str,
    exchange: Optional[str] = "NSE",
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return cached TradingView fundamentals data for a symbol.

    Returns:
        §20.4 envelope with `data.raw` containing the full fundamentals blob.

    Raises:
        HTTPException 503: If the TV bridge sidecar is unreachable.
    """
    bridge = TVBridgeClient()
    cache_svc = TVCacheService()

    resolved_exchange = exchange or "NSE"

    log.info("tv_fundamentals_request", symbol=symbol, exchange=resolved_exchange)

    try:
        entry = await cache_svc.get_or_fetch(
            session=db,
            symbol=symbol,
            exchange=resolved_exchange,
            data_type="fundamentals",
            interval="none",
            bridge=bridge,
        )
    except TVBridgeUnavailableError as exc:
        log.warning(
            "tv_fundamentals_bridge_unavailable",
            symbol=symbol,
            exchange=resolved_exchange,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="TV bridge unavailable") from exc

    return {
        "data": {
            "symbol": symbol,
            "exchange": resolved_exchange,
            "raw": entry.tv_data or {},
        },
        "_meta": _build_meta(entry.fetched_at, entry.is_stale),
    }
