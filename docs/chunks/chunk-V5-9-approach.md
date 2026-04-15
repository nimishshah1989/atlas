---
chunk: V5-9
project: atlas
date: 2026-04-15
title: Global Intelligence API — 5 read-only routes
---

# Approach

## Data Scale
- `atlas_briefings` — empty (V5-8 pipeline exists but runs on schedule; table may be empty)
- `atlas_intelligence` — small (<1K rows, agent findings)
- `de_macro_values` — JIP-owned; medium (~10K-50K rows), queried by ticker + date range
- `de_rs_scores WHERE entity_type='global'` — JIP-owned; subset of RS table
- `de_global_prices`, `de_global_instrument_master` — JIP-owned; small reference tables

Scale: All queries at or under 1K rows → SQL is fine, no pandas needed.

## Approach

### Route Implementation
5 routes under `/api/v1/global`, each returning §20.4 `{data, _meta}` envelope.

### Empty data handling (critical)
- `atlas_briefings` is likely empty → `/briefing` must return `{data: null, _meta: {..., stale: true}}`
- `atlas_intelligence` may have no global-type findings → empty list is valid
- `de_*` tables may have partial data → graceful degradation per spec

### JIP service methods (added to JIPMarketService)
- `get_macro_ratios()` — JOIN de_macro_values + de_macro_master, last 10 values per ticker
- `get_global_rs_heatmap()` — JOIN de_rs_scores + de_global_prices + de_global_instrument_master

### ORM reads (atlas-owned tables)
- `atlas_briefings` — SQLAlchemy `select(AtlasBriefing).where(scope='market').order_by(date.desc()).limit(1)`
- `atlas_intelligence` — SQLAlchemy `select(AtlasIntelligence).where(finding_type.in_([...]))`

### Wiki patterns checked
- `contract-stub-501-sync` — need to check if any stub test lists /global/* paths
- `fastapi-dependency-patch-gotcha` — get_db must be overridden even when service is mocked
- `dual-key-model-serializer-compat` — emit both `data` + legacy key + `_meta` + `meta`
- `session-poisoning-missing-table` — if de_global_prices/etc doesn't exist, catch and degrade

### Existing code reused
- `JIPMarketService` — add 2 new methods here
- `JIPDataService` — expose the 2 new methods as facade pass-throughs
- `backend/models/intelligence.py` — pattern for model_serializer envelope
- `backend/db/session.py` — `get_db` dependency
- `backend/models/schemas.py` — `ResponseMeta`

### Edge cases
- Empty `atlas_briefings` → stale=True response with null data (not 404)
- `de_global_instrument_master` — may not have all tickers in rs_scores; use LEFT JOIN
- NULL values in macro series (gaps) — include in sparkline as null
- `de_global_prices` missing ticker → show RS entry without price
- SQL CAST collision: use CAST() not ::type in text() queries with named params

### Test location
`tests/routes/test_global_intel.py` (NOT `tests/api/` — that dir auto-marks as integration)

### Expected runtime
Each query <100ms on RDS. All routes will complete well under 500ms.

## Files to create/modify
1. `backend/models/global_intel.py` — new Pydantic models
2. `backend/clients/jip_market_service.py` — add 2 methods
3. `backend/clients/jip_data_service.py` — expose 2 new methods
4. `backend/routes/global_intel.py` — 5 route handlers
5. `backend/main.py` — register router
6. `tests/routes/test_global_intel.py` — unit tests
7. `contracts/v5-api.openapi.yaml` — add 5 new route specs
