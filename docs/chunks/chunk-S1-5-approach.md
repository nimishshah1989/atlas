# Chunk S1-5 Approach — MF Detail Page (/funds/[id])

## Data scale
This is a pure frontend chunk — no new backend tables, no data queries.
Frontend only touches React components + tests.

## Chosen approach

Pure React/SWR port following the S1-4 (Stock Detail) pattern exactly:
- Page: `"use client"`, `use(params)` from React, `useState` for category + fundName, `useEffect` for title
- Components: `useAtlasData<T>` + `DataBlock` wrapper for all GET endpoints
- Recharts: `LineChart` for NavChartBlock + RollingAlphaBetaBlock, `PieChart` for SectorAllocationBlock
- Tooltip formatter: `(value: any, name: any)` with eslint-disable comment (pattern confirmed x2)
- AUM: `₹${formatIndianNumber(aum)}` — never raw numbers
- NO "Atlas Verdict", NO "HOLD / ADD ON DIPS"

## Wiki patterns checked
- `recharts-tooltip-formatter-any-type` (2x promoted) — use `(value: any, name: any)` + eslint-disable
- `useatlasdata-haskey-vs-empty-array` (2x promoted) — inline override for zero-row arrays
- `useatlasdata-get-post-split` — all endpoints here are GET-only, no POST needed
- `static-html-mockup-react-spec` — pattern is React port of V2FE-6 mf-detail.html spec

## Existing code being reused
- `src/hooks/useAtlasData.ts` — unchanged SWR wrapper
- `src/components/ui/{DataBlock,LoadingSkeleton,EmptyState,StaleWarning,ErrorBanner}` — unchanged
- `src/lib/format.ts` — `formatCurrency`, `formatPercent`, `formatIndianNumber`, `signColor`, `formatDate`, `formatDecimal`
- S1-4 page.tsx pattern — exact same structure (use(params), useState, useEffect for title)
- S1-2/S1-3 Recharts patterns — LineChart + PieChart with eslint-disable tooltip

## Files to create
1. `src/app/funds/[id]/page.tsx`
2. `src/components/funds/FundHeroBlock.tsx`
3. `src/components/funds/ReturnsBlock.tsx`
4. `src/components/funds/NavChartBlock.tsx`
5. `src/components/funds/AlphaRiskBlock.tsx`
6. `src/components/funds/RollingAlphaBetaBlock.tsx`
7. `src/components/funds/HoldingsBlock.tsx`
8. `src/components/funds/WeightedTechnicalsBlock.tsx`
9. `src/components/funds/SectorAllocationBlock.tsx`
10. `src/components/funds/SuitabilityBlock.tsx`
11. `tests/unit/funds/test_mf_detail_page.test.tsx`

## Edge cases
- AUM null: `formatIndianNumber(0)` returns "0" — guard with `data?.aum != null`
- NAV null: `formatCurrency(null)` returns "—" — safe
- Empty holdings array: inline `effectiveState` override for zero-row case
- Empty sectors: same pattern for PieChart
- `onNameLoaded` is optional prop — use `onNameLoaded?.(name)` syntax
- `use(params)` requires Promise<{id}> interface, same as S1-4's Promise<{symbol}>

## Expected runtime
Pure frontend build/test — `npm test` runs in ~30s, `npm run build` in ~60s on t3.large.
No DB queries, no Python, no backend changes.
