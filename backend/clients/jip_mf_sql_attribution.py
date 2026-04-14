"""SQL for Brinson attribution: category-level benchmark returns + alpha.

Separated from jip_mf_sql.py to keep the main module under 500 lines.
"""

# Category-level 1Y returns from NAV history + equal-weight benchmark weights
CATEGORY_NAV_RETURNS_SQL = """
    WITH latest_nav AS (
        SELECT DISTINCT ON (mstar_id)
            mstar_id, nav AS nav_latest
        FROM de_mf_nav_daily
        ORDER BY mstar_id, nav_date DESC
    ),
    past_nav AS (
        SELECT DISTINCT ON (mstar_id)
            mstar_id, nav AS nav_1y
        FROM de_mf_nav_daily
        WHERE nav_date <= CURRENT_DATE - INTERVAL '1 year'
        ORDER BY mstar_id, nav_date DESC
    ),
    fund_returns AS (
        SELECT
            m.mstar_id,
            m.category_name,
            CASE
                WHEN p.nav_1y IS NOT NULL AND p.nav_1y > 0
                THEN (l.nav_latest / p.nav_1y - 1)
                ELSE NULL
            END AS return_1y
        FROM de_mf_master m
        JOIN latest_nav l ON l.mstar_id = m.mstar_id
        LEFT JOIN past_nav p ON p.mstar_id = m.mstar_id
        WHERE m.is_etf = false AND m.is_active = true
          AND m.category_name IS NOT NULL
    ),
    category_totals AS (
        SELECT COUNT(*) AS total_active_funds FROM de_mf_master
        WHERE is_etf = false AND is_active = true AND category_name IS NOT NULL
    )
    SELECT
        f.category_name,
        COUNT(*) AS fund_count,
        AVG(f.return_1y) AS avg_return_1y,
        (COUNT(*) * 1.0) / NULLIF((SELECT total_active_funds FROM category_totals), 0)
            AS benchmark_weight
    FROM fund_returns f
    WHERE f.return_1y IS NOT NULL
    GROUP BY f.category_name
    HAVING COUNT(*) >= 2
    ORDER BY f.category_name
"""

CATEGORY_NAV_RETURNS_DECIMAL_FIELDS = (
    "avg_return_1y",
    "benchmark_weight",
)

# Category-level manager_alpha aggregate — used as selection effect proxy
# when per-fund returns are not available
CATEGORY_ALPHA_SQL = """
    WITH latest_derived AS (
        SELECT DISTINCT ON (mstar_id)
            mstar_id, manager_alpha
        FROM de_mf_derived_daily
        WHERE manager_alpha IS NOT NULL
        ORDER BY mstar_id, nav_date DESC
    )
    SELECT
        m.category_name,
        COUNT(*) AS fund_count,
        AVG(d.manager_alpha) AS avg_manager_alpha
    FROM de_mf_master m
    JOIN latest_derived d ON d.mstar_id = m.mstar_id
    WHERE m.is_etf = false AND m.is_active = true
      AND m.category_name IS NOT NULL
    GROUP BY m.category_name
    HAVING COUNT(*) >= 2
    ORDER BY m.category_name
"""

CATEGORY_ALPHA_DECIMAL_FIELDS = ("avg_manager_alpha",)
