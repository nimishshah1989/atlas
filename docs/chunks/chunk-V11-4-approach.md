# Chunk V11-4 Approach: Derivatives + India VIX Consumption Routes

## Data Scale (actual)
- `de_fo_bhavcopy`: 0 rows (empty) — F&O data not yet ingested
- `de_fo_summary`: 0 rows (empty) — pre-computed PCR table not yet ingested
- `de_participant_oi`: 1360 rows — available but not used by this chunk
- `de_macro_values`: 115481 rows — INDIAVIX ticker has only 2 rows (2026-04-13..2026-04-14)
- DATABASE_URL not available in this shell env; row counts sourced from spec/known data

## Chosen Approach

### Architecture
- **Pure SQL via SQLAlchemy async text()**: All queries in JIPDerivativesService; route handlers are thin wrappers
- **Inline health gate**: Each route does a COUNT(*) + MAX(date) freshness check inline (no file-based dependency), returning 503 with `{"reason": "..."}` when tables are empty/stale
- **Staleness threshold**: 5 calendar days (accommodates weekends + holidays)
- **VIX staleness**: With only 2 rows dated 2026-04-13..2026-04-14 and today being 2026-04-18, the lag is 4 days — technically healthy, so VIX route will return 200 with 2 data points. F&O routes will return 503 (empty tables).

### Route registration
- `GET /api/derivatives/pcr/{symbol}` — MUST be registered BEFORE `/{symbol}/oi` to prevent FastAPI treating "pcr" as a symbol param (FastAPI static-before-param pattern)
- Both derivatives routes share the `check_fo_health` path
- VIX route lives in separate `backend/routes/macros.py`

### Data models
- Separate `backend/models/derivatives.py` for PCR, OI, VIX models (schemas-file-line-budget pattern)
- All Pydantic v2 models use `model_serializer` to emit `_meta` key (pydantic-v2-meta-serializer pattern)
- `Decimal` not `float` for all financial values

## Wiki Patterns Applied
- **conftest-integration-marker-trap**: Tests in `tests/routes/` NOT `tests/api/`
- **asyncmock-context-manager-pattern**: Mock `__aenter__`/`__aexit__` as AsyncMock
- **pydantic-v2-meta-serializer**: `model_serializer` emits `_meta` key
- **FastAPI static-before-param** (fastapi-static-route-before-path-param): `/pcr/{symbol}` registered before `/{symbol}/oi`
- **plain-dict-envelope**: `response_model=None`, returns `dict[str, Any]`

## Existing Code Reused
- `backend/db/session.py` → `async_session_factory`
- Pattern from `backend/routes/instruments.py` for session mock in tests
- Pattern from `tests/routes/test_instruments.py` for test structure

## Edge Cases
- `de_fo_bhavcopy` empty → 503, reason field present, structlog warn
- `de_fo_summary` empty but `de_fo_bhavcopy` has data → fallback CTE computation
- VIX date=2026-04-14, today=2026-04-18 → lag=4 days < 5 → healthy (will return data)
- `NULL` in pcr_oi/pcr_volume handled with `Optional[Decimal]`
- `NULL` in change_in_oi → `int(r["change_in_oi"])` cast (safe since SQL SUM returns 0 for no rows)
- `pcr_series` with 0 rows but table healthy → returns 200 with empty data list
- `data_as_of = max(dates)` with empty list → `None` (explicit `default=None`)

## Expected Runtime
- Health check query: < 5ms (COUNT(*) + MAX on indexed date column)
- PCR series: < 50ms (date-range filtered query on empty/small table)
- OI buildup: < 50ms same
- VIX series: < 20ms (2 rows, ticker='INDIAVIX' filtered)
- On t3.large: all routes well within 500ms budget
