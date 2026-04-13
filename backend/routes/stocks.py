"""Stock API routes — V1 endpoints."""

import time
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.jip_data_service import JIPDataService
from backend.core.computations import build_conviction_pillars, compute_quadrant
from backend.db.session import get_db
from backend.models.schemas import (
    BreadthSnapshot,
    MarketBreadthResponse,
    MoverEntry,
    MoversResponse,
    RSDataPoint,
    RSHistoryResponse,
    RegimeSnapshot,
    ResponseMeta,
    SectorGroup,
    SectorListResponse,
    SectorMetrics,
    StockDeepDive,
    StockDeepDiveResponse,
    StockSummary,
    StockUniverseResponse,
)

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


def _dec(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    return Decimal(str(val))


@router.get("/universe", response_model=StockUniverseResponse)
async def get_universe(
    benchmark: Optional[str] = Query("NIFTY 500", description="Benchmark filter"),
    sector: Optional[str] = Query(None, description="Sector filter"),
    db: AsyncSession = Depends(get_db),
) -> StockUniverseResponse:
    """Get all stocks grouped by sector with technicals and RS."""
    t0 = time.monotonic()
    svc = JIPDataService(db)
    rows = await svc.get_equity_universe(benchmark=benchmark, sector=sector)

    # Group by sector
    sector_map: dict[str, list[StockSummary]] = {}
    data_as_of = None

    for row in rows:
        rs_c = _dec(row.get("rs_composite"))
        rs_m = _dec(row.get("rs_momentum"))
        stock = StockSummary(
            id=row["id"],
            symbol=row["symbol"],
            company_name=row["company_name"],
            sector=row.get("sector"),
            nifty_50=row.get("nifty_50", False),
            nifty_200=row.get("nifty_200", False),
            nifty_500=row.get("nifty_500", False),
            close=_dec(row.get("close")),
            rs_composite=rs_c,
            rs_momentum=rs_m,
            quadrant=compute_quadrant(rs_c, rs_m),
            rsi_14=_dec(row.get("rsi_14")),
            adx_14=_dec(row.get("adx_14")),
            above_200dma=row.get("above_200dma"),
            above_50dma=row.get("above_50dma"),
            macd_histogram=_dec(row.get("macd_histogram")),
            beta_nifty=_dec(row.get("beta_nifty")),
            sharpe_1y=_dec(row.get("sharpe_1y")),
            mf_holder_count=row.get("mf_holder_count"),
            cap_category=row.get("cap_category"),
        )
        s = row.get("sector") or "Unknown"
        sector_map.setdefault(s, []).append(stock)

        if data_as_of is None and row.get("rs_date"):
            data_as_of = row["rs_date"]

    sectors = [
        SectorGroup(sector=s, stock_count=len(stocks), stocks=stocks)
        for s, stocks in sector_map.items()
    ]

    elapsed = int((time.monotonic() - t0) * 1000)
    total_stocks = sum(sg.stock_count for sg in sectors)

    return StockUniverseResponse(
        sectors=sectors,
        meta=ResponseMeta(
            data_as_of=data_as_of,
            record_count=total_stocks,
            query_ms=elapsed,
        ),
    )


@router.get("/sectors", response_model=SectorListResponse)
async def get_sectors(
    db: AsyncSession = Depends(get_db),
) -> SectorListResponse:
    """Get 31 sectors with 22 metrics each."""
    t0 = time.monotonic()
    svc = JIPDataService(db)
    rows = await svc.get_sector_rollups()

    sectors = []
    for row in rows:
        avg_rs = _dec(row.get("avg_rs_composite"))
        avg_mom = _dec(row.get("avg_rs_momentum"))

        sectors.append(
            SectorMetrics(
                sector=row["sector"],
                stock_count=row["stock_count"],
                avg_rs_composite=avg_rs,
                avg_rs_momentum=avg_mom,
                sector_quadrant=compute_quadrant(avg_rs, avg_mom),
                pct_above_200dma=_dec(row.get("pct_above_200dma")),
                pct_above_50dma=_dec(row.get("pct_above_50dma")),
                pct_above_ema21=_dec(row.get("pct_above_ema21")),
                avg_rsi_14=_dec(row.get("avg_rsi_14")),
                pct_rsi_overbought=_dec(row.get("pct_rsi_overbought")),
                pct_rsi_oversold=_dec(row.get("pct_rsi_oversold")),
                avg_adx=_dec(row.get("avg_adx")),
                pct_adx_trending=_dec(row.get("pct_adx_trending")),
                pct_macd_bullish=_dec(row.get("pct_macd_bullish")),
                pct_roc5_positive=_dec(row.get("pct_roc5_positive")),
                avg_beta=_dec(row.get("avg_beta")),
                avg_sharpe=_dec(row.get("avg_sharpe")),
                avg_sortino=_dec(row.get("avg_sortino")),
                avg_volatility_20d=_dec(row.get("avg_volatility_20d")),
                avg_max_dd=_dec(row.get("avg_max_dd")),
                avg_calmar=_dec(row.get("avg_calmar")),
                avg_mf_holders=_dec(row.get("avg_mf_holders")),
                avg_disparity_20=_dec(row.get("avg_disparity_20")),
            )
        )

    elapsed = int((time.monotonic() - t0) * 1000)
    return SectorListResponse(
        sectors=sectors,
        meta=ResponseMeta(record_count=len(sectors), query_ms=elapsed),
    )


@router.get("/breadth", response_model=MarketBreadthResponse)
async def get_breadth(
    db: AsyncSession = Depends(get_db),
) -> MarketBreadthResponse:
    """Get market breadth and regime data."""
    t0 = time.monotonic()
    svc = JIPDataService(db)

    breadth_data = await svc.get_market_breadth()
    regime_data = await svc.get_market_regime()

    if not breadth_data or not regime_data:
        raise HTTPException(status_code=503, detail="Market data not available")

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
    )

    elapsed = int((time.monotonic() - t0) * 1000)
    return MarketBreadthResponse(
        breadth=breadth,
        regime=regime,
        meta=ResponseMeta(
            data_as_of=breadth_data["date"],
            record_count=1,
            query_ms=elapsed,
        ),
    )


