"""SQL query constants for JIP MF service — separated for file-size gate."""

UNIVERSE_SQL = """
    WITH latest_nav AS (
        SELECT DISTINCT ON (mstar_id)
            mstar_id, nav_date, nav
        FROM de_mf_nav_daily
        ORDER BY mstar_id, nav_date DESC
    ),
    latest_derived AS (
        SELECT DISTINCT ON (mstar_id)
            mstar_id, nav_date AS derived_date,
            derived_rs_composite, nav_rs_composite,
            manager_alpha, sharpe_1y, sortino_1y,
            max_drawdown_1y, volatility_1y, beta_vs_nifty
        FROM de_mf_derived_daily
        ORDER BY mstar_id, nav_date DESC
    )
    SELECT
        m.mstar_id, m.amfi_code, m.isin, m.fund_name, m.amc_name,
        m.category_name, m.broad_category, m.is_index_fund, m.is_active,
        m.inception_date, m.expense_ratio,
        n.nav, n.nav_date,
        d.derived_rs_composite, d.nav_rs_composite, d.manager_alpha,
        d.sharpe_1y, d.sortino_1y, d.max_drawdown_1y,
        d.volatility_1y, d.beta_vs_nifty
    FROM de_mf_master m
    LEFT JOIN latest_nav n ON n.mstar_id = m.mstar_id
    LEFT JOIN latest_derived d ON d.mstar_id = m.mstar_id
    WHERE {where_clause}
    ORDER BY d.derived_rs_composite DESC NULLS LAST
"""

UNIVERSE_DECIMAL_FIELDS = (
    "nav",
    "expense_ratio",
    "derived_rs_composite",
    "nav_rs_composite",
    "manager_alpha",
    "sharpe_1y",
    "sortino_1y",
    "max_drawdown_1y",
    "volatility_1y",
    "beta_vs_nifty",
)

CATEGORIES_SQL = """
    WITH latest_derived AS (
        SELECT DISTINCT ON (mstar_id)
            mstar_id, derived_rs_composite, manager_alpha
        FROM de_mf_derived_daily
        ORDER BY mstar_id, nav_date DESC
    ),
    latest_flows AS (
        SELECT DISTINCT ON (category)
            category, month_date, net_flow_cr, gross_inflow_cr,
            gross_outflow_cr, aum_cr, sip_flow_cr
        FROM de_mf_category_flows
        ORDER BY category, month_date DESC
    )
    SELECT
        m.category_name, m.broad_category,
        COUNT(*) FILTER (WHERE m.is_active = true AND m.is_etf = false)
            AS active_fund_count,
        AVG(d.derived_rs_composite) AS avg_rs_composite,
        AVG(d.manager_alpha) AS avg_manager_alpha,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY d.manager_alpha)
            AS manager_alpha_p50,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY d.manager_alpha)
            AS manager_alpha_p90,
        f.month_date AS latest_flow_date,
        f.net_flow_cr, f.gross_inflow_cr, f.gross_outflow_cr,
        f.aum_cr, f.sip_flow_cr
    FROM de_mf_master m
    LEFT JOIN latest_derived d ON d.mstar_id = m.mstar_id
    LEFT JOIN latest_flows f ON f.category = m.category_name
    WHERE m.is_etf = false
    GROUP BY
        m.category_name, m.broad_category,
        f.month_date, f.net_flow_cr, f.gross_inflow_cr,
        f.gross_outflow_cr, f.aum_cr, f.sip_flow_cr
    ORDER BY AVG(d.derived_rs_composite) DESC NULLS LAST
"""

CATEGORIES_DECIMAL_FIELDS = (
    "avg_rs_composite",
    "avg_manager_alpha",
    "manager_alpha_p50",
    "manager_alpha_p90",
    "net_flow_cr",
    "gross_inflow_cr",
    "gross_outflow_cr",
    "aum_cr",
    "sip_flow_cr",
)

FLOWS_SQL = """
    SELECT
        month_date, category, net_flow_cr, gross_inflow_cr,
        gross_outflow_cr, aum_cr, sip_flow_cr, sip_accounts, folios
    FROM de_mf_category_flows
    WHERE month_date >= CURRENT_DATE - (:months * INTERVAL '1 month')
    ORDER BY month_date DESC, category
"""

FLOWS_DECIMAL_FIELDS = (
    "net_flow_cr",
    "gross_inflow_cr",
    "gross_outflow_cr",
    "aum_cr",
    "sip_flow_cr",
)

FUND_DETAIL_SQL = """
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
    ),
    latest_weighted AS (
        SELECT DISTINCT ON (mstar_id)
            mstar_id, as_of_date AS weighted_as_of,
            weighted_rsi, weighted_breadth_pct_above_200dma,
            weighted_macd_bullish_pct
        FROM de_mf_weighted_technicals WHERE mstar_id = :mstar_id
        ORDER BY mstar_id, as_of_date DESC
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
        w.weighted_as_of, w.weighted_rsi,
        w.weighted_breadth_pct_above_200dma, w.weighted_macd_bullish_pct
    FROM de_mf_master m
    LEFT JOIN latest_nav n ON n.mstar_id = m.mstar_id
    LEFT JOIN latest_derived d ON d.mstar_id = m.mstar_id
    LEFT JOIN latest_sectors s ON s.mstar_id = m.mstar_id
    LEFT JOIN latest_holdings h ON h.mstar_id = m.mstar_id
    LEFT JOIN latest_weighted w ON w.mstar_id = m.mstar_id
    WHERE m.mstar_id = :mstar_id
"""

