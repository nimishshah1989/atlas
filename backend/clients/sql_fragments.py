"""Shared SQL CTE fragments for JIP data queries.

Reusable across equity, market, and MF query modules.
"""

from decimal import Decimal
from typing import Any, Optional


def safe_decimal(val: Any) -> Optional[Decimal]:
    """Safe Decimal conversion — always through str."""
    if val is None:
        return None
    return Decimal(str(val))


LATEST_DATES_CTE = """
    latest_dates AS (
        SELECT
            (SELECT MAX(date) FROM de_rs_scores WHERE entity_type = 'equity' AND vs_benchmark = 'NIFTY 500') AS rs_date,
            (SELECT MAX(date) FROM de_equity_technical_daily) AS tech_date,
            (SELECT MAX(as_of_date) FROM de_mf_holdings) AS mf_date
    )
"""

RS_CTE = """
    latest_rs AS (
        SELECT entity_id, rs_composite, rs_1w, rs_1m, rs_3m, rs_6m, rs_12m
        FROM de_rs_scores
        WHERE entity_type = 'equity'
          AND vs_benchmark = 'NIFTY 500'
          AND date = (SELECT rs_date FROM latest_dates)
    )
"""

RS_28D_CTE = """
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
    )
"""

TECH_CTE_FULL = """
    latest_tech AS (
        SELECT instrument_id,
            close_adj, sma_50, sma_200, ema_21,
            rsi_14, adx_14, macd_line, macd_signal, macd_histogram,
            above_200dma, above_50dma,
            beta_nifty, sharpe_1y, sortino_1y, max_drawdown_1y, calmar_ratio,
            volatility_20d, relative_volume, mfi_14, obv,
            delivery_vs_avg, bollinger_upper, bollinger_lower,
            disparity_20, stochastic_k, stochastic_d, roc_5
        FROM de_equity_technical_daily
        WHERE date = (SELECT tech_date FROM latest_dates)
    )
"""

TECH_CTE_SLIM = """
    latest_tech AS (
        SELECT instrument_id, close_adj, rsi_14, adx_14, above_200dma, above_50dma,
               macd_histogram, beta_nifty, sharpe_1y
        FROM de_equity_technical_daily
        WHERE date = (SELECT tech_date FROM latest_dates)
    )
"""

MF_COUNTS_CTE = """
    mf_counts AS (
        SELECT instrument_id, COUNT(DISTINCT mstar_id) AS mf_holder_count
        FROM de_mf_holdings
        WHERE as_of_date = (SELECT mf_date FROM latest_dates)
          AND instrument_id IS NOT NULL
        GROUP BY instrument_id
    )
"""

CAP_CTE = """
    latest_cap AS (
        SELECT DISTINCT ON (instrument_id)
            instrument_id, cap_category
        FROM de_market_cap_history
        ORDER BY instrument_id, effective_from DESC
    )
"""
