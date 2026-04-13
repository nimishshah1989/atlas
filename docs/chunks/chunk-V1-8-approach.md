# Chunk V1-8 Approach — Frontend wiring: finding chips + decision card + sector badge + Playwright

## Data scale
No DB queries needed — this is a pure frontend chunk. Backend APIs are already working.

## Approach

### 1. Fix `api.ts` — DecisionSummary type mismatch
The frontend type used `symbol/signal/reason/action` but the backend `DecisionSummary` schema uses `entity/decision_type/rationale/user_action`. Update the TS type to match. Also add `FindingSummary` and `IntelligenceListResponse` types, plus `getFindings()` function.

Backend `DecisionActionRequest` expects `{ action: DecisionAction, note: string | null }`. The existing `actionDecision(id, action, note?)` body already sends `{ action, note }` — keep that.

### 2. Update DecisionPanel.tsx
Map the new field names. Add confidence % and horizon display. Show source_agent if present. Decision type label mapping: `buy_signal → BUY SIGNAL`, `sell_signal → SELL SIGNAL`, etc.

### 3. Create FindingChips.tsx
- Pure client component
- Fetches `/api/v1/intelligence/findings?entity=SYMBOL&limit=10`
- Displays compact chips with finding_type, title, confidence
- Color coding by finding_type (rs_analysis=teal, technical=blue, breadth=amber, etc.)
- Graceful: no findings → render nothing

### 4. Wire FindingChips into DeepDivePanel.tsx
Add `<FindingChips entity={symbol} />` between stock header and RsChart.

### 5. Update fixtures.ts
- Update `DECISIONS_FIXTURE` to match real backend `DecisionSummary` shape
  - Must still work with existing `market-sector-stock.spec.ts` which imports DECISIONS_FIXTURE
  - The existing spec only uses DECISIONS_FIXTURE for page.route() mocking the GET endpoint — it doesn't assert on field values of decisions, just that the panel renders
- Add `FINDINGS_FIXTURE` as `IntelligenceListResponse` with 3 findings for HDFCBANK

### 6. Create `v1-fm-flow.spec.ts`
Comprehensive FM flow test:
- Market overview loads
- Sector table renders with quadrant badges
- Sector click → stock table
- Stock click → deep dive with finding chips
- Decision panel shows with correct badges
- Action buttons work (mock PUT endpoint)
- Back navigation
- lakh/crore formatting verified
- Mock all backend calls via `page.route()`

## Wiki patterns checked
- [Extract Fixtures to Pass File-Size Gate] — keep spec under 500L, fixtures in fixtures.ts
- [Next.js SSR/Browser BACKEND_BASE Split] — API calls from browser use `/api` prefix via NEXT_PUBLIC_API_URL

## Existing code being reused
- `format.ts` — quadrantColor, quadrantBg, formatCurrency
- `fixtures.ts` — STATUS, BREADTH, SECTORS, UNIVERSE, DEEPDIVE, RS_HISTORY, MOVERS fixtures
- Pattern from `market-sector-stock.spec.ts` for page.route() mocking

## Edge cases
- No findings for entity: FindingChips renders nothing (not error)
- Null confidence in finding: show "—" not error
- Null user_action in decision: show pending state
- decision_type is a mixed-case enum (BUY vs buy_signal): label function handles both

## Key constraint
- The existing `market-sector-stock.spec.ts` imports `DECISIONS_FIXTURE` — if we change its type, the TypeScript compiler will catch mismatches. After updating the TS interface, the fixture must conform to the new interface.
- The existing spec only routes DECISIONS_FIXTURE to the mock endpoint, doesn't assert on specific decision field values → safe to change the fixture shape.

## Expected runtime
- `npm test` (jest unit tests): <30s
- `npx playwright test v1-fm-flow.spec.ts`: <60s (browser launch + 8 tests)
- `ruff check`: 0s (no backend changes)
