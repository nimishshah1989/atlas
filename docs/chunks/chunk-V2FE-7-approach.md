# V2FE-7 Approach: MF Rank page data wiring

## Actual data scale
- No DB queries required — this is a frontend-only wiring chunk
- mf-rank.html is 670 lines with a 176-line inline script block (lines 468-644)
- No new tables, no schema changes

## Wiki patterns checked
1. **inline-script-to-iife-asset-defer** (PROMOTED 3x, V2FE-3+4+5) — Extract inline `<script>` to `assets/mf-rank.js` as IIFE, replace with 3 deferred `<script src=... defer>` tags
2. **void-sentinel-regex-parser-dom** (PROMOTED 14x) — Two sentinel zones in mf-rank.html: top DP COMPONENT SLOTS (lines 221-229) and ATLAS-SENTINELS-V2 block (lines 647-668). Tests must assert "at-least-one carries data-endpoint", never `[0]`.

## Chosen approach

### Step 1: Add data-endpoint attrs
Wire 7 elements with data-endpoint/data-params/data-data-class attrs:
- `[data-component=regime-banner]` (line 222) → `/api/v1/stocks/breadth`
- `[data-component=signal-strip]` div (line 223) → `/api/v1/stocks/breadth`
- `[data-component=interpretation-sidecar]` (line 226) → `data-v2-derived="true"` (client-derived, NO endpoint)
- `<aside data-block=filter-rail>` (line 322) → `/api/v1/mf/categories` + `/api/v1/mf/universe` facets
- `<div data-block=rank-table>` (line 355) → `/api/v1/query/template` with `mf_rank_composite`
- `<pre data-role=formula>` (line 432) → `data-v2-static="true"` (static, NO endpoint)
- `<footer class="methodology-footer">` (line 459, the first/real footer) → `/api/v1/system/data-health`

### Step 2: Extract inline script to mf-rank.js
- Create `frontend/mockups/assets/mf-rank.js` as IIFE
- Include all helper functions from original inline script
- Add `initFilterRail()` for filter-rail interaction (re-fires loadBlock on filter change)
- Add `loadSparklines()` for batched sparkline loading (single POST with mstar_ids array, N+1 guard)
- Add fixture fetch with API-first pattern + fallback error message

### Step 3: Replace inline `<script>` block with 3 deferred tags
Following exact V2FE convention from breadth.js / stock-detail.js precedent.

## Existing code being reused
- Pattern from `breadth.js`, `stock-detail.js`, `explore-country.js` for IIFE structure
- Test pattern from `test_breadth_bindings.py` for AttrCollector/HTMLParser approach

## Edge cases
- Two sentinel zones — void sentinels at top (lines 221-228) and ATLAS-SENTINELS-V2 block at bottom (lines 647-668). The real methodology footer at line 459 is the one to wire; the hidden ones at lines 646+663 must NOT receive data-endpoint.
- `[data-role=formula]` must explicitly have NO data-endpoint (static content)
- `[data-component=interpretation-sidecar]` must explicitly have NO data-endpoint (client-derived)
- Filter-rail re-fires loadBlock — guarded with `if (typeof window.loadBlock === 'function')`
- Sparkline N+1 guard — single POST with mstar_ids array, not N individual calls

## Expected runtime
- Pure frontend file edits — no backend calls, no DB
- Tests: < 2 seconds (pure HTML parsing)

## Exit criteria
1. `grep -c "data-endpoint" frontend/mockups/mf-rank.html` returns ≥5
2. `pytest tests/unit/v2fe/test_mf_rank_bindings.py -v` passes ≥6 tests
3. `[data-block=rank-table]` has `data-endpoint="/api/v1/query/template"` with `mf_rank_composite`
4. `footer.methodology-footer` has `data-endpoint="/api/v1/system/data-health"`
5. `[data-role=formula]` has no `data-endpoint`