FUND_DETAIL_DECIMAL_FIELDS = (
    "expense_ratio",
    "nav",
    "derived_rs_composite",
    "nav_rs_composite",
    "manager_alpha",
    "coverage_pct",
    "sharpe_1y",
    "sharpe_3y",
    "sharpe_5y",
    "sortino_1y",
    "sortino_3y",
    "sortino_5y",
    "max_drawdown_1y",
    "max_drawdown_3y",
    "max_drawdown_5y",
    "volatility_1y",
    "volatility_3y",
    "stddev_1y",
    "stddev_3y",
    "stddev_5y",
    "beta_vs_nifty",
    "information_ratio",
    "treynor_ratio",
    "weighted_rsi",
    "weighted_breadth_pct_above_200dma",
    "weighted_macd_bullish_pct",
)

HOLDINGS_SQL = """
    WITH latest_as_of AS (
        SELECT MAX(as_of_date) AS as_of
        FROM de_mf_holdings WHERE mstar_id = :mstar_id
    ),
    latest_rs AS (
        SELECT DISTINCT ON (entity_id) entity_id, rs_composite
        FROM de_rs_scores WHERE entity_type = 'equity'
        ORDER BY entity_id, date DESC
    ),
    latest_tech AS (
        SELECT DISTINCT ON (instrument_id) instrument_id, above_200dma, rsi_14
        FROM de_equity_technical_daily
        ORDER BY instrument_id, date DESC
    )
    SELECT
        h.mstar_id, h.as_of_date, h.holding_name, h.isin,
        h.instrument_id, h.weight_pct, h.shares_held,
        h.market_value, h.sector_code, h.is_mapped,
        i.current_symbol, i.sector,
        r.rs_composite, t.above_200dma, t.rsi_14
    FROM de_mf_holdings h
    LEFT JOIN de_instrument i ON i.id = h.instrument_id
    LEFT JOIN latest_rs r ON r.entity_id = h.instrument_id::text
    LEFT JOIN latest_tech t ON t.instrument_id = h.instrument_id
    WHERE h.mstar_id = :mstar_id
      AND h.as_of_date = (SELECT as_of FROM latest_as_of)
    ORDER BY h.weight_pct DESC NULLS LAST
"""

SECTORS_SQL = """
    WITH latest_as_of AS (
        SELECT MAX(as_of_date) AS as_of
        FROM de_mf_sector_exposure WHERE mstar_id = :mstar_id
    )
    SELECT s.sector, s.weight_pct, s.stock_count, s.as_of_date
    FROM de_mf_sector_exposure s
    WHERE s.mstar_id = :mstar_id
      AND s.as_of_date = (SELECT as_of FROM latest_as_of)
    ORDER BY s.weight_pct DESC NULLS LAST
"""

RS_HISTORY_SQL = """
    SELECT
        date, rs_composite, rs_1w, rs_1m, rs_3m, rs_6m, rs_12m,
        vs_benchmark
    FROM de_rs_scores
    WHERE entity_id = :mstar_id
      AND entity_type = 'mf'
      AND date >= CURRENT_DATE - (:months * INTERVAL '1 month')
    ORDER BY date
"""

RS_HISTORY_DECIMAL_FIELDS = (
    "rs_composite",
    "rs_1w",
    "rs_1m",
    "rs_3m",
    "rs_6m",
    "rs_12m",
)

WEIGHTED_TECHNICALS_SQL = """
    SELECT mstar_id, as_of_date, weighted_rsi,
        weighted_breadth_pct_above_200dma, weighted_macd_bullish_pct
    FROM de_mf_weighted_technicals
    WHERE mstar_id = :mstar_id
    ORDER BY as_of_date DESC
    LIMIT 1
"""

NAV_HISTORY_SQL_TEMPLATE = """
    SELECT nav_date, nav
    FROM de_mf_nav_daily
    WHERE {where_clause}
    ORDER BY nav_date
"""

