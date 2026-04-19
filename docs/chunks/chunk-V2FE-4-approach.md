---
chunk: V2FE-4
project: atlas
date: 2026-04-19
title: Breadth Terminal page data wiring
---

## Data scale

No DB queries needed — pure frontend HTML/JS wiring. No table scans required.

## Approach

Pure HTML + JS wiring task. No backend changes. Three deliverables:

### 1. breadth.html — add data-endpoint attrs

Current state: 0 data-endpoint attributes. Target: ≥9.

Blocks to wire (from spec §3.6 table):
- `.hero-card` × 3 → `/api/v1/stocks/breadth` with universe=${universe}, range=1d, include=counts
- `[data-component=regime-banner]` (visible at line 347, NOT the sentinel at 1315) → `/api/v1/stocks/breadth`
- `[data-component=signal-strip]` (div at line 348, NOT span at 349) → `/api/v1/stocks/breadth`
- `[data-block=breadth-kpi]` × 3 → `/api/v1/stocks/breadth`
- `[data-block=oscillator]` (div at line 481) → `/api/v1/stocks/breadth`, range=5y, include=index_close,events
- `[data-block=oscillator]` ROC panel (line 545) → data-v2-derived="true", no second endpoint
- `[data-block=zone-reference]` (line 570) → `/api/v1/stocks/breadth`, range=5y, include=zone_summary
- `[data-block=signal-history]` (line 605) → `/api/v1/stocks/breadth/zone-events`, range=5y
- `[data-component=divergences-block]` → NEW element added to right-rail area → `/api/v1/stocks/breadth/divergences`
- `[data-block=signal-playback]` / `#signal-playback` → data-v2-derived="true" only, no data-endpoint (client-side)
- `footer[data-role=methodology]` (line 947) → `/api/v1/system/data-health`

Key DOM facts from reading the file:
- Line 347: `<div data-as-of="2026-04-17" data-component="regime-banner" data-regime="risk-on">` — DP COMPONENT SLOT (top of body, no endpoint yet)
- Line 348: `<div data-as-of="2026-04-17" data-component="signal-strip">` — DP COMPONENT SLOT
- Line 481: `<div class="chart-with-events" data-as-of="2026-04-17" data-block="oscillator" data-type="quantitative">` — primary oscillator
- Line 545: `<div class="oscillator-panel" data-block="oscillator">` — ROC panel (derived)
- Line 570: `<div class="zone-labels" data-block="zone-reference">` — zone reference
- Line 605: `<div class="signal-history" data-block="signal-history">` — signal history
- Line 632: `<div class="playback-wrap" id="signal-playback">` — simulator (client-side only)
- Line 947: `<footer class="methodology-footer" data-role="methodology">` — methodology footer
- Line 1315: sentinel regime-banner with display:none — do NOT add data-endpoint here
- Lines 393, 404, 415: three `.hero-card` divs

The DP COMPONENT SLOTS at lines 347-348 are void-sentinel elements per the void-sentinel pattern. The spec says to wire them. Since they already carry `data-component`, we add `data-endpoint` to them directly. BUT the spec note says "add to visible one at line 347". Lines 347-348 ARE the DP slots (top of body). The visible regime-banner is implied by those slots. We add to the slots.

Wait - re-reading: the DP COMPONENT SLOTS at lines 347-348 carry no endpoint. The pattern from V2FE-2 (today.html) shows adding data-endpoint directly to those void-sentinel elements. The test checks "at-least-one element with data-component=regime-banner carries data-endpoint".

### 2. atlas-data.js — template substitution

Extend `loadBlock()` to substitute `${universe}` and `${indicator}` in the params string before JSON.parse. Also add `reloadUniverseBlocks()` function.

### 3. breadth.js — extract inline script

Move lines 956-1294 (`<script>(function(){...}());</script>`) to `frontend/mockups/assets/breadth.js`. Replace with thin bootstrap + deferred script tags.

The bootstrap replaces the inline script with:
```html
<script>
window.__breadthUniverse = window.__breadthUniverse || 'nifty500';
window.__breadthIndicator = window.__breadthIndicator || 'ema21';
</script>
<script defer src="assets/atlas-states.js"></script>
<script defer src="assets/atlas-data.js"></script>
<script defer src="assets/breadth.js"></script>
```

The extracted `breadth.js` is the full IIFE from the inline script.

### 4. Tests

`tests/unit/v2fe/test_breadth_bindings.py` — 10 tests using BeautifulSoup html.parser pattern from test_today_bindings.py.

## Wiki patterns checked

- `void-sentinel-regex-parser-dom` (12x) — binding tests must assert "at-least-one element with the block attribute carries data-endpoint", never `[0]`. Two sentinel zones exist.
- `static-html-mockup-react-spec` (8x) — V2 phase: data-endpoint/data-params/data-fixture/data-data-class as authoritative DOM-slot→endpoint map.
- `inline-script-to-iife-asset-defer` (1x staging) — V2 wiring chunks extract inline script to IIFE + deferred tags.

## Existing code being reused

- `tests/unit/v2fe/test_today_bindings.py` — exact same AttrCollector/HTMLParser pattern
- `frontend/mockups/assets/atlas-data.js` — extending loadBlock() with template substitution

## Edge cases

- The divergences-block doesn't exist yet → add void sentinel AND a visible structural element in the right-rail area near signal history
- Signal-playback stays client-side → data-v2-derived="true" + TODO V3 comment, no data-endpoint
- ROC oscillator panel (second data-block=oscillator) → data-v2-derived="true", no second endpoint (spec says "client derives 5-day ROC from ema21_count series")
- Sentinel regime-banner at line 1315 (display:none) → must NOT get data-endpoint
- The DP COMPONENT SLOT void sentinel for regime-banner at line 347 already has data-component; add data-endpoint there (void-sentinel pattern says this is correct)

## Expected runtime

All operations on a single HTML file ~1326 lines + one JS file. Total edit time < 1 minute. Tests run in < 5 seconds.
