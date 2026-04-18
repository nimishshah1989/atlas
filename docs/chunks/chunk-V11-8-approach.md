---
chunk: V11-8
project: atlas
date: 2026-04-18
---

# V11-8 Approach: Insider + Bulk/Block Deal Surfaces

## Actual data scale

DATABASE_URL not set in shell, so live row counts unavailable. Based on project memory
note `project_jip_empty_tables.md`: many JIP tables are sparse/empty (de_fo_bhavcopy=0,
de_global_price_daily USDINR=3 rows). Insider, bulk, and block deal tables are likely
similarly sparse — the inline health gate with 503 degradation handles this case
explicitly without crashing.

## Chosen approach

Inline DB Health Gate pattern (patterns/inline-db-health-gate.md) — exactly matches
the V11-4 derivatives pattern. One service class `JIPInsiderService` with three
check_*_health() methods. Routes are direct: check health, 503 if unhealthy, fetch if
healthy.

No Alembic migration needed — all three tables (de_insider_trades, de_bulk_deals,
de_block_deals) are JIP de_* read-only tables.

## Wiki patterns used

1. `inline-db-health-gate` (PROMOTED 2x) — COUNT(*) + MAX(date) → 503 {"reason": "..."}
2. `pydantic-v2-meta-serializer` (PROMOTED) — model_serializer emits _meta key
3. `conftest-integration-marker-trap` (PROMOTED) — tests in tests/routes/ not tests/api/
4. `asyncmock-context-manager-pattern` (PROMOTED) — __aenter__/__aexit__ as AsyncMock
5. `zero-value-truthiness-trap` (PROMOTED) — `is not None` checks for all financial fields

## Existing code being reused

- Pattern: `backend/clients/jip_derivatives_service.py` — identical structure
- Pattern: `backend/models/derivatives.py` — identical model structure
- Pattern: `backend/routes/derivatives.py` — identical route structure
- Pattern: `tests/routes/test_derivatives.py` — identical test structure
- `backend/db/session.py` — async_session_factory, get_db
- `backend/main.py` — will add insider router after derivatives.router

## Edge cases

- NULLs: all financial fields (value_inr, avg_price, trade_price, post_holding_pct)
  are Optional with `is not None` checks (not truthiness)
- Empty tables: health gate returns 503 before any data fetch
- Stale tables: lag > _STALENESS_DAYS=5 returns 503
- Zero-value trap: Decimal("0") is not None — must use `is not None` checks
- Symbol case: always `symbol.upper()` for JIP queries, and in meta response
- Date range validation: from_date > to_date → HTTP 400 INVALID_DATE_RANGE

## Files to create/modify

- backend/clients/jip_insider_service.py (new)
- backend/models/insider.py (new)
- backend/routes/insider.py (new)
- tests/routes/test_insider.py (new)
- backend/main.py (modify: add insider router)

## Expected runtime

Service queries are simple COUNT(*) + MAX(date) health checks plus bounded
date-range SELECT. On t3.large: <50ms per query, <200ms total per request.
24 unit tests with mocked DB: <5 seconds total test run.
