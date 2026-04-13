"""JIP Equity Service — stock universe, detail, RS history, movers."""

import time
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.clients.sql_fragments import (
    CAP_CTE,
    LATEST_DATES_CTE,
    MF_COUNTS_CTE,
    RS_28D_CTE,
    RS_CTE,
    TECH_CTE_FULL,
    TECH_CTE_SLIM,
)

log = structlog.get_logger()


class JIPEquityService:
    """Read-only access to JIP equity data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_equity_universe(
        self,
        benchmark: Optional[str] = "NIFTY 500",
        sector: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get all active instruments with latest technicals and RS."""
        start_time = time.monotonic()

        conditions = ["i.is_active = true"]
        params: dict[str, Any] = {}

        if benchmark == "NIFTY 50":
            conditions.append("i.nifty_50 = true")
        elif benchmark == "NIFTY 200":
            conditions.append("i.nifty_200 = true")
        elif benchmark == "NIFTY 500":
            conditions.append("i.nifty_500 = true")

        if sector:
            conditions.append("i.sector = :sector")
            params["sector"] = sector

        where_clause = " AND ".join(conditions)

        query = text(f"""
            WITH {LATEST_DATES_CTE},
            {RS_CTE},
            {RS_28D_CTE},
            {TECH_CTE_SLIM},
            {MF_COUNTS_CTE},
            {CAP_CTE}
            SELECT
                i.id, i.current_symbol AS symbol, i.company_name, i.sector,
                i.nifty_50, i.nifty_200, i.nifty_500,
                t.close_adj AS close, t.rsi_14, t.adx_14, t.above_200dma, t.above_50dma,
                t.macd_histogram, t.beta_nifty, t.sharpe_1y,
                r.rs_composite, r.rs_1w, r.rs_1m, r.rs_3m, r.rs_6m, r.rs_12m,
                r.rs_composite - COALESCE(r28.rs_composite_28d, r.rs_composite) AS rs_momentum,
                mc.mf_holder_count,
                cap.cap_category,
                (SELECT rs_date FROM latest_dates) AS rs_date,
                (SELECT tech_date FROM latest_dates) AS tech_date
            FROM de_instrument i
            LEFT JOIN latest_rs r ON r.entity_id = i.id::text
            LEFT JOIN rs_28d r28 ON r28.entity_id = i.id::text
            LEFT JOIN latest_tech t ON t.instrument_id = i.id
            LEFT JOIN mf_counts mc ON mc.instrument_id = i.id
            LEFT JOIN latest_cap cap ON cap.instrument_id = i.id
            WHERE {where_clause}
            ORDER BY i.sector, r.rs_composite DESC NULLS LAST
        """)

        query_result = await self.session.execute(query, params)
        rows = query_result.mappings().all()

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        log.info("equity_universe_fetched", count=len(rows), ms=elapsed_ms)
        return [dict(row) for row in rows]

    async def get_stock_detail(self, symbol: str) -> Optional[dict[str, Any]]:
        """Get full stock data for deep-dive."""
        query = text(f"""
            WITH {LATEST_DATES_CTE},
            {RS_CTE},
            {RS_28D_CTE},
            {TECH_CTE_FULL},
            {MF_COUNTS_CTE},
            {CAP_CTE}
            SELECT
                i.id, i.current_symbol AS symbol, i.company_name, i.sector, i.industry,
                i.nifty_50, i.nifty_200, i.nifty_500, i.isin, i.listing_date,
                t.close_adj AS close, t.sma_50, t.sma_200, t.ema_21,
                t.rsi_14, t.adx_14, t.macd_line, t.macd_signal, t.macd_histogram,
                t.above_200dma, t.above_50dma,
                t.beta_nifty, t.sharpe_1y, t.sortino_1y, t.max_drawdown_1y, t.calmar_ratio,
                t.volatility_20d, t.relative_volume, t.mfi_14, t.obv,
                t.delivery_vs_avg, t.bollinger_upper, t.bollinger_lower,
                t.disparity_20, t.stochastic_k, t.stochastic_d,
                r.rs_composite, r.rs_1w, r.rs_1m, r.rs_3m, r.rs_6m, r.rs_12m,
                r.rs_composite - COALESCE(r28.rs_composite_28d, r.rs_composite) AS rs_momentum,
                mc.mf_holder_count,
                cap.cap_category,
                (SELECT rs_date FROM latest_dates) AS rs_date,
                (SELECT tech_date FROM latest_dates) AS tech_date
            FROM de_instrument i
            LEFT JOIN latest_rs r ON r.entity_id = i.id::text
            LEFT JOIN rs_28d r28 ON r28.entity_id = i.id::text
            LEFT JOIN latest_tech t ON t.instrument_id = i.id
            LEFT JOIN mf_counts mc ON mc.instrument_id = i.id
            LEFT JOIN latest_cap cap ON cap.instrument_id = i.id
            WHERE i.current_symbol = :symbol AND i.is_active = true
            LIMIT 1
        """)

        query_result = await self.session.execute(query, {"symbol": symbol.upper()})
        row = query_result.mappings().first()
        if not row:
            return None
        return dict(row)

    async def get_rs_history(
        self,
        symbol: str,
        benchmark: str = "NIFTY 500",
        months: int = 12,
    ) -> list[dict[str, Any]]:
        """Get RS history for a stock."""
        query = text(f"""
            SELECT r.date, r.rs_composite, r.rs_1w, r.rs_1m, r.rs_3m
            FROM de_rs_scores r
            JOIN de_instrument i ON r.entity_id = i.id::text
            WHERE i.current_symbol = :symbol
              AND r.entity_type = 'equity'
              AND r.vs_benchmark = :benchmark
              AND r.date >= CURRENT_DATE - INTERVAL '{months} months'
            ORDER BY r.date
        """)

        query_result = await self.session.execute(
            query, {"symbol": symbol.upper(), "benchmark": benchmark}
        )
        return [dict(row) for row in query_result.mappings().all()]

    async def get_sector_rollups(self) -> list[dict[str, Any]]:
        """Compute 22 metrics per sector from latest technicals + RS."""
        start_time = time.monotonic()

        query = text(f"""
            WITH {LATEST_DATES_CTE},
            {RS_CTE},
            {RS_28D_CTE},
            latest_tech AS (
                SELECT instrument_id, close_adj, rsi_14, adx_14, above_200dma, above_50dma,
                       ema_21, macd_histogram, roc_5, beta_nifty, sharpe_1y, sortino_1y,
                       volatility_20d, max_drawdown_1y, calmar_ratio, disparity_20
                FROM de_equity_technical_daily
                WHERE date = (SELECT tech_date FROM latest_dates)
            ),
            {MF_COUNTS_CTE}
            SELECT
                i.sector,
                COUNT(*) AS stock_count,
                AVG(r.rs_composite) AS avg_rs_composite,
                AVG(r.rs_composite
                    - COALESCE(r28.rs_composite_28d, r.rs_composite))
                    AS avg_rs_momentum,
                COUNT(*) FILTER (WHERE t.above_200dma = true)
                    * 100.0 / NULLIF(COUNT(*), 0) AS pct_above_200dma,
                COUNT(*) FILTER (WHERE t.above_50dma = true)
                    * 100.0 / NULLIF(COUNT(*), 0) AS pct_above_50dma,
                COUNT(*) FILTER (WHERE t.close_adj > t.ema_21)
                    * 100.0 / NULLIF(COUNT(*), 0) AS pct_above_ema21,
                AVG(t.rsi_14) AS avg_rsi_14,
                COUNT(*) FILTER (WHERE t.rsi_14 > 70)
                    * 100.0 / NULLIF(COUNT(*), 0) AS pct_rsi_overbought,
                COUNT(*) FILTER (WHERE t.rsi_14 < 30)
                    * 100.0 / NULLIF(COUNT(*), 0) AS pct_rsi_oversold,
                AVG(t.adx_14) AS avg_adx,
                COUNT(*) FILTER (WHERE t.adx_14 > 25)
                    * 100.0 / NULLIF(COUNT(*), 0) AS pct_adx_trending,
                COUNT(*) FILTER (WHERE t.macd_histogram > 0)
                    * 100.0 / NULLIF(COUNT(*), 0) AS pct_macd_bullish,
                COUNT(*) FILTER (WHERE t.roc_5 > 0)
                    * 100.0 / NULLIF(COUNT(*), 0) AS pct_roc5_positive,
                AVG(t.beta_nifty) AS avg_beta,
                AVG(t.sharpe_1y) AS avg_sharpe,
                AVG(t.sortino_1y) AS avg_sortino,
                AVG(t.volatility_20d) AS avg_volatility_20d,
                AVG(t.max_drawdown_1y) AS avg_max_dd,
                AVG(t.calmar_ratio) AS avg_calmar,
                AVG(mc.mf_holder_count) AS avg_mf_holders,
                AVG(t.disparity_20) AS avg_disparity_20
            FROM de_instrument i
            LEFT JOIN latest_rs r ON r.entity_id = i.id::text
            LEFT JOIN rs_28d r28 ON r28.entity_id = i.id::text
            LEFT JOIN latest_tech t ON t.instrument_id = i.id
            LEFT JOIN mf_counts mc ON mc.instrument_id = i.id
            WHERE i.is_active = true AND i.sector IS NOT NULL
            GROUP BY i.sector
            ORDER BY AVG(r.rs_composite) DESC NULLS LAST
        """)

        query_result = await self.session.execute(query)
        rows = query_result.mappings().all()

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        log.info("sector_rollups_computed", sectors=len(rows), ms=elapsed_ms)
        return [dict(row) for row in rows]

    async def get_movers(self, limit: int = 15) -> dict[str, list[dict[str, Any]]]:
        """Get top RS momentum gainers and losers."""
        query = text(f"""
            WITH {LATEST_DATES_CTE},
            {RS_CTE},
            {RS_28D_CTE},
            momentum AS (
                SELECT
                    i.current_symbol AS symbol, i.company_name, i.sector,
                    r.rs_composite,
                    r.rs_composite - COALESCE(r28.rs_composite_28d, r.rs_composite) AS rs_momentum
                FROM de_instrument i
                JOIN latest_rs r ON r.entity_id = i.id::text
                LEFT JOIN rs_28d r28 ON r28.entity_id = i.id::text
                WHERE i.is_active = true AND i.nifty_500 = true
            )
            (SELECT *, 'gainer' AS mover_type FROM momentum
             ORDER BY rs_momentum DESC NULLS LAST LIMIT :lim)
            UNION ALL
            (SELECT *, 'loser' AS mover_type FROM momentum
             ORDER BY rs_momentum ASC NULLS LAST LIMIT :lim)
        """)

        query_result = await self.session.execute(query, {"lim": limit})
        rows = [dict(row) for row in query_result.mappings().all()]

        return {
            "gainers": [row for row in rows if row.get("mover_type") == "gainer"],
            "losers": [row for row in rows if row.get("mover_type") == "loser"],
        }
