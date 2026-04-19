---
chunk: S1-0
project: atlas
date: 2026-04-19
---

# S1-0 Approach: Shared infrastructure — SWR, apiFetch, useAtlasData, UI primitives, format utils

## Summary

Pure frontend infrastructure chunk. No backend, no database, no migrations.

## Data scale

Not applicable — this chunk is purely TypeScript/React. No DB queries required.

## Chosen approach

### 1. SWR install
Standard npm install. SWR is the React data-fetching library specified. No alternatives considered (spec mandates it).

### 2. CSS tokens
Add missing tokens to the `:root` block of globals.css. Existing vars (--background, --foreground, --teal, --teal-light) are preserved; new design-token vars appended.

### 3. apiFetch in api.ts
Appended after existing code. Key differences from existing fetchApi:
- Uses `?? "http://localhost:8000"` (not empty string)
- Has 8-second AbortController timeout
- Throws typed AtlasApiError instead of generic Error
- Returns `{ data: T; _meta: AtlasMeta }` envelope

### 4. useAtlasData hook
SWR-based hook with:
- Key = `[endpoint, JSON.stringify(params)]` for cache isolation
- State machine: loading → ready | stale | empty | error
- `hasData()` checks `.records`, `.series`, `.divergences` arrays matching atlas-data.js logic
- STALENESS_THRESHOLDS exported as const (exact values from atlas-states.js)
- `dataClass` option enables staleness checking against threshold

### 5. UI primitives
Five components under `src/components/ui/`:
- `LoadingSkeleton`: skeleton-block with 3 lines
- `EmptyState`: ∅ icon + text, role="status"
- `StaleWarning`: amber banner, data-staleness-banner, role="alert"
- `ErrorBanner`: red card, role="alert"
- `DataBlock`: orchestrates state → component mapping
- `index.ts`: re-exports all

No "use client" on pure presentational components (they receive props only). DataBlock passes state down.

### 6. format.ts additions
Three new pure functions appended:
- `formatDate`: Intl.DateTimeFormat with IST timezone → DD-MMM-YYYY
- `formatSign`: +/-/"" for null-safe sign
- `formatStaleness`: seconds → human readable (m/h/d)

### 7. Tests
No Jest installed yet → set up Jest + @testing-library/react + @testing-library/jest-dom.
- jest.config.js with ts-jest + jsdom environment
- babel.config.js for JSX transform
- tests/unit/ui/test_ui_primitives.test.tsx: DataBlock + ErrorBanner + StaleWarning + formatDate
- tests/unit/hooks/test_useAtlasData.test.ts: STALENESS_THRESHOLDS constants

## Wiki patterns checked
- static-html-mockup-react-spec (S1 chunk context)
- fault-tolerant-panel-isolation (each DataBlock is independent)

## Existing code reused
- `frontend/src/lib/api.ts` — AUGMENTED (append only)
- `frontend/src/lib/format.ts` — AUGMENTED (append only)
- `frontend/src/app/globals.css` — AUGMENTED (new tokens in :root)

## Edge cases
- `apiFetch` with zero params: no query string appended
- `formatDate(null)`: returns "—"
- `hasData`: non-object input returns false
- `computeState`: no swrData + no error + not validating → "loading" (initial render)
- `dataClass` undefined: staleness check skipped entirely

## Expected runtime
Pure frontend — no server load. npm install ~5s, build ~30s.
