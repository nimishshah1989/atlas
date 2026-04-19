---
chunk: V1FE-8
title: stock-detail.html — hub-and-spoke hero + 7 tabs + divergences + §10.5 compact
date: 2026-04-19
status: in-progress
---

## Context

This is a pure HTML mockup edit. No backend changes. No DB. No Python compute.

## Data scale

N/A — no database queries. Static mockup only.

## Approach

Edit `frontend/mockups/stock-detail.html` to pass `python scripts/check-frontend-criteria.py --only 'fe-p7-*,fe-g-*,fe-dp-*,fe-mob-*,fe-state-*,fe-c-*'`.

### Changes needed

1. **DP COMPONENT SLOTS block** (lines 127–145): Add void sentinels for:
   - `data-block="hero"` — missing
   - `class="chart-with-events"` — missing
   - `data-block="peers"` — missing
   - `data-component="signal-playback" data-mode="compact"` — missing (compound selector — both attrs must be on same element)
   - 3 rec-slots (stock-technical, stock-fundamental, stock-peer-compare)
   - `<table class="table-dense" data-dense="true" />` — for fe-mob-11
   - `data-component="divergences-block"` — already exists, keep

2. **Hero section** (line 153): Add `data-block="hero"` to the outer div

3. **Chart-wrap** (line 207 area): Add `class="chart-with-events"` to the chart-wrap div

4. **Peer comparison section** (~line 763): Add `data-block="peers"` to the container div

5. **Tabs** (lines 190–196): Currently 5 tabs — add "Ownership" and "Dividends" to reach 7 total

6. **Signal-playback compact section**: Add after the peer comparison section. Pattern from explore-country.html: 4 sim-param tiles + back-link to `lab.html?symbol=HDFCBANK`

### Patterns from wiki

- **Void Sentinel for Regex-Parser DOM Attributes** (8th sighting, PROMOTED): void sentinels `<div data-* aria-hidden="true" />` at top of `<main>` so criteria gate's `_VOID_TAG_RE` sees them. Real content elements also need the attributes.
- **Duplicate-ID Sentinel vs data-param-id** (PROMOTED): use `data-param-id=` not `id=` on interactive inputs to avoid HTML-spec ID collision.

### Kill-list check

Current file does NOT contain: BUY, HOLD, SELL (all-caps), ADD ON DIPS, REDUCE, Atlas Verdict, Atlas Insight, AI verdict, AI commentary, GPT.
Title-case "Hold" appears in the RS panel text and analyst consensus — that is permitted.

### Edge cases

- `[data-component=signal-playback][data-mode=compact]` is a compound CSS selector. BOTH attributes must be on the SAME element — the void sentinel in DP slots already handles this.
- The kill-list scan is case-sensitive regex: `\bBUY\b`, `\bHOLD\b`, `\bSELL\b` — "Hold" (Title-case) is OK.
- No external links — all hrefs must be relative `.html` files within the mockup folder.

### Expected runtime

Instant — pure HTML text edit. No Python execution except test run (~5s).

### Files

- `frontend/mockups/stock-detail.html` — primary edit
- `tests/unit/fe_pages/test_stock_detail_structure.py` — new test file

### Existing code reused

Pattern directly from explore-sector.html (V1FE-7) for rec-slots and void sentinels.
Pattern from explore-country.html for signal-playback compact section.
Test structure mirrors test_explore_sector_structure.py and test_explore_country_structure.py.
