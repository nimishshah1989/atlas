# Chunk V5-14 Approach — Pro shell /pro/global page

## Summary
Build the `/pro/global` dashboard page in the ATLAS frontend, consuming 5 Global Intelligence API routes from V5-9. Plus a backend pytest smoke test under `tests/frontend/`.

## Data scale
No new DB reads — global intelligence routes already exist (V5-9). This chunk is purely frontend + integration smoke test.

## Chosen approach

### Frontend API client (`frontend/src/lib/api-global.ts`)
- Same `fetchApi<T>` helper pattern as `api-intelligence.ts`
- Types mirror `backend/models/global_intel.py` Pydantic models
- Decimal fields serialized as strings by FastAPI → `string | null` in TS
- Dual-key responses (`data` + legacy key) — frontend uses `??` fallback pattern
- 5 typed functions: `getGlobalBriefing`, `getMacroRatios`, `getGlobalRSHeatmap`, `getGlobalRegime`, `getGlobalPatterns`

### Frontend page (`frontend/src/app/pro/global/page.tsx`)
- `"use client"`, sticky header, breadcrumbs showing "Global"
- 5 independent panels, each with own `useState`/`useEffect` (isolated state)
- Layout: Briefing (full-width top) → Regime + Ratios (2-col) → RS Heatmap (full-width) → Patterns (full-width)
- Each panel: try/catch independent — failure isolated, others continue
- Loading: animate-pulse skeleton, not spinners
- data_as_of: each panel shows `<span className="text-xs text-gray-400">Data as of {date}</span>`
- IST date formatting via `toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })`
- Numbers: `formatCurrency`, `formatDecimal`, `formatPercent`, `formatRs`, `regimeColor`, `signColor` from `@/lib/format`
- Design: white bg, teal accents (#1D9E75), border-[#e4e4e8], desktop-first

### Backend smoke test (`tests/frontend/test_global_page.py`)
- Placed under `tests/frontend/` — conftest will auto-mark as integration
- Uses `httpx.AsyncClient` hitting `http://localhost:8000`
- Tests each endpoint returns 200 + meta structure
- Tests Decimal values are strings (not floats)
- Tests date fields are ISO strings
- Tests panel independence (all 5 endpoints callable independently)

## Wiki patterns checked
- [Dual-Key Model Serializer Compat](patterns/dual-key-model-serializer-compat.md) — frontend uses `??` fallback
- [Conftest Integration Marker Trap](bug-patterns/conftest-integration-marker-trap.md) — place frontend smoke tests in tests/frontend/ with its own conftest

## Existing code reused
- `frontend/src/lib/api-intelligence.ts` — fetchApi pattern
- `frontend/src/lib/format.ts` — formatCurrency, formatDecimal, formatPercent, formatRs, regimeColor, signColor
- `frontend/src/app/pro/intelligence/page.tsx` — page structure, skeleton, card patterns

## Edge cases handled
- briefing/regime/breadth may all be null (empty table) → show "No data available"
- Decimal fields may be null → formatDecimal/formatCurrency handles null → "—"
- `data_as_of` from different sources: briefing.date, regime.date, breadth.date, sparkline dates, _meta.data_as_of
- Empty arrays for ratios/heatmap/patterns → show empty state message
- Network error per panel → show panel-level error, other panels unaffected

## Expected runtime
- Frontend build: existing Next.js, no new deps, ~30s
- Tests: httpx async calls, <5s per endpoint against live backend

## Files in scope
1. `frontend/src/lib/api-global.ts` (new)
2. `frontend/src/app/pro/global/page.tsx` (new)
3. `tests/frontend/test_global_page.py` (new)
4. `tests/frontend/__init__.py` (new)
5. `tests/frontend/conftest.py` (new)