@router.get("/movers", response_model=MoversResponse)
async def get_movers(
    limit: int = Query(15, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> MoversResponse:
    """Get top RS momentum gainers and losers."""
    t0 = time.monotonic()
    svc = JIPDataService(db)
    movers = await svc.get_movers(limit=limit)

    def _to_mover(row: dict[str, Any]) -> MoverEntry:
        rs_c = _dec(row.get("rs_composite"))
        rs_m = _dec(row.get("rs_momentum"))
        return MoverEntry(
            symbol=row["symbol"],
            company_name=row["company_name"],
            sector=row.get("sector"),
            rs_composite=rs_c,
            rs_momentum=rs_m,
            quadrant=compute_quadrant(rs_c, rs_m),
        )

    elapsed = int((time.monotonic() - t0) * 1000)
    return MoversResponse(
        gainers=[_to_mover(row) for row in movers["gainers"]],
        losers=[_to_mover(row) for row in movers["losers"]],
        meta=ResponseMeta(
            record_count=len(movers["gainers"]) + len(movers["losers"]),
            query_ms=elapsed,
        ),
    )


@router.get("/{symbol}", response_model=StockDeepDiveResponse)
async def get_stock_deep_dive(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> StockDeepDiveResponse:
    """Get complete deep-dive for a stock with conviction pillars."""
    t0 = time.monotonic()
    svc = JIPDataService(db)
    stock_detail = await svc.get_stock_detail(symbol)

    if not stock_detail:
        raise HTTPException(status_code=404, detail=f"Stock {symbol.upper()} not found")

    conviction = build_conviction_pillars(stock_detail)

    stock = StockDeepDive(
        id=stock_detail["id"],
        symbol=stock_detail["symbol"],
        company_name=stock_detail["company_name"],
        sector=stock_detail.get("sector"),
        industry=stock_detail.get("industry"),
        nifty_50=stock_detail.get("nifty_50", False),
        nifty_200=stock_detail.get("nifty_200", False),
        nifty_500=stock_detail.get("nifty_500", False),
        isin=stock_detail.get("isin"),
        listing_date=stock_detail.get("listing_date"),
        cap_category=stock_detail.get("cap_category"),
        close=_dec(stock_detail.get("close")),
        sma_50=_dec(stock_detail.get("sma_50")),
        sma_200=_dec(stock_detail.get("sma_200")),
        ema_21=_dec(stock_detail.get("ema_21")),
        rsi_14=_dec(stock_detail.get("rsi_14")),
        adx_14=_dec(stock_detail.get("adx_14")),
        macd_line=_dec(stock_detail.get("macd_line")),
        macd_signal=_dec(stock_detail.get("macd_signal")),
        macd_histogram=_dec(stock_detail.get("macd_histogram")),
        above_200dma=stock_detail.get("above_200dma"),
        above_50dma=stock_detail.get("above_50dma"),
        beta_nifty=_dec(stock_detail.get("beta_nifty")),
        sharpe_1y=_dec(stock_detail.get("sharpe_1y")),
        sortino_1y=_dec(stock_detail.get("sortino_1y")),
        max_drawdown_1y=_dec(stock_detail.get("max_drawdown_1y")),
        calmar_ratio=_dec(stock_detail.get("calmar_ratio")),
        volatility_20d=_dec(stock_detail.get("volatility_20d")),
        relative_volume=_dec(stock_detail.get("relative_volume")),
        mfi_14=_dec(stock_detail.get("mfi_14")),
        obv=stock_detail.get("obv"),
        delivery_vs_avg=_dec(stock_detail.get("delivery_vs_avg")),
        bollinger_upper=_dec(stock_detail.get("bollinger_upper")),
        bollinger_lower=_dec(stock_detail.get("bollinger_lower")),
        disparity_20=_dec(stock_detail.get("disparity_20")),
        stochastic_k=_dec(stock_detail.get("stochastic_k")),
        stochastic_d=_dec(stock_detail.get("stochastic_d")),
        conviction=conviction,
        mf_holder_count=stock_detail.get("mf_holder_count"),
    )

    elapsed = int((time.monotonic() - t0) * 1000)
    return StockDeepDiveResponse(
        stock=stock,
        meta=ResponseMeta(
            data_as_of=stock_detail.get("rs_date"),
            record_count=1,
            query_ms=elapsed,
        ),
    )


@router.get("/{symbol}/rs-history", response_model=RSHistoryResponse)
async def get_rs_history(
    symbol: str,
    benchmark: str = Query("NIFTY 500"),
    months: int = Query(12, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
) -> RSHistoryResponse:
    """Get RS score history for a stock."""
    t0 = time.monotonic()
    svc = JIPDataService(db)
    rows = await svc.get_rs_history(symbol, benchmark=benchmark, months=months)

    history_points = [
        RSDataPoint(
            date=row["date"],
            rs_composite=_dec(row.get("rs_composite")),
            rs_1w=_dec(row.get("rs_1w")),
            rs_1m=_dec(row.get("rs_1m")),
            rs_3m=_dec(row.get("rs_3m")),
        )
        for row in rows
    ]

    elapsed = int((time.monotonic() - t0) * 1000)
    return RSHistoryResponse(
        symbol=symbol.upper(),
        benchmark=benchmark,
        points=history_points,
        meta=ResponseMeta(record_count=len(history_points), query_ms=elapsed),
    )
