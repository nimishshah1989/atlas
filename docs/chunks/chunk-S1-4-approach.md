---
chunk: S1-4
project: atlas
date: 2026-04-19
---

# S1-4 Approach: Stock Detail /stocks/[symbol]

## Data scale
No new DB queries in this chunk — all data fetched via existing API endpoints at runtime. No table migration.

## Chosen approach
Port stock-detail.html mockup to React/SWR following established S1-0..S1-3 patterns:
- 1 page component + 8 sub-components + 1 test file
- All GET endpoints → `useAtlasData<T>` hook
- All components wrap render in `<DataBlock state={state} ...>`
- Empty-array override pattern (`effectiveState`) for components returning `{divergences: []}` or `{records: []}` — per wiki `useatlasdata-haskey-vs-empty-array` (confirmed S1-1, S1-3)
- Recharts Tooltip formatter uses `(value: any, name: any)` with `typeof` guard — per wiki `recharts-tooltip-formatter-any-type` (confirmed S1-2, S1-3)
- Next.js App Router params via `use(params)` — per staging `nextjs16-params-as-promise`
- Hero block loads first; calls `onSectorLoaded(sector)` on settle; PeersBlock SWR key = null until sector available

## Wiki patterns checked
- `recharts-tooltip-formatter-any-type` (1x S1-2) — ComposedChart Tooltip: `(value: any, name: any)` + eslint-disable + typeof guard
- `useatlasdata-haskey-vs-empty-array` (1x S1-1, confirmed S1-3) — empty array override at component level
- `nextjs16-params-as-promise` (staging 1x) — `use(params)` in client component
- `static-html-mockup-react-spec` (13x) — stock-detail.html is the spec; wired in V2FE-5

## Existing code reused
- `src/lib/api.ts` — apiFetch, AtlasMeta, AtlasApiError
- `src/hooks/useAtlasData.ts` — SWR hook
- `src/components/ui/DataBlock.tsx` — state machine renderer
- `src/lib/format.ts` — formatCurrency, formatPercent, formatDate
- Breadth `OscillatorPanel.tsx` as reference for ComposedChart dual-sub-chart pattern

## Edge cases
- `sector` from hero can be null; PeersBlock renders "loading sector…" message when null
- All numeric fields may be null; use `?? null` and `?? "—"` guards throughout
- `useAtlasData` hasData() key-presence gap: override with `effectiveState` when array is empty
- HeroData may return sector in `data.sector` or `data._meta.sector` — check both

## Expected runtime
Import tests only (no render calls) — < 2s for `npm test -- --testPathPatterns stocks`
