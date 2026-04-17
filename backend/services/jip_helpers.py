"""
JIP read helpers — reusable DISTINCT ON wrappers for de_* tables.

Every de_* table read must use DISTINCT ON to get only the latest row per
ticker/entity. Never read de_* tables without this wrapper.
"""

from __future__ import annotations

import time
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Any, Optional
import datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


def _safe_decimal(value: Any) -> Optional[Decimal]:
    """Convert value to Decimal; return None if None/NaN/empty."""
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
        # Reject NaN and Infinity
        if not parsed.is_finite():
            return None
        return parsed
    except (InvalidOperation, DecimalException, ValueError, ArithmeticError):
        return None


async def latest_etf_technicals(
    session: AsyncSession,
    tickers: Optional[list[str]] = None,
    as_of: Optional[datetime.date] = None,
) -> dict[str, dict[str, Any]]:
    """
    Return latest technical row per ticker from de_etf_technical_daily.
    Uses DISTINCT ON to guarantee exactly one row per ticker.

    Args:
        session: Async DB session connected to JIP read-replica
        tickers: Optional list to filter; None = all active ETFs
        as_of: Cutoff date (inclusive); None = latest available

    Returns:
        dict keyed by ticker -> raw row dict with all technical columns
    """
    t0 = time.perf_counter()

    date_filter = "AND date <= :as_of" if as_of else ""
    ticker_filter = "AND ticker = ANY(:tickers)" if tickers else ""

    sql = text(f"""
        SELECT DISTINCT ON (ticker)
            ticker,
            date,
            close             AS close_price,
            volume,
            rsi_14,
            macd,
            macd_signal,
            macd_hist,
            bb_upper,
            bb_middle,
            bb_lower,
            bb_width,
            sma_20,
            sma_50,
            sma_200,
            ema_9,
            ema_21,
            adx_14,
            di_plus,
            di_minus,
            stoch_k,
            stoch_d,
            atr_14,
            obv,
            vwap,
            mom_10,
            roc_10,
            cci_20,
            wpr_14,
            cmf_20
        FROM de_etf_technical_daily
        WHERE 1=1
            {date_filter}
            {ticker_filter}
        ORDER BY ticker, date DESC
    """)

    params: dict[str, Any] = {}
    if as_of:
        params["as_of"] = as_of
    if tickers:
        params["tickers"] = tickers

    await session.execute(text("SET LOCAL statement_timeout = '5000'"))
    query_result = await session.execute(sql, params)
    rows = query_result.mappings().all()

    elapsed = (time.perf_counter() - t0) * 1000
    log.info("jip_etf_technicals_fetched", count=len(rows), elapsed_ms=round(elapsed, 1))
    return {row["ticker"]: dict(row) for row in rows}


async def latest_etf_rs(
    session: AsyncSession,
    tickers: Optional[list[str]] = None,
    as_of: Optional[datetime.date] = None,
) -> dict[str, dict[str, Any]]:
    """
    Return latest RS row per ETF ticker from de_rs_scores.
    Uses DISTINCT ON to guarantee exactly one row per ticker.
    """
    t0 = time.perf_counter()

    date_filter = "AND date <= :as_of" if as_of else ""
    ticker_filter = "AND entity_id = ANY(:tickers)" if tickers else ""

    sql = text(f"""
        SELECT DISTINCT ON (entity_id)
            entity_id   AS ticker,
            date,
            rs_composite,
            rs_momentum,
            quadrant
        FROM de_rs_scores
        WHERE entity_type = 'etf'
            {date_filter}
            {ticker_filter}
        ORDER BY entity_id, date DESC
    """)

    params: dict[str, Any] = {}
    if as_of:
        params["as_of"] = as_of
    if tickers:
        params["tickers"] = tickers

    await session.execute(text("SET LOCAL statement_timeout = '5000'"))
    query_result = await session.execute(sql, params)
    rows = query_result.mappings().all()

    elapsed = (time.perf_counter() - t0) * 1000
    log.info("jip_etf_rs_fetched", count=len(rows), elapsed_ms=round(elapsed, 1))
    return {row["ticker"]: dict(row) for row in rows}


