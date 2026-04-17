# Chunk V7-2 Approach: ETF Detail + Chart-Data + RS-History Routes

## Data Scale
- de_etf_master: ~258 rows (single-row-per-ticker, no DISTINCT ON needed for master)
- de_etf_ohlcv: ~435,746 rows (ticker+date keyed, date-range queries with DISTINCT ON)
- de_etf_technical_daily: ~435,746 rows (same shape, LEFT JOIN to ohlcv)
- de_rs_scores: entity_type='etf' rows, unknown count but similar scale

## Approach

### SQL Strategy
- All reads via SQLAlchemy 2.0 async text() queries, never raw asyncpg
- DISTINCT ON (date) for chart-data and rs-history prevents duplicate date rows (JIP tables have duplicates per bug pattern jip-cte-duplicate-rows-window-dedup)
- Date-range WHERE clause on all OHLCV/RS queries to constrain scale
- statement_timeout SET LOCAL on each query to prevent runaway queries

### Route Order (Critical)
FastAPI path resolution: static before parameterized. Order in router:
1. /universe (already registered)
2. /{ticker}/chart-data (must be before /{ticker})
3. /{ticker}/rs-history (must be before /{ticker})
4. /{ticker} (catch-all path param, last)

### Model Serialization
- model_serializer(mode="wrap") pattern from V7-1 for §20.4 envelopes
- ETFDetailResponse: flat data dict + _meta key
- ETFChartDataResponse: {ticker, data: [points], _meta}
- ETFRSHistoryResponse: {ticker, months, data: [points], _meta}

### Private helpers imported from etf_service.py
- _safe_decimal, _build_rs_block, _build_technicals_block, _build_gold_rs_block, _fetch_gold_rs_bulk
- These are reused to avoid duplication

### Error codes
- ETF_NOT_FOUND (404): master row missing
- INVALID_DATE_RANGE (400): from >= to
- DATE_RANGE_TOO_LARGE (400): > 1826 days (5 years)
- JIP_UNAVAILABLE (503): SQLAlchemyError/OSError/etc

## Wiki Patterns Checked
- pydantic-v2-meta-serializer: model_serializer for _meta envelope (from V7-1)
- conftest-integration-marker-trap: tests go in tests/routes/ NOT tests/api/
- jip-cte-duplicate-rows-window-dedup: DISTINCT ON required on JIP tables
- FastAPI static route before path param: route declaration order critical
- Zero-value truthiness trap: use is not None for financial fields

## Existing Code Reused
- _safe_decimal from etf_service.py (imported)
- _build_rs_block, _build_technicals_block, _build_gold_rs_block from etf_service.py
- _fetch_gold_rs_bulk from etf_service.py
- latest_etf_technicals, latest_etf_rs from jip_helpers.py
- ResponseMeta from backend.models.schemas
- get_db from backend.db.session

## Edge Cases
- NULL financial values: _safe_decimal returns None (not 0)
- Missing master row: explicit 404 before any JIP data fetch
- Empty RS history: returns empty points list, not error
- quadrant value: wrapped in try/except Quadrant(val) with fallback None
- from_date == to_date: 400 INVALID_DATE_RANGE (strict less-than)
- months=12 uses exact year arithmetic to get ~365 days back

## Expected Runtime
- /etf/{ticker}: ~3 DB queries (master + technicals + rs + gold_rs) ~50-100ms
- /etf/{ticker}/chart-data (1y = 252 rows): ~20-40ms with index on (ticker, date)
- /etf/{ticker}/rs-history (12mo): ~10-20ms
- All within t3.large capability easily
