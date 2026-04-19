---
chunk: V2FE-1c
project: atlas
date: 2026-04-19
---
# V2FE-1c Approach

## Scope
3 source edits + 2 new test files.

## Data scale
No data queries in this chunk — pure template registration + route wiring.
The `conviction_series` query touches `atlas_gold_rs_cache` (LIMIT 52 rows per fund).

## Chosen approach

### 1. templates.py — add `_stock_peers` + `_sector_breadth_template`, update `_mf_rank_composite`
- `_stock_peers`: UQL equity entity, NEQ filter to exclude anchor, sort by rs_composite DESC
- `_sector_breadth_template`: sector entity with group_by + aggregations (pct_true for booleans)
- `_mf_rank_composite`: update to accept optional `category`/`period` params, use correct MF entity fields
- REGISTRY extended with two new keys

### 2. models/mf.py — add `conviction_series` to `WeightedTechnicalsResponse`
- `Optional[list[dict[str, Any]]]` field — add `Any` to typing import

### 3. routes/mf.py — wire `get_fund_weighted_technicals`
- Replace `not_implemented()` stub with real implementation
- Follows spec §18 include pattern (same as breadth.py)
- `conviction_series` include: raw SQL on `atlas_gold_rs_cache` with try/except → `[]` on failure
- Add `db: AsyncSession = Depends(get_db)` to the route signature
- Add `include: Optional[str] = Query(None)` param

### 4. tests/api/test_uql_templates.py (new)
- ASGI + dependency override + `patch(engine.execute_template)` pattern
- Tests: stock_peers valid/missing-symbol, mf_rank_composite valid/no-params, sector_breadth_template valid/universe-param
- Error cases: unknown template 404, missing required param 400

### 5. tests/api/test_mf_weighted_technicals_include.py (new)
- ASGI + patch JIPDataService pattern
- Tests: 200 response shape, staleness, data_as_of, conviction_series absent without include,
  present with include, empty [] when no rows, fault-tolerant [] on DB exception

## Wiki patterns applied
- [FastAPI Dependency Override in Tests](patterns/fastapi-dependency-override-in-tests.md) — ASGI fixture
- [UQL Dispatcher Engine](patterns/uql-dispatcher-engine.md) — templates go through shared engine

## Existing code reused
- `_require` / `_optional` helpers already in templates.py
- `compute_staleness`, `data_as_of_from_freshness` from mf_helpers.py
- `JIPDataService.get_fund_weighted_technicals` already in jip_data_service.py

## Edge cases
- `conviction_series` DB query fails → returns `[]`, never raises 500
- `wt` is None (fund has no weighted technicals) → None fields, as_of_date falls back to data_as_of
- `mf_rank_composite` with no category → no filter added (all active funds)
- `_stock_peers` missing `symbol` → UQLError TEMPLATE_PARAM_MISSING → HTTP 400

## Expected runtime
- Test suite: <5s (all mocked, no live DB)
- Route: <50ms (single SQL query LIMIT 52)
