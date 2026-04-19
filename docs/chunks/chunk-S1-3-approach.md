---
chunk: S1-3
project: ATLAS
date: 2026-04-19
title: Breadth Terminal (/breadth page)
---

# Approach: S1-3 Breadth Terminal

## Data scale
Not a data-engineering chunk. Pure frontend React port. No DB queries needed.
Breadth endpoints already exist on backend: `/api/v1/stocks/breadth` and
`/api/v1/stocks/breadth/zone-events` and `/api/v1/stocks/breadth/divergences`.

## Chosen approach
React/SWR port of `breadth.html` → `/breadth` Next.js page. Following the exact
same pattern established in S1-1 (Pulse) and S1-2 (Explore Country).

### Component structure
- `frontend/src/app/breadth/page.tsx` — "use client" page with universe/indicator state
- `frontend/src/components/breadth/UniverseSelector.tsx` — presentational pill group
- `frontend/src/components/breadth/IndicatorSelector.tsx` — presentational pill group
- `frontend/src/components/breadth/HeroKPIRow.tsx` — fetches breadth counts (useAtlasData)
- `frontend/src/components/breadth/OscillatorPanel.tsx` — ComposedChart dual-axis (Recharts)
- `frontend/src/components/breadth/ZoneLabelsBlock.tsx` — zone summary (useAtlasData)
- `frontend/src/components/breadth/SignalHistoryBlock.tsx` — sortable table (useAtlasData)
- `frontend/src/components/breadth/DivergencesBlock.tsx` — divergences list (useAtlasData)
- `frontend/src/components/breadth/ConvictionHaloBlock.tsx` — presentational EmptyState only

## Wiki patterns checked
1. `static-html-mockup-react-spec` — React port follows DOM spec from mockup
2. `recharts-tooltip-formatter-any-type` — use `(value: any, name: any)` in Recharts Tooltip
3. `useatlasdata-haskey-vs-empty-array` — DivergencesBlock needs effectiveState override
4. `useatlasdata-get-post-split` — all endpoints here are GET-only, use useAtlasData

## Existing code being reused
- `useAtlasData` hook from `@/hooks/useAtlasData`
- `DataBlock` wrapper from `@/components/ui/DataBlock`
- `EmptyState` from `@/components/ui/EmptyState`
- Recharts (already installed: ^3.8.1)
- Pattern from `DivergencesCountryBlock.tsx` for effectiveState guard
- Pattern from `YieldCurveBlock.tsx` for Recharts tooltip formatter typing

## Key decisions
1. `"use client"` only on hook-using components (HeroKPIRow, OscillatorPanel,
   ZoneLabelsBlock, SignalHistoryBlock, DivergencesBlock). NOT on UniverseSelector,
   IndicatorSelector, ConvictionHaloBlock.
2. OscillatorPanel uses ComposedChart with dual Y-axes (left=count 0-500, right=index_close)
3. Recharts Tooltip: `(value: any, name: any)` pattern per wiki staging entry
4. DivergencesBlock: effectiveState override (same as DivergencesCountryBlock)
5. Sort state in SignalHistoryBlock: local React useState, no external dep

## Edge cases
- Empty series array: ComposedChart renders empty (no crash)
- NULL index_close: YAxis right-axis simply won't have points
- Empty zone events: effectiveState → "empty", EmptyState renders
- SWR key uniqueness: params JSON.stringify ensures universe changes revalidate

## Expected runtime
Build: ~30s (Next.js incremental). Tests: <5s (9 jest unit tests, import-only).
