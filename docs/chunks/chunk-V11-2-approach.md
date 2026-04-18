---
chunk: V11-2
project: atlas
date: 2026-04-18
---

# V11-2 Approach: Adjustment-factor consumption — `?adjusted=true` on price routes

## Actual data scale

- `de_corporate_actions`: 14,964 rows (verified via COUNT(*))
- `de_instrument`: 2,743 rows
- `de_equity_ohlcv`: 0 rows in pg_stat but partitioned — parent table, actual data in year partitions
- `de_adjustment_factors_daily`: 0 rows — spec says DO NOT use this table

### Action type breakdown
- dividend: 7,138 | other: 6,202 | split: 510 | bonus: 488 | rights: 418 | merger: 118 | buyback: 90
- Non-null, non-zero adj_factor: 904 rows (only split/bonus/rights have meaningful adj_factors)

### Schema verified
Columns match spec exactly: id, instrument_id, ex_date, action_type, dividend_type, ratio_from, ratio_to, cash_value, new_instrument_id, adj_factor, notes, created_at, updated_at

### RELIANCE bonus 2024-10-28 quirk
adj_factor=1.0 (identity, no adjustment). Two duplicate rows. The DISTINCT ON in SQL deduplicate these. Product of 1.0 * 1.0 = 1.0 — no adjustment applied. This is correct per spec.

## Chosen approach

### Scale decision
Per-symbol corporate actions: at most ~10-20 rows after filter (split/bonus/rights + non-null adj_factor). Well under 1K. Python dict computation is appropriate.

Adjustment computation: pure Python/Decimal suffix product over at most ~20 events per symbol. No SQL aggregation needed — volume is trivial.

### Architecture
1. `backend/services/adjustment_service.py` — pure computation, no IO, all Decimal
2. `backend/clients/jip_equity_service.py` — add `get_corporate_actions()` method
3. `backend/models/instruments.py` — Pydantic v2 models with model_serializer for _meta
4. `backend/routes/instruments.py` — FastAPI route with soft health degradation
5. `backend/main.py` — register instruments.router
6. `tests/services/test_adjustment_service.py` + `tests/routes/test_instruments.py`

### Health gate: SOFT (fail-open)
- Check data-health.json for corporate_actions domain failures
- If failing: return raw prices + meta.warnings populated
- If health file missing: fail-open (no warnings, proceed normally)
- NEVER raise 503

### Pydantic _meta pattern
Use model_serializer to emit `_meta` (Pydantic v2 rejects leading underscore fields).
Pattern already confirmed in ETF routes: `backend/models/etf.py`.

## Wiki patterns checked
- pydantic-v2-meta-serializer (PROMOTED) — standard for all §20.4 envelope routes
- conftest-integration-marker-trap (PROMOTED) — route tests go in tests/routes/
- fastapi-dependency-patch-gotcha (PROMOTED) — must patch get_db even with mocked service
- decimal-not-float (PROMOTED) — Decimal(str(val)) for all financial arithmetic

## Existing code being reused
- `backend/clients/jip_equity_service.py::get_chart_data()` — returns list[dict] with OHLCV
- `backend/db/session.py::async_session_factory` — session factory
- `backend/models/etf.py` — model_serializer pattern reference

## Edge cases handled
1. NULL adj_factor: skipped (filter in both SQL and Python)
2. adj_factor=0: skipped (prevents division-by-zero in inverse, also product-chain safe)
3. adj_factor=1.0 (RELIANCE quirk): passes through, product stays 1.0 — no adjustment
4. Duplicate rows on same ex_date: DISTINCT ON in SQL, Python dedup multiplies factors
5. Empty corporate actions: schedule=[], apply_adjustment returns prices unchanged (factor=1)
6. None OHLC values: preserved as None in output
7. Prices after all events: factor=Decimal("1") (no future events)
8. Prices before all events: factor = full suffix product (all events after)
9. Health file missing: fail-open, no warnings
10. Symbol not found: 404 with structured error envelope
11. from_date > to_date: 400 with INVALID_DATE_RANGE

## Expected runtime on t3.large
- Corporate actions fetch: ~10ms (14,964 rows, single symbol = ~10-20 rows returned)
- OHLCV fetch: ~30-50ms (up to 365 rows for 1Y range)
- Adjustment computation: <1ms (pure Python, <20 events)
- Total: <100ms warm, <200ms cold
