# Chunk V6-4 Approach: TV TA + Screener + Fundamentals API Routes

## Summary
Add `GET /api/tv/ta/{symbol}`, `GET /api/tv/screener/{symbol}`, and `GET /api/tv/fundamentals/{symbol}` routes backed by the existing `TVCacheService.get_or_fetch()` infrastructure from V6-1/2/3.

## Data Scale
No new tables. Reads from `atlas_tv_cache` (composite PK: symbol, data_type, interval). Row count is bounded by (symbols × data_types × intervals) — expected <1000 rows. All queries are single-row lookups via PK — no scale concern.

## Chosen Approach
- Add response models to `backend/models/tv.py`
- Create `backend/routes/tv.py` router with 3 GET routes
- Register router in `backend/main.py`
- Return plain `dict[str, Any]` (§20.4 envelope) — same pattern as `backend/routes/webhooks.py`
- Use `TVCacheService.get_or_fetch()` with a `TVBridgeClient` constructed from settings
- Catch `TVBridgeUnavailableError` → 503

## Wiki Patterns Checked
- `FastAPI Dependency Patch Gotcha` — must patch `get_db` even when service mocked
- `Conftest Integration Marker Trap` — route tests must go in `tests/routes/`, not `tests/api/`
- `Local Sidecar Transport Error Wrapping` — bridge errors convert to domain exception (already done in V6-2)
- `Contract Stub 501 Sync` — no SKELETON_CALLS pattern in this project; skip

## Existing Code Reused
- `backend/services/tv/bridge.py` — `TVBridgeClient`, `TVBridgeUnavailableError`
- `backend/services/tv/cache_service.py` — `TVCacheService.get_or_fetch()`
- `backend/models/tv.py` — `TvCacheEntry`, `TvDataType`
- `backend/routes/webhooks.py` — exact pattern for plain dict response, structlog, get_settings()
- `tests/routes/test_tv_webhook.py` — mock pattern for ASGITransport + AsyncClient

## Edge Cases
- `entry.tv_data` can be any structure — use defensive `.get()` with `or` fallback (handles None values from external API)
- Bridge unavailable at route time → 503 (not 500)
- Stale cache hit → return data + `_meta.is_stale=True`
- symbol in path, exchange/interval as Optional query params with defaults

## Expected Runtime
Route handler: <50ms (DB PK lookup). Bridge call on cache miss: ~2s (sidecar). Background refresh never blocks response.

## Files to Create/Modify
1. `backend/models/tv.py` — ADD response models (TvTaData, TvTaMeta, TvTaResponse, TvScreenerData, TvFundamentalsData)
2. `backend/routes/tv.py` — CREATE (3 GET routes)
3. `backend/main.py` — ADD router registration
4. `tests/routes/test_tv_routes.py` — CREATE (6+ unit tests)
5. `tests/api/test_tv_ta.py` — CREATE (4 live integration tests, auto-skipped)
