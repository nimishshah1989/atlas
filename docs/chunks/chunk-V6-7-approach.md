# Chunk V6-7 Approach: Alerts API + Alert Rules CRUD

## Data Scale
- `atlas_alerts` table: small (system-generated, in-flight alerts). Expected O(100s-1000s) rows.
- No table scans needed; simple WHERE filters on is_deleted, is_read, source.

## Chosen Approach
- SQLAlchemy 2.0 async `select()` with WHERE filters — appropriate at this scale
- Route prefix: `/api/alerts` (no version prefix — matches existing pattern in chunk spec)
- Static `/rules` routes registered BEFORE `/{alert_id}/read` to prevent path collision (FastAPI Static Route Before Path Param pattern — seen 4x)
- `alert_id` typed as `int` (BigInteger PK) so literal "rules" string is never captured
- §20.4 envelope: plain dict return for list endpoint
- mark-read: select by id + is_deleted==False, 404 if missing, set is_read=True, commit

## Wiki Patterns Applied
- [FastAPI Static Route Before Path Param] — /rules routes registered before /{alert_id}/read
- [Conftest Integration Marker Trap] — unit tests in tests/routes/, integration in tests/api/
- [AsyncMock Context Manager Pattern] — mock __aenter__/__aexit__ as AsyncMock for session
- [FastAPI Dependency Patch Gotcha] — use dependency_overrides[get_db], not just service mocks
- [ORM Model __new__ Trap] — use MagicMock(spec=AtlasAlert) not direct construction in tests
- [Decimal Not Float] — rs_at_alert field is Decimal

## Existing Code Being Reused
- `backend/db/session.py` → `get_db` dependency + `async_session_factory`
- `backend/db/models.py` → `AtlasAlert` ORM model (already exists at line 390)
- Pattern from `backend/routes/watchlists.py` for session usage
- Pattern from `tests/routes/test_watchlists.py` for mock test structure

## Edge Cases
- NULLs: symbol, instrument_id, alert_type, message, metadata_json, rs_at_alert can all be NULL
- is_deleted soft-delete: always filter `AtlasAlert.is_deleted == False`
- alert_id 999999 → 404 (required by punch list)
- unread=true filter: `.where(AtlasAlert.is_read == False)`
- source filter: `.where(AtlasAlert.source == source)` only when source is not None

## Expected Runtime
- List endpoint: <10ms on t3.large (simple indexed filter on small table)
- Mark-read: <20ms (single row by PK)

## Files to Create/Modify
1. `backend/models/alert.py` — Pydantic v2 response/request models
2. `backend/routes/alerts.py` — 4 routes
3. `backend/main.py` — add alerts router
4. `tests/routes/test_alerts.py` — unit tests (mocked)
5. `tests/api/test_alerts.py` — integration tests (live backend)
