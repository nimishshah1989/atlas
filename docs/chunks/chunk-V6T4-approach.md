---
chunk: V6T-4
project: atlas
date: 2026-04-17
---

# V6T-4 Approach: TV Column on Market Tab + Watchlist Refresh TV Signals

## Data scale
- atlas_tv_cache: cache table, per-symbol rows, expected < 1K in dev. Bulk query via SQLAlchemy IN clause — fine.
- No financial calculations in this chunk. No Decimal concerns except no floats in response types (all strings/ints/None).

## Approach

### Backend
1. Add GET /ta/bulk BEFORE /ta/{symbol} in tv.py router — critical per FastAPI Static Route Before Path Param bug pattern.
2. Pure cache lookup only — no bridge calls, no background refresh. SQLAlchemy IN query on AtlasTvCache.
3. Add tv_ta raw field to /ta/{symbol} response (additive, strict superset).
4. Return plain dict (§20.4 pattern) — no Pydantic response_model.

### Frontend
1. TvChip.tsx — new component using classifyTvScore from lib/tv.ts (existing function, never re-implement).
2. StockTable.tsx — add tvMap state, fetch getTvBulkCache after universe loads, TV column header + sort.
3. StockTableRow.tsx — add tvScore prop + TvChip TD.
4. api.ts — add getTvBulkCache + getTvTa functions + types.
5. api-watchlists.ts — remove SyncTv* exports and syncWatchlistToTv().
6. watchlists/page.tsx — replace Sync-to-TV button with Refresh TV signals button using Promise.allSettled.

## Wiki patterns checked
- [FastAPI Static Route Before Path Param] — bulk route MUST be above /{symbol}
- [Plain Dict §20.4 Envelope for Near-Realtime Routes] — return dict[str, Any] directly
- [Domain Score Classifier Helper] — TvChip imports classifyTvScore, never re-implements
- [Conftest Integration Marker Trap] — tests go in tests/routes/ not tests/api/

## Existing code reused
- backend/db/tv_models.py AtlasTvCache ORM model
- backend/routes/tv.py _build_meta(), _extract_ta_fields()
- frontend/src/lib/tv.ts classifyTvScore()
- tests/routes/test_tv_routes.py pattern for ASGITransport + AsyncClient + DB override

## Edge cases
- Empty symbols list: return early with empty items
- Symbols > 500: 400 error
- Uncached symbols: tv_ta=null, fetched_at=null (not skipped)
- Null tv_data in cache: tv_ta=None in response
- All TV fetches rejected in watchlist: show error banner, tvScores Map still populated with nulls

## Expected runtime
- Bulk cache query: < 10ms for < 500 symbols (indexed PK)
- No bridge calls in bulk route
