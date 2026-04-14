# V2-9 Approach: Pro shell MF deep-dive panel

## Date: 2026-04-14

## Data scale
- No new DB queries in this chunk — all backend endpoints already exist (V2-5/V2-7)
- This chunk is frontend-only + new test file

## Approach

### Punch list 1: Refactor MFDeepDive.tsx to single fetch
The current component makes 3 parallel API calls (getMfFundDeepDive + getMfHoldings + getMfSectors).
The deep-dive response already contains top_holdings, sector_exposure, and weighted_technicals.
Strategy: remove getMfHoldings + getMfSectors calls and state variables. Replace SectorExposureTable
(which needs full sector array) with inline summary using sector_exposure from deep-dive.
TopHoldingsTable already prefers topHoldings when non-empty — pass top_holdings from dive.

### Punch list 2: RS history sparkline (async load)
New component MFNAVSparkline.tsx — loads getMfNavHistory after main dive loads.
Uses a separate useEffect that fires when `dive` becomes non-null.
SVG sparkline: normalize values to 0-100 height, polyline, teal #1D9E75.
Shows skeleton while loading, renders nothing on error.

### Punch list 3: Overlap widget
New component MFOverlapWidget.tsx — text input for second fund mstar_id + Compare button.
Calls getMfOverlap on submit, renders overlap_pct headline + common_holdings table.
Sort by Math.min(parseFloat(weight_a), parseFloat(weight_b)) descending.

### API additions
api-mf.ts: add getMfOverlap(fundA, fundB) function + MFOverlapHolding + MFOverlapResponse types.
api.ts: re-export the new function + types.

### Tests
tests/api/test_mf_deep_dive_panel.py — 5 tests verifying:
1. Deep-dive has all pillar data (single-fetch sufficient)
2. NAV history returns points array
3. Overlap returns common_holdings with weight_a/weight_b
4. Overlap requires exactly 2 funds (returns 400)
5. Deep-dive top_holdings has symbol + weight_pct

## Wiki patterns checked
- Decimal Not Float: all financial values string in API responses
- FastAPI Dependency Patch Gotcha: must patch get_db even when service fully mocked
- Conftest Integration Marker Trap: tests in tests/api/ — no conftest auto-marks issue
- AsyncMock Context Manager Pattern: mock JIPDataService methods as AsyncMock

## Existing code reused
- _make_fund_row helper pattern from test_mf_page_api.py
- _make_freshness, _patch_svc patterns adapted for deep-dive/overlap/nav tests
- getMfNavHistory already exists in api-mf.ts (just need to use it in sparkline)
- SectorExposureTable component stays but is no longer called (replaced with inline summary)

## Edge cases
- Empty NAV history: sparkline renders nothing
- Overlap with no common holdings: shows "No common holdings" message
- Overlap API error: shows error state, not crash
- NULLs in weight_a/weight_b: parseFloat("") returns NaN → guarded with fallback

## Expected runtime
- Frontend build: N/A (no build step in tests)
- pytest: <5s (pure mock tests, no DB)
- No t3.large compute concerns — frontend-only + unit tests
