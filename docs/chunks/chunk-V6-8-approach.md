---
chunk: V6-8
project: ATLAS
date: 2026-04-17
status: in-progress
---

# V6-8 Approach: Pro shell /pro/alerts + /pro/watchlists pages

## Summary
Pure frontend chunk — backend API is already fully implemented in V6-6 and V6-7.
No DB changes, no Alembic migrations, no backend route changes.

## Scale context
Not applicable — no database queries. Frontend reads from existing API.

## Files to create
1. `frontend/src/lib/api-alerts.ts` — TypeScript client for alerts API
2. `frontend/src/lib/api-watchlists.ts` — TypeScript client for watchlists API
3. `frontend/src/app/pro/alerts/page.tsx` — Alerts page (client component)
4. `frontend/src/app/pro/watchlists/page.tsx` — Watchlists page (client component)
5. `tests/api/test_v6_8_pages_api.py` — Integration tests for API shape

## Approach

### API client pattern
- Mirrors `frontend/src/lib/api-global.ts`: `const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""`
- Generic `fetchApi<T>()` helper with error extraction
- All Decimal backend values arrive as strings (FastAPI serializes Decimal → str)
- No `float` types in TypeScript

### Page shell pattern
- Matches `/pro/global/page.tsx` and `/pro/intelligence/page.tsx`
- Sticky header with breadcrumb, ATLAS Pro branding, max-w-[1600px]
- White bg, `#1D9E75` teal accent, `border-[#e4e4e8]`
- Skeleton loading (animate-pulse), not spinners

### Alerts page
- Load on mount via `useEffect` + `getAlerts()`
- Filter state: source (select), unread-only (checkbox toggle)
- Re-fetch when filter changes
- Source badge color: teal=rs_analyzer, purple=sector_analyst, amber=mf_decisions, gray=others
- Unread: teal left border; read: gray left border
- Mark-read: optimistic local state update

### Watchlists page
- Load on mount via `useEffect` + `getWatchlists()`
- Sync-to-TV: per-card loading state, inline success/error message
- New watchlist form: name input + symbols textarea (comma-separated)
- Delete: calls `deleteWatchlist(id)`, filters out from local state on 204

### Tests (integration markers auto-applied by conftest.py)
- All tests in `tests/api/` → auto-marked as integration
- Use `api_client` fixture (skips if backend unreachable)
- Tests assert response shape, not data values
- 404 tests use sentinel IDs (999999, 00000000-0000-0000-0000-000000000000)

## Wiki patterns checked
- `Fault-Tolerant Panel Isolation` — each page/section has own error state
- `Plain Dict §20.4 Envelope` — already handled by backend, frontend just reads `data` key
- `Defensive Or-Empty Extraction` — backend concern, already done

## Edge cases
- Empty watchlists list: show empty state message
- Symbol list > 5: show first 5 + "+N more" badge
- TV sync failure: show inline error, don't remove card
- Network errors on mark-read: show inline error, don't update is_read
- NULLs for optional fields (symbol, alert_type, rs_at_alert, etc.)

## Expected runtime
- `npm run build`: ~60s on t3.large
- `python -m py_compile tests/api/test_v6_8_pages_api.py`: <1s
