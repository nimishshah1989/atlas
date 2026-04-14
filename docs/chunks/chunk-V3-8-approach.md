# Chunk V3-8 Approach: Pro shell /pro/simulate Simulation Lab page

## Data scale
Frontend-only chunk. No DB queries needed. Consuming existing backend API (V3-1..V3-7 DONE).

## Chosen approach
- Follow the exact `api-mf.ts` pattern for the API client (fetchApi helper + TypeScript interfaces)
- Follow existing `page.tsx` tab pattern for adding "Simulate" tab
- Use Recharts AreaChart for portfolio value chart (already in package.json)
- 3-step form builder with local state only
- Financial values from API come as strings (FastAPI serializes Decimal as str) — parse to Number only for display/chart

## Wiki patterns checked
- Decimal Not Float: frontend parses Decimal strings to Number only at display boundary
- Dashboard-Backend Name Drift: typed interfaces mirror backend Pydantic models exactly

## Existing code reused
- `frontend/src/lib/format.ts` — formatCurrency, formatPercent, signColor, formatDecimal
- `frontend/src/lib/api-mf.ts` — fetchApi pattern
- `frontend/src/app/page.tsx` — tab switcher pattern
- `frontend/src/components/mf/MFCategoryTable.tsx` — table pattern with sort

## Edge cases
- Simulation run can take several seconds — loading state required
- API may return 400 (invalid params) or 501 (not implemented signal) — user-friendly error display
- Empty saved simulations list — empty state message
- daily_values may be empty on error — chart handles empty array gracefully
- Transaction log may be long — scrollable table

## Files to create/modify
1. `frontend/src/lib/api-simulate.ts` — API client with types
2. `frontend/src/components/simulate/SimulationBuilder.tsx` — 3-step form
3. `frontend/src/components/simulate/SimulationResults.tsx` — results display
4. `frontend/src/components/simulate/SavedSimulations.tsx` — saved list
5. `frontend/src/app/page.tsx` — add Simulate tab
6. `tests/api/test_simulate_page_api.py` — backend API shape tests

## Expected runtime
All frontend builds happen in browser. Backend tests run in ~2s on t3.large.
API test file uses mocked services (no real DB), so test suite remains fast.

## Risks
- Recharts AreaChart type-safety with date strings on x-axis (need formatter)
- 3-step form state management complexity — use simple useState array
