---
chunk: S1-2
project: atlas
date: 2026-04-19
---

# S1-2 Approach: Explore Country Page

## Data scale
- Frontend-only chunk. No DB queries.
- Endpoints fetched via useAtlasData (SWR GET). No data scale concerns.

## Chosen approach
- Mirror exact pattern from S1-1 (pulse/page.tsx → explore/country/page.tsx)
- 9 new components in src/components/explore/
- Recharts for all charts (LineChart for yield curve, BarChart for flows, ScatterChart for RRG)
- DataBlock wraps all components; state="empty" auto-renders EmptyState (no special handling needed for sparse endpoints)
- useAtlasData returns state="empty" when meta.insufficient_data===true — DataBlock auto-renders EmptyState

## Wiki patterns checked
- static-html-mockup-react-spec (13x PROMOTED) — mockup is spec, components mirror DOM blocks
- useatlasdata-haskey-vs-empty-array (S1-1 staging) — inline emptiness override for zero-length arrays
- useatlasdata-get-post-split (S1-1 staging) — all these endpoints are GET, no POST needed

## Existing code being reused
- useAtlasData hook (src/hooks/useAtlasData.ts)
- DataBlock, EmptyState, LoadingSkeleton, StaleWarning, ErrorBanner (src/components/ui/)
- format.ts: formatCurrency, formatPercent, quadrantColor, quadrantBg, formatDate
- Pulse page pattern (src/app/pulse/page.tsx)

## Edge cases
- DerivativesBlock: sparse endpoint (de_fo_bhavcopy=0 rows) → useAtlasData returns state="empty" automatically → DataBlock shows EmptyState. No ErrorBanner.
- InrChartBlock: sparse (USDINR=X has only 3 rows) → same auto-empty path.
- SectorsRRGBlock: empty data → inline emptiness check needed (data?.series may be empty array)
- FlowsBlock: insufficient_data → EmptyState via DataBlock
- ZoneEventsTable: empty records → inline check
- DivergencesCountryBlock: empty divergences → inline check

## Expected runtime
- Build: ~30s. Tests: ~5s. Frontend-only, no backend.
