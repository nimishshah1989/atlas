# Chunk V6-3 Approach: TV Cache Service + Webhook Route

## Data Scale
- `atlas_tv_cache` table: new, starts empty. Cache entries per (symbol, data_type, interval) — small dataset (hundreds at most). No scale concerns.
- No JIP de_* tables touched. Read-only pass through to cache.

## Approach

### 1. config.py additions
Add 3 new fields to existing `Settings` class: `tv_webhook_secret`, `tv_bridge_url`, `tv_cache_ttl_seconds`. Pydantic-settings picks them from env.

### 2. cache_service.py
Pure async service. Uses SQLAlchemy 2.0 `select()` + `insert().on_conflict_do_update()` for upsert. Background refresh opens its own session via `async_session_factory` — cannot reuse caller's session (asyncpg can't multiplex). Staleness = UTC now - fetched_at > ttl_seconds.

### 3. webhooks.py route
POST /api/webhooks/tradingview — no UQL needed (this is an inbound push webhook, not a query endpoint). 403 guard on header check before body parse. Pydantic v2 auto-raises 422 on bad body.

### 4. Tests placement
- Unit tests: `tests/unit/tv/test_cache_service.py` (already unit/ dir — no integration marker)
- Route tests: `tests/routes/test_tv_webhook.py` (NOT tests/api/ — that conftest auto-marks integration)

## Wiki Patterns Checked
- [Idempotent Upsert](patterns/idempotent-upsert.md) — ON CONFLICT DO UPDATE
- [AsyncMock Context Manager Pattern](patterns/asyncmock-context-manager-pattern.md) — mock __aenter__/__aexit__
- [FastAPI Dependency Patch Gotcha](bug-patterns/fastapi-dependency-patch-gotcha.md) — must patch get_db
- [Conftest Integration Marker Trap](bug-patterns/conftest-integration-marker-trap.md) — tests go in tests/routes/, not tests/api/

## Existing Code Reused
- `backend/db/tv_models.py` — AtlasTvCache ORM
- `backend/models/tv.py` — TvCacheEntry, TvDataType
- `backend/services/tv/bridge.py` — TVBridgeClient, TVBridgeUnavailableError
- `backend/db/session.py` — async_session_factory, get_db
- `backend/config.py` — Settings, get_settings

## Edge Cases
- NULL fetched_at: impossible (server_default=func.now()), but if it were NULL, treat as stale
- Empty symbol: rejected by Pydantic min_length=1
- Bridge unavailable on background refresh: swallow TVBridgeUnavailableError, log warning
- Missing/wrong X-TV-Signature header: 403 before body parse
- tv_webhook_secret="" (default): any non-empty header will not match "" — means webhook is disabled unless configured. Document this.

## Expected Runtime
- Cache lookup: <5ms (indexed PK lookup)
- Background refresh: async fire-and-forget, never blocks response
- Webhook upsert: <10ms (single PK upsert)
- All on t3.large well within budget
