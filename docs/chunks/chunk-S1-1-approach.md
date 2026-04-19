---
chunk: S1-1
project: atlas
date: 2026-04-19
status: in-progress
---

# Chunk S1-1 — Pulse Page React Port

## Scope
Port today.html → `/pulse` Next.js page with 9 sub-components and 1 test file.

## Data Scale
No DB queries needed — this is a pure frontend chunk. All data comes from
existing backend endpoints already built in V2FE-1/V2FE-1a:
- /api/v1/stocks/breadth (breadth + regime)
- /api/v1/stocks/breadth/divergences
- /api/v1/query/template (POST)
- /api/v1/global/events

## Approach

### Component pattern
All GET-based components use `useAtlasData<T>` from S1-0 (SWR wrapper).
All POST-based components (SectorBoard, MoverStrip, FundStrip) use
useState + useEffect with raw fetch — apiFetch is GET-only.

### State machine
`useAtlasData` returns `{data, meta, state, error, isLoading, mutate}`.
`state` is `"loading"|"ready"|"stale"|"empty"|"error"`.
All components wrap output in `<DataBlock state={state}>`.

### POST helper pattern
```tsx
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const [state, setState] = useState<"loading"|"ready"|"empty"|"error">("loading");
const [data, setData] = useState<RowType[]>([]);
useEffect(() => {
  fetch(`${API_BASE}/api/v1/query/template`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({template: "...", params: {...}}),
  })
    .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
    .then(json => {
      const records = json?.data?.records ?? json?.records ?? [];
      if (records.length === 0) setState("empty");
      else { setData(records); setState("ready"); }
    })
    .catch(e => { setErrorMsg(String(e)); setState("error"); });
}, []);
```

### Wiki patterns checked
- static-html-mockup-react-spec: mockup is the DOM spec; React port preserves structure
- fault-tolerant-panel-isolation: each component fetches independently
- inline-script-to-iife-asset-defer: N/A (React not mockup)
- jest-separate-babel-config-for-nextjs-swc: use babel.config.jest.js (already set up)

### Existing code reused
- `src/hooks/useAtlasData.ts` — SWR wrapper
- `src/lib/format.ts` — formatCurrency, formatPercent, formatDecimal, formatDate, formatSign, regimeColor, signColor
- `src/components/ui/DataBlock.tsx`, EmptyState, LoadingSkeleton, StaleWarning, ErrorBanner

### Edge cases
- NULL breadth fields — all formatX functions handle null → "—"
- Empty divergences array → EmptyState shown inside DivergencesBlock
- POST failures → error state shown via ErrorBanner pattern
- Deferred blocks (four-decision-card) → EmptyState only, no API call
- SectorBoard sort state — client-side sort with useState, no fetch on sort change

### TypeScript constraints
- No `any` types — use `unknown` or specific interfaces
- All components: `"use client"` directive
- All exports: default export

### Tests
8 tests in `tests/unit/pulse/test_pulse_page.test.tsx`.
Mock SWR and global fetch. Test only that components are function exports.
Pattern: same as existing unit tests — jsdom environment, babel-jest transform.

### Expected runtime
Pure frontend build: instantaneous. No DB. No Python. No migrations.
