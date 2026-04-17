---
chunk: C-DER-1
project: atlas
date: 2026-04-17
status: in-progress
---

# C-DER-1 Approach: Gold RS + Piotroski Derived Signals

## Actual Data Scale (from pg_stat_user_tables)

| Table | Row Count |
|---|---|
| de_equity_technical_daily | 3,693,512 |
| de_global_price_daily | 261,018 |
| de_equity_fundamentals_history | 55,140 |
| de_equity_fundamentals | 2,272 |

All queries use WHERE instrument_id = :instrument_id or WHERE ticker = 'GLD', so they are single-entity point lookups. With LIMIT 80 added, these are trivially fast even on the 3.7M row table.

## Schema Verified (Spec-to-Schema Drift Check)

All columns confirmed to exist via information_schema:
- de_equity_technical_daily: `close_adj` (numeric), `date`, `instrument_id` — CONFIRMED
- de_global_price_daily: `close` (numeric), `date`, `ticker` — CONFIRMED
- de_equity_fundamentals_history: `fiscal_period_end`, `net_profit_cr`, `cfo_cr`, `opm_pct`, `revenue_cr`, `total_assets_cr`, `borrowings_cr`, `equity_capital_cr`, `reserves_cr`, `period_type` — ALL CONFIRMED
- de_equity_fundamentals: `roe_pct`, `debt_to_equity`, `instrument_id` — CONFIRMED

## Chosen Approach

Pure read-only query-time derivations. No new DB tables. Two async functions in `backend/services/derived_signals.py`:

1. **Gold RS**: Two SQL queries (stock prices + GLD prices), compute ratio via Decimal arithmetic. Single entity, LIMIT 80, no full-table scans.
2. **Piotroski**: Two SQL queries (history rows + point-in-time fundamentals), 9 boolean checks, score 0-9.

Both called concurrently via `asyncio.gather` with isolated sessions (Isolated-Session Parallel Gather pattern — asyncpg can't multiplex).

## Wiki Patterns Applied

1. **Isolated-Session Parallel Gather** — Per-query AsyncSession + asyncio.gather for parallel deep-dive; asyncpg multiplexing guard
2. **Zero-Value Truthiness Trap** — Use `is not None` everywhere for financial fields (0 is valid)
3. **FastAPI Dependency Patch Gotcha** — Patch `get_db` in route tests even when service is mocked
4. **Decimal Not Float** — str->Decimal conversion for all financial values
5. **Spec-to-Schema Drift Verification** — Verified all column names against information_schema before writing SQL

## Existing Code Being Reused

- `backend/db/session.py`: `async_session_factory`, `get_db`
- `backend/models/schemas.py`: `StockDeepDive` (adding fields), `BaseModel`, `Enum`
- `backend/routes/stocks.py`: `get_stock_deep_dive` (adding signal gather after conviction)
- `tests/routes/test_stock_conviction.py`: Pattern for route tests with `app.dependency_overrides[get_db]`
- `sqlalchemy.text()` pattern already used throughout codebase

## Edge Cases

- **GLD < 30 rows**: Return GoldRS sentinel with NEUTRAL signal (not None) — per spec
- **Stock < 30 rows**: Return None
- **denominator == 0** (gold_return == -1): Return None (division guard)
- **0 history rows for Piotroski**: Return None
- **1 history row**: F3/F5/F7/F8/F9 all False (no prior year)
- **NULL financial fields**: Each F-check uses `is not None` guard (Zero-Value Truthiness Trap)
- **total_equity == 0**: Return None from `_total_equity()` helper (division guard)
- **Signal exceptions**: `asyncio.gather(return_exceptions=True)` + isinstance check → null field in response, never 500

## Expected Runtime

- Gold RS: ~5ms (single-entity point lookup, LIMIT 80, indexed on instrument_id)
- Piotroski: ~5ms (LIMIT 3 from 55K rows, indexed on instrument_id)
- Both concurrent via asyncio.gather: ~5-10ms total added to deep-dive

## Files Created/Modified

- CREATE: `backend/services/derived_signals.py`
- CREATE: `tests/services/test_derived_signals.py`
- CREATE: `tests/routes/test_stock_derived_signals.py`
- MODIFY: `backend/models/schemas.py` (4 new models + StockDeepDive fields + __all__)
- MODIFY: `backend/routes/stocks.py` (imports + gather block + StockDeepDive constructor)
