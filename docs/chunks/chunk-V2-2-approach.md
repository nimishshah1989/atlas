# Chunk V2-2 Approach: JIP Client MF Extension

## Data Scale
- de_mf_master: ~13,380 rows (small)
- de_mf_nav_daily: ~1.4M+ rows (partitioned, needs date filter)
- de_mf_derived_daily: 727,398 rows (needs nav_date filter)
- de_mf_holdings: 230,254 rows (needs as_of_date filter)
- de_mf_sector_exposure: 13,211 rows (small)
- de_mf_category_flows: 3,125 rows (small)
- de_mf_lifecycle: 469 rows (small)
- de_rs_scores: used for MF RS with entity_type='mf'

All queries use WHERE on date/nav_date/as_of_date — no full-table scans.

## Chosen Approach
- All queries via SQL (not Python aggregation) — appropriate for the scale
- Pattern: same as JIPEquityService — text() queries, mappings().all(), list[dict]
- Use DISTINCT ON for "latest row per key" pattern (most efficient on PG)
- safe_decimal() for all financial columns (weight_pct, nav, flows, etc.)
- is_etf=false filter ALWAYS in get_mf_universe()

## Wiki Patterns Checked
- AsyncMock Context Manager Pattern — for cassette tests (mock session.execute())
- Facade Split of a God Module — this chunk extends the MF service portion

## Existing Code Being Reused
- JIPEquityService pattern: session.execute(text(...), params), mappings().all()
- JIPMarketService pattern: simple single-result queries
- test_jip_service_timeout.py: _FakeSession/_FakeResult/_FakeMappings pattern for mocking

## Punch List
1. Every method round-trips cassette tests (mock AsyncSession, verify shape)
2. is_etf=false in get_mf_universe() — explicit filter required
3. pipeline.py line 44 "SELECT MAX(date) FROM de_rs_scores" → move to JIPMarketService.get_latest_rs_date()

## Edge Cases
- is_etf=false: explicit WHERE clause (not just is_index_fund)
- NULL nav/RS: use COALESCE or return None fields via safe_decimal
- Empty holdings: return [] not None
- mstar_id not found in get_fund_detail: return None
- Overlap with zero common holdings: return overlap_pct=0, list=[]
- de_mf_weighted_technicals may not have row for every fund: return None

## Column Name Fixes
- de_mf_master: fund_name (NOT scheme_name), amc_name (NOT fund_house)
- de_mf_nav_daily: nav_date (NOT date)
- de_mf_derived_daily: nav_date (NOT date)
- Primary key: mstar_id (NOT fund_code)
- Fix existing get_mf_holders: scheme_name → fund_name

## Files Modified
- backend/clients/jip_mf_service.py — extend with 12 new methods + fix bug
- backend/clients/jip_data_service.py — add delegate methods for new MF methods
- backend/pipeline.py — remove direct de_* SQL, call JIP client method
- tests/unit/test_jip_mf_service.py — cassette tests (new file)

## Expected Runtime on t3.large
- get_mf_universe(): 200-500ms (13K rows with 3 JOINs)
- get_fund_nav_history(): 50-200ms (with mstar_id + date range filter on partitioned table)
- All other methods: <100ms (small tables or indexed lookups)