async def etf_master_rows(
    session: AsyncSession,
    country: Optional[str] = None,
    benchmark: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Return active ETF master rows filtered by country/benchmark.
    de_etf_master has one row per ticker (no DISTINCT ON needed).
    """
    t0 = time.perf_counter()

    country_filter = "AND country = :country" if country else ""
    benchmark_filter = "AND benchmark = :benchmark" if benchmark else ""

    sql = text(f"""
        SELECT
            ticker,
            name,
            country,
            currency,
            sector,
            category,
            benchmark,
            expense_ratio,
            inception_date,
            is_active
        FROM de_etf_master
        WHERE is_active = true
            {country_filter}
            {benchmark_filter}
        ORDER BY ticker
    """)

    params: dict[str, Any] = {}
    if country:
        params["country"] = country
    if benchmark:
        params["benchmark"] = benchmark

    await session.execute(text("SET LOCAL statement_timeout = '5000'"))
    query_result = await session.execute(sql, params)
    rows = query_result.mappings().all()

    elapsed = (time.perf_counter() - t0) * 1000
    log.info("jip_etf_master_fetched", count=len(rows), elapsed_ms=round(elapsed, 1))
    return [dict(row) for row in rows]


async def etf_single_master(
    session: AsyncSession,
    ticker: str,
) -> Optional[dict[str, Any]]:
    """Fetch single ETF master row. Returns None if ticker not found."""
    sql = text("""
        SELECT
            ticker, name, exchange, country, currency, sector,
            asset_class, category, benchmark, expense_ratio,
            inception_date, is_active
        FROM de_etf_master
        WHERE ticker = :ticker
        LIMIT 1
    """)
    await session.execute(text("SET LOCAL statement_timeout = '5000'"))
    query_result = await session.execute(sql, {"ticker": ticker.upper()})
    row = query_result.mappings().first()
    return dict(row) if row else None


async def etf_chart_data(
    session: AsyncSession,
    ticker: str,
    from_date: datetime.date,
    to_date: datetime.date,
) -> list[dict[str, Any]]:
    """
    Return OHLCV + key technicals for ticker over date range.
    DISTINCT ON (o.date) prevents duplicate date rows.
    """
    sql = text("""
        SELECT DISTINCT ON (o.date)
            o.date,
            o.open,
            o.high,
            o.low,
            o.close,
            o.volume,
            t.sma_50,
            t.sma_200,
            t.ema_20,
            t.rsi_14,
            t.macd_line,
            t.macd_signal,
            t.macd_histogram,
            t.bollinger_upper,
            t.bollinger_lower,
            t.adx_14
        FROM de_etf_ohlcv o
        LEFT JOIN de_etf_technical_daily t
            ON t.ticker = o.ticker AND t.date = o.date
        WHERE o.ticker = :ticker
          AND o.date BETWEEN :from_date AND :to_date
        ORDER BY o.date ASC
    """)
    await session.execute(text("SET LOCAL statement_timeout = '10000'"))
    query_result = await session.execute(
        sql,
        {"ticker": ticker.upper(), "from_date": from_date, "to_date": to_date},
    )
    return [dict(r) for r in query_result.mappings().all()]


async def etf_rs_history(
    session: AsyncSession,
    ticker: str,
    from_date: datetime.date,
    to_date: datetime.date,
) -> list[dict[str, Any]]:
    """
    Return RS time-series for a single ETF ticker over date range.
    DISTINCT ON (date) prevents duplicate date rows.
    """
    sql = text("""
        SELECT DISTINCT ON (date)
            date,
            rs_composite,
            rs_momentum,
            quadrant
        FROM de_rs_scores
        WHERE entity_type = 'etf'
          AND entity_id = :ticker
          AND date BETWEEN :from_date AND :to_date
        ORDER BY date ASC
    """)
    await session.execute(text("SET LOCAL statement_timeout = '5000'"))
    query_result = await session.execute(
        sql,
        {"ticker": ticker.upper(), "from_date": from_date, "to_date": to_date},
    )
    return [dict(r) for r in query_result.mappings().all()]
