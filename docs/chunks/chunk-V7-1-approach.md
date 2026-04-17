# Chunk V7-1 Approach: ETF Universe API

## Data scale
No direct row-count check needed — this chunk reads from `de_etf_master`, `de_etf_technical_daily`, `de_rs_scores`, and `atlas_gold_rs_cache`. Scale is unknown until runtime; DISTINCT ON wrappers are mandatory per wiki pattern.

## Chosen approach
- Thin JIP helper module (`jip_helpers.py`) wraps all `de_*` reads with DISTINCT ON
- Service layer (`etf_service.py`) with in-process 5-min TTL cache (keyed by country|benchmark|includes|as_of)
- Route (`etf.py`) is a thin shim — no SQL in route handlers
- All DB fetches within a single session are sequential (not concurrent) per spec note — SQLAlchemy async sessions cannot multiplex concurrent queries

## Wiki patterns checked
- **DISTINCT ON Latest-Row-Per-Key** — used in all three de_* helper functions
- **Conftest Integration Marker Trap** — tests go in `tests/routes/test_etf_universe.py` NOT `tests/api/`
- **FastAPI Dependency Patch Gotcha** — must patch `get_db` even when service fully mocked
- **Zero-Value Truthiness Trap** — use `is not None` not `if value:` for financial fields
- **Schemas File Line Budget** — ETF models go in new `backend/models/etf.py` (schemas.py at 498L, near limit)

## Existing code reused
- `backend/models/schemas.py` — imports `Quadrant`, `ResponseMeta`
- `backend/db/session.py` — `get_db` dependency
- `backend/services/gold_rs_cache.py` — pattern reference only; gold_rs fetched directly via SQL

## Edge cases
- NULLs: `_safe_decimal` handles None, NaN, Infinity, empty string
- Empty masters: return `([], False)` immediately  
- Missing gold_rs/rs/tech rows: opt-in blocks are `None` when ticker not in result dict
- Expense ratio = 0.0: handled by `is not None` (not truthiness)
- Invalid include param: 400 with INVALID_INCLUDE error envelope
- JIP down: 503 with JIP_UNAVAILABLE envelope
- Concurrent cache requests: asyncio.Lock per cache_key (double-check after lock)

## Files to create/modify
- `backend/services/jip_helpers.py` (new)
- `backend/models/etf.py` (new)
- `backend/services/etf_service.py` (new)
- `backend/routes/etf.py` (new)
- `tests/routes/test_etf_universe.py` (new — NOT tests/api/)
- `backend/main.py` (modify — add etf router)

## Expected runtime
All queries use DISTINCT ON with 5-second statement_timeout; in-process cache serves subsequent requests in <1ms. Cold path expected <200ms on t3.large assuming JIP indexes exist.
