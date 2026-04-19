# V2FE-3 Approach: explore-country.html Data Wiring

## Summary
Pure HTML attribute injection + JS extraction chunk. No backend changes needed (all API endpoints already exist from V2FE-1/1a/1b).

## Data Scale
Not applicable — this is a static HTML mockup wiring chunk. No DB queries.

## Chosen Approach
1. Targeted Edit calls on explore-country.html (1204 lines) using exact string matching
2. Create frontend/mockups/assets/explore-country.js (new file, IIFE wrapper)
3. Replace inline `<script>` block with three `<script defer src="...">` tags
4. Create tests/unit/v2fe/test_explore_country_bindings.py with 15 binding tests

## Wiki Patterns Checked
- **void-sentinel-regex-parser-dom** (11x): grep every data-component occurrence in TWO zones (DP COMPONENT SLOTS top-of-body AND criteria-gate sentinels near </body>). V2+ must grep all occurrences before editing.
- **static-html-mockup-react-spec** (7x): V2 phase extends contract with data-endpoint/data-params/data-fixture/data-data-class binding attrs; mockup becomes authoritative DOM-slot→endpoint map.

## Existing Code Being Reused
- All API endpoints already exist: /api/v1/stocks/breadth, /api/v1/global/flows, /api/v1/sectors/rrg, /api/v1/global/events, /api/v1/stocks/breadth/zone-events, /api/v1/stocks/breadth/divergences, /api/v1/derivatives/summary, /api/v1/macros/yield-curve, /api/v1/query
- Pattern mirrors V2FE-2 (today.html wiring): same attribute naming convention

## File Structure of explore-country.html
- Lines 367-387: DP COMPONENT SLOTS (void sentinels top-of-main)
- Lines 576-638: Breadth panel with 3x deriv-cards + dual-axis-overlay chart
- Lines 640-655: signal-playback compact + rec-slot
- Line 658: derivatives section (#sect-deriv)
- Line 717: rates section (#sect-rates)
- Line 824: INR/FX section (#sect-fx)
- Line 860: flows section (data-block="flows", #sect-flows)
- Line 939: sectors-rrg section (data-block="sectors-rrg", #sect-sectors)
- Lines 1141-1157: </main> + inline script block
- Lines 1180-1193: structural sentinels near </body> (regime-banner, signal-strip, four-universal-benchmarks)

## Edits Plan (19 total)
1. void regime-banner (line 368): add endpoint+params+data-class
2. void signal-strip (line 369): add endpoint+fixture+data-class
3. void dual-axis-overlay (line 372): add endpoint+params+fixture+data-class
4. void interpretation-sidecar (line 373): add data-v2-derived="true"
5. structural four-universal-benchmarks wrapper (line 1188): add endpoint+params+data-class
6. void signal-playback compact (line 383): add data-v2-derived="true"
7. first rec-slot (line 384): add data-v2-deferred="true"
8. 3x breadth-kpi deriv-cards (lines 578-592): add data-block+endpoint+params+fixture+data-class
9. structural dual-axis-overlay chart (line 594): add endpoint+params+fixture+data-class
10. structural signal-playback compact (line 640): add data-v2-derived="true"
11. second rec-slot (line 653): add data-v2-deferred="true"
12. derivatives section (line 658): add block+endpoint+data-class+sparse
13. rates section (line 717): add block+endpoint+params+data-class
14. INR/FX section (line 824): add block+endpoint+params+data-class+sparse
15. flows section (line 860): add endpoint+params+data-class
16. sectors-rrg section (line 939): add endpoint+params+fixture+data-class
17. Add 3x new void sentinels before </main> (signal-history-table, divergences-block, events-overlay)
18. structural regime-banner (line 1180): add endpoint+params+data-class
19. structural signal-strip (line 1181): add endpoint+fixture+data-class

## Edge Cases
- The 3 breadth-kpi deriv-cards have identical opening tags (`<div class="deriv-card">`), must use sufficient surrounding context for unique matching
- signal-playback compact appears at line 383 (void) AND line 640 (structural) — edit both separately with unique context
- rec-slot appears at line 384 (void) AND line 653 (structural) — edit both separately
- The four-universal-benchmarks wrapper at line 1188 is a div (structural sentinel), the span chips in the main body (lines 375-378) are NOT edited per spec

## Expected Runtime
< 1 second (pure file reads + edits, no network)
