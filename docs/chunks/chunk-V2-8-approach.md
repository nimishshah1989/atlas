# Chunk V2-8 Approach: Pro shell MF page

## Summary
Frontend-only chunk. All backend MF routes (V2-1..V2-7) are already wired and returning real data. This chunk adds an MF tab to the existing ATLAS Pro shell (`frontend/src/app/page.tsx`) with a broad→category→fund→deep-dive drill-down flow.

## Data Scale
No new data layer. All data comes from existing backend API routes at `/api/v1/mf/`. No DB writes, no Alembic migrations.

## Chosen Approach

### Frontend architecture
- Extend the existing `View` union type in `page.tsx` with 3 MF view states: `mf-categories`, `mf-funds`, `mf-deep-dive`
- Add tab switcher at page level: "Market" (existing equity) vs "Mutual Funds" (new)
- MF landing view: MFCategoryTable (top-level rollup by category)
- Category click → MFUniverseTree (funds list filtered by category, from /universe response)
- Fund click → MFDeepDive (single fund deep-dive)
- MFFlowsPanel: sidebar component showing flows data alongside category table

### Component pattern
Follows established pattern from SectorTable/StockTable/DeepDivePanel:
- `useEffect` + `useState` for data fetching
- Skeleton loading (animate-pulse) not spinners
- Graceful degradation on error

### Wiki patterns checked
- `formatting.ts` already has all helpers needed (formatCurrency, formatPercent, formatIndianNumber, signColor, quadrantColor, quadrantBg)
- API client pattern: `fetchApi<T>()` with TypeScript interfaces
- Component pattern: matches SectorTable/DeepDivePanel structure exactly
- No new npm deps needed (recharts already installed for charts)

### Existing code being reused
- `format.ts` — all formatting helpers, no new ones needed
- `api.ts` — fetchApi helper, adding MF fetch functions
- `page.tsx` — View union type extended, tab switcher added
- Skeleton loading pattern from DeepDivePanel

## Files in scope (per chunk spec)
1. `frontend/src/lib/api.ts` — add MF types + fetch functions
2. `frontend/src/components/mf/MFCategoryTable.tsx` — new
3. `frontend/src/components/mf/MFUniverseTree.tsx` — new
4. `frontend/src/components/mf/MFFlowsPanel.tsx` — new
5. `frontend/src/components/mf/MFDeepDive.tsx` — new
6. `frontend/src/app/page.tsx` — modify to add MF tab/views
7. `tests/api/test_mf_page_api.py` — new, backend API shape tests

## Edge Cases
- NULL financial fields: all format helpers handle null → "—"
- Empty fund lists: gracefully show "No funds in this category"
- Empty flows: show "No flow data available"
- Missing NAV: show "—" via formatCurrency
- Decimal values from API come as strings — use parseFloat() before formatting
- staleness EXPIRED: show warning badge with data_as_of date

## TypeScript Types
API returns Decimal as strings, dates as "YYYY-MM-DD" strings. All TypeScript interface fields that are Decimal use `string | null`. Date fields use `string`.

## Expected Runtime
- Page load: 2 API calls in parallel (categories + flows) → ~100-300ms on t3.large
- Category drill: 1 API call (universe) → ~200-500ms
- Fund deep-dive: 1 API call → ~100-200ms

## UI Layout
- Tab switcher in header ("Market | Mutual Funds")
- MF categories view: 3-col layout (category table L span, flows panel R span — mirrors equity sectors/decisions layout)
- Fund list: full-width table with back button (mirrors StockTable)
- Deep-dive: full-width panel (mirrors DeepDivePanel)
