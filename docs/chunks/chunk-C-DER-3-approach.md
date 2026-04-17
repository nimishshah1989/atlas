# Chunk C-DER-3 Approach: Sector RRG + Sentiment Composite + Regime Enrichment

## Data Scale (verified live RDS 2026-04-17)
- `de_market_regime`: 4,396 rows — small, CTE aggregation fast (<10ms)
- `de_rs_scores`: 14.7M rows total; sector only 212,692 — filter by entity_type='sector'
- `de_sector_breadth_daily`: 127,584 rows — DISTINCT ON for latest-per-sector
- `de_fo_summary`: 0 rows — PCR pipeline dead, must mark unavailable
- `de_flow_daily`: 5 rows total, 0 FII rows — flow pipeline dead, mark unavailable
- `de_breadth_daily`: 4,382 rows — simple ORDER BY date DESC LIMIT 1
- `de_equity_fundamentals`: 2,272 rows — PERCENTILE_CONT aggregate

## Approach

### Part A — Regime Enrichment
- SQL CTE for `compute_days_in_regime`: single aggregation on ~4,396-row table, fast
- Python RLE for `compute_regime_history`: fetch 400 rows, O(n) loop, ~10ms
- Wired into `get_breadth` via `asyncio.gather` with isolated sessions (Isolated-Session Parallel Gather pattern)
- Empty table → None/[] gracefully

### Part B — RRG Service
- Main SQL: CTE joining today_rs + lag_rs + stats + breadth_latest — server-side computation
- ~31 sectors × 1 main query + ~31×4 tail query = 2 SQL calls total, ~124 tail rows
- Python normalisation: (rs_raw - mean) / stddev * 10 + 100
- Quadrant uses 100-centred comparison (NOT 0-centred like existing compute_quadrant)
- stddev=0 guard: set to 1 to avoid ZeroDivisionError
- DISTINCT ON (sector) ORDER BY sector, date DESC for breadth_latest — follows DISTINCT ON latest-row pattern

### Part C — Sentiment Service
- 4 component queries: breadth (hard-fail 503), PCR count (0→unavailable), flow count (≤5→unavailable), fundamentals medians
- Weight redistribution is a locked lookup table, not dynamic calculation
- Graceful degradation: PCR+Flow both unavailable → breadth=0.6, fund=0.4
- Zone thresholds: 20/40/60/80 boundaries

## Wiki Patterns Applied
- **Isolated-Session Parallel Gather**: per-query AsyncSession for concurrent gather in get_breadth
- **Gather Return Exceptions Optional Enrichment**: return_exceptions=True for regime enrichment
- **DISTINCT ON Latest-Row-Per-Key**: breadth_latest CTE uses DISTINCT ON (sector) ORDER BY sector, date DESC
- **SQLAlchemy Param-Cast Collision**: use CAST() not ::type with :param syntax
- **Zero-Value Truthiness Trap**: use `is not None` checks for all financial fields
- **FastAPI Dependency Patch Gotcha**: patch get_db in route tests
- **Conftest Integration Marker Trap**: route tests go in tests/routes/ (not tests/api/)

## Existing Code Reused
- `backend/db/session.py`: async_session_factory, get_db
- `backend/models/schemas.py`: Quadrant enum, ResponseMeta, RegimeSnapshot
- `backend/routes/stocks.py`: existing get_breadth — additive only
- Test patterns from test_stock_derived_signals.py

## Edge Cases
- `de_market_regime` empty → days_in_regime=None, regime_history=[]
- Regime never changed → days_in_regime = count of all rows, regime_history=[]
- stddev_rs=0 (all sectors identical) → set to 1, no ZeroDivisionError
- No lag row for sector → rs_composite_lag = rs_composite_today, raw_momentum=0
- de_fo_summary=0 → PCR unavailable, note="PCR data unavailable — pipeline gap"
- de_flow_daily≤5 → Flow unavailable, note="FII flow data unavailable — pipeline gap"
- Fundamentals all NULL → Component 4 unavailable
- Both PCR+Flow unavailable → weight_redistribution_active=True, breadth=0.6, fund=0.4

## Expected Runtime (t3.large)
- compute_days_in_regime: <10ms (CTE on 4,396 rows)
- compute_regime_history: <10ms (400 rows Python RLE)
- compute_sector_rrg: <30ms (2 SQL queries, ~124 rows)
- compute_sentiment_composite: <50ms (4 queries, all tiny)
- All endpoints <200ms cold, <100ms warm
