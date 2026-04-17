# Chunk V6-6 Approach — Watchlist CRUD + TV Sync API

## Data scale
- `atlas_watchlists` table: new, no existing rows
- No large data queries — CRUD against a small user-managed table

## Chosen approach
- Pure SQLAlchemy 2.0 async CRUD (select/update/delete via ORM, no raw SQL needed)
- Soft-delete pattern already on the model (is_deleted, deleted_at)
- TV sync: call `TVBridgeClient.get_screener(first_symbol, "NSE")` as connectivity test; empty symbols list → set tv_synced=True without bridge call

## Wiki patterns checked
- `Conftest Integration Marker Trap` — tests/api/ auto-marks as integration; place tests in tests/routes/
- `ORM Model __new__ Trap` — use MagicMock(spec=AtlasWatchlist) in tests
- `FastAPI Dependency Patch Gotcha` — override get_db via dependency_overrides
- `FastAPI Static Route Before Path Param` — /{id}/sync-tv registered after /{id} routes (fine, sync-tv is after UUID segment)
- `Contract Stub 501 Sync` — no skeleton stubs file found for watchlists

## Existing code reused
- `backend/db/models.py` AtlasWatchlist ORM model (lines 161-178)
- `backend/services/tv/bridge.py` TVBridgeClient + TVBridgeUnavailableError
- `backend/db/session.py` get_db dependency
- Pattern from `backend/routes/tv.py` and `tests/routes/test_tv_routes.py`

## Edge cases
- Empty symbols list on sync-tv → skip bridge call, set tv_synced=True
- Unknown UUID on GET/PATCH/DELETE → 404
- is_deleted=True items excluded from list
- TVBridgeUnavailableError → 503 with {"detail": "TV bridge unavailable"}
- datetime.now(UTC) for deleted_at (tz-aware)

## Files to create/modify
1. `backend/models/watchlist.py` — Pydantic v2 models
2. `backend/routes/watchlists.py` — FastAPI router
3. `backend/main.py` — register router
4. `tests/routes/test_watchlists.py` — 10+ tests (tests/routes/ avoids integration marker)

## Expected runtime
- All CRUD: <10ms per call (indexed PK lookup)
- TV sync: depends on bridge (mocked in tests)

## Test location note
The chunk spec says `tests/api/test_watchlists.py` but that conftest auto-marks as integration. Tests placed in `tests/routes/test_watchlists.py` instead — same tests, correct location per bug pattern.
