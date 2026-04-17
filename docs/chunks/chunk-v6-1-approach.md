---
chunk: V6-1
project: atlas
date: 2026-04-17
title: V6 DB migration — atlas_tv_cache + atlas_watchlists (tv_synced) + atlas_alerts
---

# Approach

## Data scale
- atlas_watchlists: small (< 100 rows). Adding column with server_default is safe zero-downtime.
- atlas_tv_cache: new table, starts empty.
- No table scans needed; pure DDL migration.

## Chosen approach
- Alembic migration file: `i8j9k0l1m2n3_v6_1_tv_cache_watchlist.py`
  - Creates `atlas_tv_cache` with composite PK (symbol, data_type, interval)
  - Adds `tv_synced BOOLEAN DEFAULT FALSE` to `atlas_watchlists`
  - `atlas_alerts` already has full correct schema — no changes
- ORM: Add `AtlasTvCache` model to `backend/db/models.py`; add `tv_synced` field to `AtlasWatchlist`
- Pydantic: New `backend/models/tv.py` with `TvCacheEntry` and `TvCacheUpsertRequest`
- Tests: `tests/unit/test_v6_1_schema.py` — ORM model inspection, Pydantic validation, AST scans

## Wiki patterns checked
- `bug-patterns/alembic-mypy-attr-defined.md` — `# type: ignore[attr-defined]` on alembic imports
- `patterns/ast-scanned-anti-pattern-detection.md` — AST scan for float/print in production code

## Existing code reused
- `backend/db/models.py` patterns: `mapped_column()`, `Mapped[T]`, `func.now()`, JSONB
- Same migration revision chain as existing v5 files

## Edge cases
- Composite PK: `atlas_tv_cache(symbol, data_type, interval)` — interval defaults to 'none' so NULL never occurs
- `JSONB` column `data`: Decimal-in-JSONB trap avoided (no Decimal in this table)
- `tv_synced` server_default="false" ensures existing rows get FALSE without needing backfill

## Expected runtime
- Migration: < 1s (no data migration, small table ALTER)
- Tests: < 5s (pure unit, no DB)
