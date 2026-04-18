"""JIP Equity Service — stock universe, detail, RS history, movers."""

import asyncio
import time
from datetime import date
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
    TECH_CTE_SLIM,
)

log = structlog.get_logger()

# Process-local TTL cache for the equity-universe query. JIP refreshes daily;
# a 5-minute cache prevents the 6-CTE join from saturating the connection
# pool under load.
_EQUITY_UNIVERSE_TTL_SECONDS = 300
_equity_universe_cache: dict[
    tuple[Optional[str], Optional[str]], tuple[float, list[dict[str, Any]]]
] = {}
_equity_universe_locks: dict[tuple[Optional[str], Optional[str]], asyncio.Lock] = {}


class JIPEquityService:
    """Read-only access to JIP equity data."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_equity_universe(
        self,
        benchmark: Optional[str] = "NIFTY 500",
        sector: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get all active instruments with latest technicals and RS. Cached 5m.

        The underlying query is a 6-CTE join with a full-table DISTINCT ON
        over de_market_cap_history that can run for 200+ seconds cold.
        Cached process-locally per (benchmark, sector); concurrent callers
        share a single in-flight query via per-key lock.
        """
        cache_key = (benchmark, sector)
        now = time.monotonic()
        cached = _equity_universe_cache.get(cache_key)
        if cached and now - cached[0] < _EQUITY_UNIVERSE_TTL_SECONDS:
            log.info("equity_universe_cache_hit", count=len(cached[1]))
            return cached[1]
        lock = _equity_universe_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = _equity_universe_cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < _EQUITY_UNIVERSE_TTL_SECONDS:
                log.info("equity_universe_cache_hit", count=len(cached[1]))
                return cached[1]
            rows = await self._fetch_equity_universe(benchmark=benchmark, sector=sector)
            _equity_universe_cache[cache_key] = (time.monotonic(), rows)
            return rows

    async def _fetch_equity_universe(
        self,
        benchmark: Optional[str],
        sector: Optional[str],
    ) -> list[dict[str, Any]]:
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
        """Get full stock data for deep-dive.

        Predicate-pushed single-symbol CTE. The shared CTE fragments in
        sql_fragments.py scan ALL instruments at the latest date (they are
        designed for sector/market rollups that need every row); joining
        them to a one-row `de_instrument` filter costs ~800-900ms cold and
        ~400ms warm because Postgres materializes the full CTEs first.
        This query instead pushes `instrument_id = (SELECT id FROM target)`
        into every CTE so each one returns at most one row. v1-03/v1-15
        budget is 500ms — single-symbol cold must fit under that.
        """
        query = text("""
            WITH target AS (
                SELECT id, current_symbol AS symbol, company_name, sector, industry,
                       nifty_50, nifty_200, nifty_500, isin, listing_date
                FROM de_instrument
                WHERE current_symbol = :symbol AND is_active = true
                LIMIT 1
            ),
            latest_dates AS (
                SELECT
                    (SELECT MAX(date) FROM de_rs_scores
                     WHERE entity_type = 'equity' AND vs_benchmark = 'NIFTY 500') AS rs_date,
                    (SELECT MAX(date) FROM de_equity_technical_daily) AS tech_date,
                    (SELECT MAX(as_of_date) FROM de_mf_holdings) AS mf_date
            ),
            latest_rs AS (
                SELECT entity_id, rs_composite, rs_1w, rs_1m, rs_3m, rs_6m, rs_12m
                FROM de_rs_scores
                WHERE entity_type = 'equity'
                  AND vs_benchmark = 'NIFTY 500'
                  AND date = (SELECT rs_date FROM latest_dates)
                  AND entity_id = (SELECT id::text FROM target)
            ),
            rs_28d_date AS (
                SELECT MAX(date) AS d FROM de_rs_scores
                WHERE entity_type = 'equity'
                  AND vs_benchmark = 'NIFTY 500'
                  AND date <= (SELECT rs_date FROM latest_dates) - INTERVAL '28 days'
            ),
            rs_28d AS (
                SELECT entity_id, rs_composite AS rs_composite_28d
                FROM de_rs_scores
                WHERE entity_type = 'equity'
                  AND vs_benchmark = 'NIFTY 500'
                  AND date = (SELECT d FROM rs_28d_date)
                  AND entity_id = (SELECT id::text FROM target)
            ),
            latest_tech AS (
                SELECT instrument_id,
                    close_adj, sma_50, sma_200, ema_20,
                    rsi_14, adx_14, macd_line, macd_signal, macd_histogram,
                    above_200dma, above_50dma,
                    beta_nifty, sharpe_1y, sortino_1y, max_drawdown_1y, calmar_ratio,
                    volatility_20d, NULL::numeric AS relative_volume, mfi_14, obv,
                    NULL::numeric AS delivery_vs_avg, bollinger_upper, bollinger_lower,
                    CASE WHEN sma_20 > 0
                         THEN ((close_adj - sma_20) / sma_20 * 100)
                         ELSE NULL
                    END AS disparity_20,
                    stochastic_k, stochastic_d
                FROM de_equity_technical_daily
                WHERE date = (SELECT tech_date FROM latest_dates)
                  AND instrument_id = (SELECT id FROM target)
            ),
            mf_counts AS (
                SELECT instrument_id, COUNT(DISTINCT mstar_id) AS mf_holder_count
                FROM de_mf_holdings
                WHERE as_of_date = (SELECT mf_date FROM latest_dates)
                  AND instrument_id = (SELECT id FROM target)
                GROUP BY instrument_id
            ),
            latest_cap AS (
                SELECT DISTINCT ON (instrument_id)
                    instrument_id, cap_category
                FROM de_market_cap_history
                WHERE instrument_id = (SELECT id FROM target)
                ORDER BY instrument_id, effective_from DESC
            )
            SELECT
                i.id, i.symbol, i.company_name, i.sector, i.industry,
                i.nifty_50, i.nifty_200, i.nifty_500, i.isin, i.listing_date,
                t.close_adj AS close, t.sma_50, t.sma_200, t.ema_20,
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
            FROM target i
            LEFT JOIN latest_rs r ON r.entity_id = i.id::text
            LEFT JOIN rs_28d r28 ON r28.entity_id = i.id::text
            LEFT JOIN latest_tech t ON t.instrument_id = i.id
            LEFT JOIN mf_counts mc ON mc.instrument_id = i.id
            LEFT JOIN latest_cap cap ON cap.instrument_id = i.id
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
                       ema_20, macd_histogram, roc_5, beta_nifty, sharpe_1y, sortino_1y,
                       volatility_20d, max_drawdown_1y, calmar_ratio,
                       CASE WHEN sma_20 > 0
                            THEN ((close_adj - sma_20) / sma_20 * 100)
                            ELSE NULL
                       END AS disparity_20
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
                COUNT(*) FILTER (WHERE t.close_adj > t.ema_20)
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

    async def symbol_exists(self, symbol: str) -> bool:
        """Return True if an active instrument with this symbol exists.

        Args:
            symbol: Ticker symbol (e.g. "RELIANCE").
        """
        sql = text("""
            SELECT 1 FROM de_instrument
            WHERE current_symbol = :symbol AND is_active = true
            LIMIT 1
        """)
        query_result = await self.session.execute(sql, {"symbol": symbol.upper()})
        return query_result.fetchone() is not None

    async def get_corporate_actions(
        self,
        symbol: str,
    ) -> list[dict[str, Any]]:
        """Fetch distinct corporate actions with non-null adj_factor for a symbol.

        Uses DISTINCT ON (ex_date, action_type) to deduplicate JIP duplicates.
        Filters to action_types that affect share price (split, bonus, rights).
        Ordered by ex_date ASC.

        Args:
            symbol: Ticker symbol (e.g. "RELIANCE").

        Returns:
            List of dicts with: ex_date (date), action_type (str), adj_factor (Decimal).
        """
        sql = text("""
            SELECT DISTINCT ON (ca.ex_date, ca.action_type)
                ca.ex_date,
                ca.action_type,
                ca.adj_factor
            FROM de_corporate_actions ca
            JOIN de_instrument i ON i.id = ca.instrument_id
            WHERE i.current_symbol = :symbol
              AND i.is_active = true
              AND ca.adj_factor IS NOT NULL
              AND ca.adj_factor > 0
              AND ca.action_type IN ('split', 'bonus', 'rights')
            ORDER BY ca.ex_date ASC, ca.action_type ASC, ca.adj_factor ASC
        """)
        query_result = await self.session.execute(sql, {"symbol": symbol.upper()})
        rows = query_result.mappings().all()
        return [dict(r) for r in rows]

    async def get_chart_data(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
    ) -> list[dict[str, Any]]:
        """Return OHLCV + technical indicators for a symbol over a date range.

        JOINs de_equity_ohlcv (partitioned parent) with de_equity_technical_daily
        on (instrument_id, date). LEFT JOIN ensures OHLCV rows without matching
        technical data are still returned with NULL indicator fields.

        Args:
            symbol: Ticker symbol (e.g. "HDFCBANK").
            from_date: Start date (inclusive). Must be a date object — asyncpg rejects strings.
            to_date: End date (inclusive). Must be a date object.

        Returns:
            List of dicts with date, OHLCV, and technical indicator fields.
        """
        sql = text("""
            SELECT
                o.date,
                o.open,
                o.high,
                o.low,
                o.close,
                o.volume,
                t.sma_20,
                t.sma_50,
                t.sma_200,
                t.ema_20,
                t.rsi_14,
                t.macd_histogram
            FROM de_equity_ohlcv o
            JOIN de_instrument i ON i.id = o.instrument_id
            LEFT JOIN de_equity_technical_daily t
                ON t.instrument_id = o.instrument_id AND t.date = o.date
            WHERE i.current_symbol = :symbol
              AND i.is_active = true
              AND o.date BETWEEN :from_date AND :to_date
            ORDER BY o.date ASC
        """)
        query_result = await self.session.execute(
            sql,
            {"symbol": symbol.upper(), "from_date": from_date, "to_date": to_date},
        )
        rows = query_result.mappings().all()
        return [dict(r) for r in rows]
