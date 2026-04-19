---
chunk: S1-6
project: ATLAS
date: 2026-04-19
status: in-progress
---

# S1-6 Approach: MF Rank Page (/funds/rank)

## Scope
Pure frontend chunk — 5 source files + 1 test file. No backend changes.

## Data scale
No DB access needed; this is a frontend component chunk. Backend API
`/api/v1/query/template` with template `mf_rank_composite` returns the rank records.

## Chosen approach
- SWR 2.3.6 direct in RankTable (POST-body key pattern, not useAtlasData which only handles GET)
- SWR key = `["/api/v1/query/template", JSON.stringify({template, params})]` — changes when filters change
- Filter state in page.tsx via useState (not URL)
- Sparkline data bundled in rank response (no N+1 calls)

## Wiki patterns checked
- S1 shared-infra conventions (SWR 2.3.6, apiFetch GET/POST split)
- S1-2 two-idiom empty-state rule (`_meta.insufficient_data` vs `{x:[]}` override)

## Existing code reused
- `frontend/src/components/pulse/RegimeBanner.tsx` — re-exported as RegimeBannerRank
- `frontend/src/lib/format.ts` — formatPercent, formatDecimal, formatCurrency
- Test patterns from `frontend/tests/unit/funds/test_mf_detail_page.test.tsx`

## Files created
1. `frontend/src/app/funds/rank/page.tsx` — "use client" page with filter state
2. `frontend/src/components/rank/FilterRail.tsx` — aside with fieldset/legend filter groups
3. `frontend/src/components/rank/SparklineCell.tsx` — mini Recharts LineChart (60x24px)
4. `frontend/src/components/rank/RegimeBannerRank.tsx` — re-export wrapper
5. `frontend/src/components/rank/RankTable.tsx` — sortable table, CSV export, SWR POST
6. `frontend/tests/unit/rank/test_mf_rank_page.test.tsx` — 10 tests

## Edge cases handled
- NULL scores: display "—" via formatDecimal/formatPercent null guards
- Empty sparkline: SparklineCell returns "—" span if data null/empty or <2 non-null points
- Error state: RankTable shows error message
- Loading state: skeleton rows
- Empty filter result: "No funds match the selected filters" message
- CSV export: URL.createObjectURL + anchor click pattern

## Expected runtime
Frontend build: ~30s. Tests: ~5s.
