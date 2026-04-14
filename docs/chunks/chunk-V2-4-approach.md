# Chunk V2-4 Approach: MF Category Rollup + Universe/Categories/Flows Routes

## Data Scale (actual row counts)
- `de_mf_master`: 13,380 rows (12,581 active non-ETF funds)
- `de_mf_derived_daily`: 728,735 rows (daily derived metrics)
- `de_mf_holdings`: 230,254 rows
- `de_rs_scores`: 14,779,545 rows (equity + MF combined)
- `de_mf_category_flows`: 3,177 rows
- `de_mf_sector_exposure`: 13,211 rows

Scale decision: All aggregation stays in SQL. Universe = ~12K rows pulled from
DB (sub-second with CTEs + DISTINCT ON). Python only for grouping into hierarchy
and Decimal conversion. No pandas anywhere — pure dict manipulation.

## Chosen Approach

### CATEGORIES_SQL: Add PERCENTILE_CONT
The existing CATEGORIES_SQL already has a GROUP BY with `AVG(d.manager_alpha)`.
We add two ordered-set aggregates alongside the AVG:
- `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY d.manager_alpha)` AS manager_alpha_p50
- `PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY d.manager_alpha)` AS manager_alpha_p90
Both added to CATEGORIES_DECIMAL_FIELDS.

### compute_category_rollup helper
New function in `mf_compute.py`. Takes:
- `universe_rows`: enriched universe rows (with `quadrant` field already set)
- `cat_rows`: raw category rows from JIP (have active_fund_count, avg_rs_composite,
  manager_alpha_p50, manager_alpha_p90, net_flow_cr, sip_flow_cr, aum_cr)
Returns list of dicts ready for CategoryRow construction. Computes
`quadrant_distribution` by iterating enriched universe rows per category.

### Route wiring
All three routes follow the stocks.py thin shim pattern:
1. Create JIPDataService(db)
2. Call service method(s)
3. Transform to Pydantic model
4. Return

**`/universe`**:
- `get_mf_universe(...)` → flat rows with derived_rs_composite, manager_alpha
- `get_mf_rs_momentum_batch()` → dict[mstar_id → {rs_momentum_28d, ...}]
- `get_mf_data_freshness()` → freshness dates
- For each fund row: look up rs_batch, set rs_momentum_28d, classify quadrant
- Group flat rows into BroadCategoryGroup → CategoryGroup → Fund hierarchy
- Build UniverseResponse

**`/categories`**:
- `get_mf_categories()` → category rows (with new p50/p90 fields)
- `get_mf_universe(active_only=True)` → flat rows for quadrant distribution
- `get_mf_rs_momentum_batch()` → batch RS
- Enrich universe rows with quadrant via classify_fund_quadrant
- Aggregate per category: count each quadrant
- Map SQL field names → CategoryRow (active_fund_count→fund_count, aum_cr→total_aum_cr)
- Build CategoriesResponse

**`/flows`**:
- `get_mf_flows(months)` → flat rows, map directly to FlowRow list
- `get_mf_data_freshness()` → freshness
- Build FlowsResponse

### Staleness calculation
From `get_mf_data_freshness()` result: `nav_as_of` date.
age_minutes = (today - nav_as_of).days * 24 * 60
flag: FRESH < 1440min, STALE < 2880min, else EXPIRED

### Field mapping
Categories SQL → CategoryRow:
- active_fund_count → fund_count
- avg_rs_composite → avg_rs_composite
- aum_cr → total_aum_cr
- manager_alpha_p50 → manager_alpha_p50
- manager_alpha_p90 → manager_alpha_p90
- net_flow_cr → net_flow_cr
- sip_flow_cr → sip_flow_cr
- quadrant_distribution → computed from universe rows

## Wiki Patterns Checked
- UQL Dispatcher Engine: routes are thin shims
- Decimal Not Float: safe_decimal() for all financial values
- DISTINCT ON Latest-Row-Per-Key: existing SQL pattern reused
- Cassette Test Pattern: mock JIPMFService with _FakeMappings/_FakeResult

## Existing Code Reused
- `classify_fund_quadrant()` from `mf_compute.py`
- `compute_universe_metrics()` from `mf_compute.py`
- `safe_decimal()` from `sql_fragments.py`
- `_decimalize()` in `jip_mf_service.py`
- `get_db` dependency pattern from stocks.py

## Edge Cases
- NULL manager_alpha: PERCENTILE_CONT ignores NULLs in PostgreSQL, returns NULL if all NULL
- Fund with no RS history: rs_momentum_28d=None, quadrant=None
- Empty category: fund_count=0, quadrant_distribution={}
- Freshness: use nav_as_of if present, else today (EXPIRED)
- /universe with filters: active_only=True default, None means True per spec

## Test Strategy
New file `tests/api/test_mf_routes.py` using mock pattern (no real DB).
Mock JIPDataService methods to return fixture data.
Tests:
- /universe 200, correct structure, fund_count consistency
- /categories 200, p50/p90 as Decimal, quadrant_distribution keys
- /flows 200, 12 months default, FlowRow fields
- Decimal invariant (no float in response)
- staleness flag logic

## Expected Runtime (t3.large)
- UNIVERSE_SQL: ~200ms (12K rows with 2 CTEs)
- RS_MOMENTUM_SQL: ~500ms (14M rs_scores rows, batch for ~8K MF entities)
- CATEGORIES_SQL: ~150ms (13K master rows, 3 CTEs with GROUP BY)
- Total /universe warm: ~900ms (within 2s p95 target)
- Total /categories warm: ~1.5s (universe + RS batch + categories)
