# Chunk V6T-3 Approach: TVConvictionPanel + DeepDivePanel wiring

## Summary
Frontend-only chunk. No backend changes. Wire `pillar_3` (PillarExternal) from `ConvictionPillars`
into a new `TVConvictionPanel` component displayed in the `DeepDivePanel` render tree.

## Data scale
No data fetched — this chunk reads a field already present in `/api/stocks/{symbol}` JSON response.
No DB queries, no row count considerations.

## Approach

### Why this is frontend-only
Backend already exposes `pillar_3` via `GET /api/stocks/{symbol}`. The `ConvictionPillars`
TypeScript interface in `api.ts` does not yet include `pillar_3`. The `DeepDivePanel` does not
render it. This chunk closes that gap.

### Files changed
1. `frontend/src/lib/api.ts` — add optional `pillar_3` field to `ConvictionPillars` interface
2. `frontend/src/lib/tv.ts` — NEW: `classifyTvScore()` utility, `TvChip`/`TvLabel` types
3. `frontend/src/components/deepdive/TVConvictionPanel.tsx` — NEW: renders 3 TV TA rows
4. `frontend/src/components/DeepDivePanel.tsx` — add import + render `<TVConvictionPanel />`
5. `frontend/tests/e2e/v6t-tv-panel.spec.ts` — NEW: Playwright E2E smoke test

### Wiki patterns checked
- [Fault-Tolerant Panel Isolation](wiki/patterns/fault-tolerant-panel-isolation.md) — component
  shows "TV data unavailable" when `tv_ta` is null; not an error state
- [Plain Dict §20.4 Envelope for Near-Realtime Routes](wiki/patterns/plain-dict-envelope-external-routes.md)
  — TV TA data arrives as `Record<string, number | string | null>` (opaque dict); typed narrowly
  with string-key access, not a strict Pydantic schema
- [External Pillar Partial-Data Flag](wiki/staging/external-pillar-partial-data-flag.md) — 
  backend already sets partial_data on meta; frontend shows graceful "unavailable" fallback

### Existing code reused
- `DeepDivePanel.tsx` render structure (space-y-4 layout, already has ConvictionPillars slot)
- `ConvictionPillars` interface in `api.ts` (appending, not replacing)

### Edge cases
- `pillar_3` is optional (`?`) and nullable (`| null`). Both states → "unavailable" fallback.
- `tv_ta` dict keys may not include `Recommend.All` / `Recommend.MA` / `Recommend.Other` — handled
  by `.get(key)` returning `undefined`, which `classifyTvScore` treats as null → shows "—"
- Score value could be a string from external API — `typeof raw === "number"` guard handles it
- `Number.isFinite` guard prevents ±Infinity passing through

### Score classification thresholds
Matches TradingView's own bands: ≥0.5 STRONG_BUY, ≥0.1 BUY, >-0.1 NEUTRAL, >-0.5 SELL, else STRONG_SELL

### Expected build time
`npm run build`: ~30s on t3.large (existing baseline). No new deps added.

### Verification steps
1. `npm run build` — exit 0
2. `npm run lint` — clean
