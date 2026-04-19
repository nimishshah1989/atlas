# Chunk V2FE-6 Approach — MF Detail Hub-and-Spoke Page Data Wiring

## Actual data scale
No new database tables or data operations in this chunk. Pure frontend wiring.

## Files in scope
1. `frontend/mockups/mf-detail.html` — 1415 lines, add data-endpoint binding attrs
2. `frontend/mockups/assets/atlas-data.js` — ~360 lines, extend _substituteTemplateVars + reloadUniverseBlocks
3. `frontend/mockups/assets/mf-detail.js` — create new IIFE
4. `tests/unit/v2fe/test_mf_detail_bindings.py` — create new, ≥12 tests

## Chosen approach
This is structurally identical to V2FE-5 (stock-detail.html). No inline script extraction needed — mf-detail.html has NO inline `<script>` block (only two external deferred scripts at lines 139-140). So only step 2 of the inline-script-to-iife-asset-defer pattern applies: add the mf-detail.js IIFE file + deferred script tag.

## Wiki patterns checked
- `void-sentinel-regex-parser-dom` (13x PROMOTED) — sentinels in TWO zones (DP COMPONENT SLOTS top-of-main AND ATLAS-SENTINELS-V2 block near </body>). The bottom sentinels at lines 1395-1403 carry `data-component="regime-banner"` and `data-component="signal-strip"` — those must also get data-endpoint added per the spec.
- `inline-script-to-iife-asset-defer` (2x PROMOTED) — no inline script in mf-detail.html so only new mf-detail.js needed.
- `static-html-mockup-react-spec` (9x PROMOTED) — V2 binding contract: data-endpoint + data-params + data-fixture + data-data-class.

## Existing code reused
- `atlas-data.js _substituteTemplateVars()` — already handles `${symbol}` and `${sector}`. Just add `${mstar_id}` and `${category}` vars.
- Test pattern from `tests/unit/v2fe/test_stock_detail_bindings.py` — identical AttrCollector + pytest fixture structure.

## Edge cases
- mf-detail.html has TWO zones with `data-component="regime-banner"` — top (line 175) and bottom (line 1395). Both need data-endpoint attrs per spec items 2 and 12.
- Holdings data-data-class is `holdings` (7d staleness), not `daily_regime` (24h).
- signal-playback compact (data-mode=compact) stays client-side → `data-v2-derived="true"`, no endpoint.
- rec-slots at top (mf-alpha-thesis, mf-risk-flag) and bottom (mf-suitability, mf-playback) all need `data-v2-deferred="true"`.
- The visible [data-block=returns] (line 294) and the sentinel [data-block=returns] (line 193) are separate elements — add data-endpoint to both (spec items 4 and 2).
- The NAV chart container: the `<div class="cw">` at line 297 is the right container, not the SVG itself. Will add data-block="nav-chart" to that div.
- The peer block (line 1261) is a `<div style="background...">` wrapping the ptable — add data-block="peers" + endpoint.
- The suitability div (line 1213, `<div class="cw">`) — add data-block="suitability".
- Sector allocation (spec item 7) — find in or near the weighted-technicals block. The sector signal grid is inside [data-block=weighted-technicals] at line 689 (`<div style="background:var(--bg-surface)...">` wrapping the ssgrid table). Will add a data-block="sector-allocation" wrapper.

## Expected runtime
HTML edits: <5s. No server-side changes. Tests: <2s.

## Exit criterion
grep count of data-endpoint in mf-detail.html must be ≥12. All ≥12 pytest tests pass.
