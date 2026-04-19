---
chunk: V2FE-2
project: atlas
date: 2026-04-19
status: success
---

# V2FE-2: Today / Pulse Page Data Wiring — Approach

## Objective
Wire `frontend/mockups/today.html` from static fixtures to live ATLAS APIs
by adding `data-endpoint`, `data-params`, `data-fixture`, and `data-data-class`
attributes. No DOM elements added except minimal void sentinels in DP COMPONENT
SLOTS section. No layout changes.

## Data scale
Not applicable — this chunk is pure HTML attribute wiring + test file.
No DB queries. No Python data pipeline.

## Current state analysis
- today.html: 1637 lines
- 0 data-endpoint attributes currently
- Existing void sentinels in DP COMPONENT SLOTS (lines 496-505):
  - `data-component="regime-banner"` at line 498 (no endpoint)
  - 5x `data-component="four-decision-card"` at lines 500-504 (no endpoint, deferred)
- Existing structural elements needing attributes:
  - Line 604: global regime-banner div
  - Line 621: global sig-strip div
  - Line 1086: India regime-banner div
  - Line 1104: India sig-strip div
- Existing void sentinels in India briefing section (lines 1353-1356):
  - `data-role="sector-board"`
  - `data-role="movers"`
  - `data-role="fund-strip"`

## Approach
Pure HTML attribute insertion via Edit tool:
1. Add data-endpoint + related attrs to existing void sentinels at lines 498-504
2. Add data-component + data-endpoint to existing structural divs at 604, 621, 1086, 1104
3. Add endpoint attrs to sector-board, movers, fund-strip sentinels at 1353-1356
4. Insert new void sentinel blocks in DP COMPONENT SLOTS section after existing ones
5. Add second movers (losers) block

## Wiki patterns checked
- void-sentinel-regex-parser-dom (10x promoted) — only add attrs to existing elements;
  new sentinels go in DP COMPONENT SLOTS before END DP COMPONENT SLOTS comment
- static-html-mockup-react-spec (6x) — static HTML with data attrs is the React spec

## Existing code reused
- test_atlas_data_js.py in tests/unit/v2fe/ — same pattern (html.parser) for test file

## Edge cases
- V1FE void-sentinel DOM contracts must remain intact (existing data-component/data-regime/data-as-of attrs)
- four-decision-card: add data-v2-deferred="true" NOT data-endpoint (explicitly deferred)
- rec-slots (data-slot-id=*) stay empty
- interpretation-sidecar stays client-derived — no data-endpoint

## Expected runtime
Instantaneous — pure HTML attribute edits, no server interaction.
Test suite: <1s (stdlib html.parser, no network calls).

## Files changed
1. `frontend/mockups/today.html` — add data-endpoint attrs + new void sentinels
2. `tests/unit/v2fe/test_today_bindings.py` — new test file with ≥10 tests
