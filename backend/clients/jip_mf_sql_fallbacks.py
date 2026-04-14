"""Fallback SQL variants for JIP MF queries.

Separated from jip_mf_sql.py to keep that module under the 500-line
modularity ceiling. Used when a JIP source table is not yet provisioned
and the main query would otherwise 500 the endpoint.
"""

FUND_DETAIL_SQL_NO_WEIGHTED = """
    WITH latest_nav AS (
        SELECT DISTINCT ON (mstar_id) mstar_id, nav_date, nav
        FROM de_mf_nav_daily WHERE mstar_id = :mstar_id
        ORDER BY mstar_id, nav_date DESC
    ),
    latest_derived AS (
        SELECT DISTINCT ON (mstar_id)
            mstar_id, nav_date AS derived_date,
            derived_rs_composite, nav_rs_composite,
            manager_alpha, coverage_pct,
            sharpe_1y, sharpe_3y, sharpe_5y,
            sortino_1y, sortino_3y, sortino_5y,
            max_drawdown_1y, max_drawdown_3y, max_drawdown_5y,
            volatility_1y, volatility_3y,
            stddev_1y, stddev_3y, stddev_5y,
            beta_vs_nifty, information_ratio, treynor_ratio
        FROM de_mf_derived_daily WHERE mstar_id = :mstar_id
        ORDER BY mstar_id, nav_date DESC
    ),
    latest_sectors AS (
        SELECT mstar_id, COUNT(*) AS sector_count,
            MAX(as_of_date) AS sector_as_of
        FROM de_mf_sector_exposure WHERE mstar_id = :mstar_id
        GROUP BY mstar_id
    ),
    latest_holdings AS (
        SELECT mstar_id, COUNT(*) AS holding_count,
            MAX(as_of_date) AS holdings_as_of
        FROM de_mf_holdings WHERE mstar_id = :mstar_id
        GROUP BY mstar_id
    )
    SELECT
        m.mstar_id, m.amfi_code, m.isin, m.fund_name, m.amc_name,
        m.category_name, m.broad_category, m.is_index_fund, m.is_etf,
        m.is_active, m.inception_date, m.closure_date,
        m.merged_into_mstar_id, m.primary_benchmark,
        m.expense_ratio, m.investment_strategy,
        n.nav, n.nav_date,
        d.derived_date, d.derived_rs_composite, d.nav_rs_composite,
        d.manager_alpha, d.coverage_pct,
        d.sharpe_1y, d.sharpe_3y, d.sharpe_5y,
        d.sortino_1y, d.sortino_3y, d.sortino_5y,
        d.max_drawdown_1y, d.max_drawdown_3y, d.max_drawdown_5y,
        d.volatility_1y, d.volatility_3y,
        d.stddev_1y, d.stddev_3y, d.stddev_5y,
        d.beta_vs_nifty, d.information_ratio, d.treynor_ratio,
        s.sector_count, s.sector_as_of,
        h.holding_count, h.holdings_as_of,
        NULL::date AS weighted_as_of,
        NULL::numeric AS weighted_rsi,
        NULL::numeric AS weighted_breadth_pct_above_200dma,
        NULL::numeric AS weighted_macd_bullish_pct
    FROM de_mf_master m
    LEFT JOIN latest_nav n ON n.mstar_id = m.mstar_id
    LEFT JOIN latest_derived d ON d.mstar_id = m.mstar_id
    LEFT JOIN latest_sectors s ON s.mstar_id = m.mstar_id
    LEFT JOIN latest_holdings h ON h.mstar_id = m.mstar_id
    WHERE m.mstar_id = :mstar_id
"""
