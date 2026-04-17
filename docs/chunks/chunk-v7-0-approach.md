---
chunk: V7-0
project: ATLAS
date: 2026-04-17
status: in_progress
---

# V7-0 Approach: Gold RS Foundation

## Actual Data Scale

From `pg_stat_user_tables`:
- `de_global_price_daily`: ~261k rows (parent, but via `de_global_prices` synonym)
- GLD (USD): 2,584 rows, 2016-01-04 to 2026-04-14
- GOLDBEES (INR): 4,093 rows, 2010-01-03 to 2026-03-30
- Both series fit in memory easily; Python-side alignment is fine for 252-day windows

## Chosen Approach

- SQL for data fetching (date-range filtered), Python for arithmetic (series is ≤252 rows)
- `compute_rs_vs_gold`: pure Python Decimal arithmetic, no pandas (series too small)
- Redis read-through: 15-min TTL, DB upsert on compute
- All RS arithmetic in `Decimal(str(value))` — no float intermediary

## Wiki Patterns Checked

- `decimal-not-float` — str->Decimal at every boundary, especially DB rows (asyncpg returns Decimal for Numeric columns, but force str() conversion anyway)
- `idempotent-upsert` — INSERT ... ON CONFLICT DO UPDATE on `uq_gold_rs_cache`
- `conftest-integration-marker-trap` — tests go to `tests/unit/gold_rs/`, not `tests/api/`

## Existing Code Reused

- `backend/services/derived_signals.py` C-DER-1 gold RS query uses same `de_global_price_daily` table with `ticker='GLD'` — V7-0 generalizes it
- `backend/db/models.py` BigInteger PK pattern (AtlasAgentScore) reused
- Alembic version header from `i8j9k0l1m2n3_v6_1_tv_cache_watchlist.py`

## Edge Cases

- NULL price: `close` column might be NULL for some rows → skip (filter in SQL)
- Insufficient aligned dates: if intersection < n+1 points → return None (never 0/NaN)
- Gold data staleness: GOLDBEES max is 2026-03-30 (>2 days ago) → STALE if used as sole series
- Exact zero RS values → strict > / < → FRAGILE (not AMPLIFIES_*)
- Redis connection failure → swallowed, fall through to DB

## Expected Runtime on t3.large

- GLD query: <5ms (2,584 rows with date filter)
- compute_rs_vs_gold: <1ms (pure Python, ≤252 aligned points)
- Redis get/set: <2ms
- DB upsert: <10ms
- Total per entity: ~20ms

## Migration

- File: `alembic/versions/j7k8l9m0n1o2_v7_0_atlas_gold_rs_cache.py`
- down_revision = "i8j9k0l1m2n3"
- UNIQUE(entity_type, entity_id, date) + 3 standalone indexes
