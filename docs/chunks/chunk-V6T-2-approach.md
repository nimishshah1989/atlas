# V6T-2 Approach: Bridge rewrite + watchlist sync-tv route removal

## Data scale
No DB writes in this chunk. No de_* tables touched.
This is a pure service-layer and test rewrite.

## Chosen approach

### 1. bridge.py rewrite
Replace the httpx-based HTTP sidecar with direct `tradingview_screener` library calls.
- `asyncio.to_thread()` wraps the synchronous `Query().get_scanner_data()` call
- Three public methods: `get_ta_summary`, `get_screener`, `get_fundamentals`
- `TVBridgeUnavailableError` name preserved — callers (tv_routes, watchlists) unchanged
- No `__init__` parameters needed (library is in-process)
- Lazy import of `tradingview_screener.Query` inside `_run_query` closure
- Three column sets: `_TA_COLUMNS`, `_SCREENER_COLUMNS`, `_FUNDAMENTAL_COLUMNS`

### 2. watchlists.py sync-tv removal
Route `POST /{watchlist_id}/sync-tv` → always raises HTTPException(404).
Status code on decorator set to 404 for consistency with FastAPI convention.
Import of `TVBridgeClient, TVBridgeUnavailableError` removed since no longer used.

### 3. test_bridge_timeout.py rewrite
8 tests, all using `patch("backend.services.tv.bridge.asyncio.to_thread")` pattern.
This avoids real network calls and cleanly handles the async-to-sync boundary.
One additional test patches `tradingview_screener.Query` directly to verify
ticker formatting and market parameter.

### 4. test_watchlists.py updates
Tests 7, 8, 11 (sync-tv tests) updated to expect 404 with no DB access needed.
The route now immediately raises HTTPException(404) — no session queries occur.

## Wiki patterns checked
- [AsyncMock Context Manager Pattern] — relevant for the existing httpx tests but not needed in new
- [Local Sidecar Transport Error Wrapping] — being replaced by in-process library
- [Bridge Probe as Connectivity Test] — sync-tv bridge probe being removed
- [Fault-Tolerant Panel Isolation] — callers already handle TVBridgeUnavailableError → 503

## Existing code reused
- `TVBridgeUnavailableError` — same exception class, same name, callers unchanged
- `backend/routes/tv.py` — not touched (separate routes)
- `backend/services/tv/cache.py` — not touched

## Edge cases
- `df.empty` == True → raise TVBridgeUnavailableError("Symbol not found")
- Any Exception from Query → caught, re-raised as TVBridgeUnavailableError
- TVBridgeUnavailableError from inner _run_query → re-raised unchanged (not double-wrapped)
- `asyncio.to_thread` ensures the synchronous blocking call doesn't block the event loop

## Expected runtime
- Library call: ~200-2000ms per symbol (network to TradingView)
- No DB queries in this chunk
- Tests: < 5s (all mocked, no real network)

## Files modified
1. backend/services/tv/bridge.py — full rewrite
2. backend/routes/watchlists.py — sync-tv route body + import cleanup
3. tests/unit/tv/test_bridge_timeout.py — full rewrite
4. tests/routes/test_watchlists.py — 3 test updates (tests 7, 8, 11)