OVERLAP_AGG_SQL = """
    WITH as_of_a AS (
        SELECT MAX(as_of_date) AS d FROM de_mf_holdings WHERE mstar_id = :mstar_id_a
    ),
    as_of_b AS (
        SELECT MAX(as_of_date) AS d FROM de_mf_holdings WHERE mstar_id = :mstar_id_b
    ),
    holdings_a AS (
        SELECT instrument_id, holding_name, weight_pct
        FROM de_mf_holdings
        WHERE mstar_id = :mstar_id_a AND instrument_id IS NOT NULL
          AND as_of_date = (SELECT d FROM as_of_a)
    ),
    holdings_b AS (
        SELECT instrument_id, holding_name, weight_pct
        FROM de_mf_holdings
        WHERE mstar_id = :mstar_id_b AND instrument_id IS NOT NULL
          AND as_of_date = (SELECT d FROM as_of_b)
    ),
    common AS (
        SELECT a.instrument_id, a.holding_name,
            a.weight_pct AS weight_pct_a, b.weight_pct AS weight_pct_b
        FROM holdings_a a JOIN holdings_b b USING (instrument_id)
    )
    SELECT
        (SELECT COUNT(*) FROM holdings_a) AS count_a,
        (SELECT COUNT(*) FROM holdings_b) AS count_b,
        COUNT(*) AS common_count,
        SUM(LEAST(c.weight_pct_a, c.weight_pct_b)) AS overlap_pct
    FROM common c
"""

OVERLAP_DETAIL_SQL = """
    WITH as_of_a AS (
        SELECT MAX(as_of_date) AS d FROM de_mf_holdings WHERE mstar_id = :mstar_id_a
    ),
    as_of_b AS (
        SELECT MAX(as_of_date) AS d FROM de_mf_holdings WHERE mstar_id = :mstar_id_b
    ),
    holdings_a AS (
        SELECT instrument_id, holding_name, weight_pct
        FROM de_mf_holdings
        WHERE mstar_id = :mstar_id_a AND instrument_id IS NOT NULL
          AND as_of_date = (SELECT d FROM as_of_a)
    ),
    holdings_b AS (
        SELECT instrument_id, holding_name, weight_pct
        FROM de_mf_holdings
        WHERE mstar_id = :mstar_id_b AND instrument_id IS NOT NULL
          AND as_of_date = (SELECT d FROM as_of_b)
    )
    SELECT
        a.instrument_id, a.holding_name,
        a.weight_pct AS weight_pct_a, b.weight_pct AS weight_pct_b
    FROM holdings_a a JOIN holdings_b b USING (instrument_id)
    ORDER BY (a.weight_pct + b.weight_pct) DESC NULLS LAST
"""

RS_MOMENTUM_SQL = """
    WITH latest AS (
        SELECT DISTINCT ON (entity_id)
            entity_id, date AS latest_date, rs_composite AS latest_rs_composite
        FROM de_rs_scores
        WHERE entity_type = 'mf'
        ORDER BY entity_id, date DESC
    ),
    max_latest_date AS (
        SELECT MAX(latest_date) AS max_date FROM latest
    ),
    past AS (
        SELECT DISTINCT ON (entity_id)
            entity_id,
            date AS past_date,
            rs_composite AS past_rs_composite
        FROM de_rs_scores
        WHERE entity_type = 'mf'
          AND date <= (SELECT max_date FROM max_latest_date) - INTERVAL '28 days'
        ORDER BY entity_id, date DESC
    )
    SELECT
        l.entity_id AS mstar_id,
        l.latest_date,
        l.latest_rs_composite,
        p.past_date,
        p.past_rs_composite,
        CASE
            WHEN p.past_rs_composite IS NOT NULL
            THEN (l.latest_rs_composite - p.past_rs_composite)
            ELSE NULL
        END AS rs_momentum_28d
    FROM latest l
    LEFT JOIN past p ON l.entity_id = p.entity_id
"""

RS_MOMENTUM_DECIMAL_FIELDS = (
    "latest_rs_composite",
    "past_rs_composite",
    "rs_momentum_28d",
)

LIFECYCLE_SQL = """
    SELECT mstar_id, event_type, effective_date, detail
    FROM de_mf_lifecycle
    WHERE mstar_id = :mstar_id
    ORDER BY effective_date DESC
"""

FRESHNESS_SQL = """
    SELECT
        (SELECT MAX(nav_date) FROM de_mf_nav_daily) AS nav_as_of,
        (SELECT MAX(nav_date) FROM de_mf_derived_daily) AS derived_as_of,
        (SELECT MAX(as_of_date) FROM de_mf_holdings) AS holdings_as_of,
        (SELECT MAX(as_of_date) FROM de_mf_sector_exposure) AS sectors_as_of,
        (SELECT MAX(month_date) FROM de_mf_category_flows) AS flows_as_of,
        (SELECT MAX(as_of_date) FROM de_mf_weighted_technicals) AS weighted_as_of,
        (SELECT COUNT(*) FROM de_mf_master WHERE is_active = true AND is_etf = false)
            AS active_fund_count
"""

HOLDERS_SQL = """
    SELECT
        h.mstar_id, m.fund_name, h.weight_pct,
        h.shares_held, h.market_value
    FROM de_mf_holdings h
    JOIN de_instrument i ON h.instrument_id = i.id
    JOIN de_mf_master m ON h.mstar_id = m.mstar_id
    WHERE i.current_symbol = :symbol
      AND h.as_of_date = (SELECT MAX(as_of_date) FROM de_mf_holdings)
    ORDER BY h.weight_pct DESC NULLS LAST
    LIMIT 50
"""
