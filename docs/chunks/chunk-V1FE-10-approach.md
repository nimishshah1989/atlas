---
chunk: V1FE-10
project: ATLAS
date: 2026-04-18
status: in-progress
---

# Chunk V1FE-10 Approach: MF Rank Page Mockup

## What we're building
- `frontend/mockups/mf-rank.html` — static HTML mockup for 4-factor MF ranking page
- `tests/unit/fe_pages/test_mf_rank_structure.py` — 9 structural tests (regex-based, no beautifulsoup)

## Data scale
- No DB access needed — this is a pure frontend mockup chunk
- Fixture: `frontend/mockups/fixtures/mf_rank_universe.json` — 5 funds, ~155 lines

## Fixture verification
From reading the fixture:
- composite_score for fund 1: round((82.5 + 78.5 + 80.0 + 85.0)/4, 1) = round(81.5, 1) = 81.5 ✓
- composite_score for fund 2: round((75.5 + 73.0 + 76.5 + 79.0)/4, 1) = round(76.0, 1) = 76.0 ✓
- composite_score for fund 3: round((70.0 + 74.5 + 72.5 + 77.0)/4, 1) = round(73.5, 1) = 73.5 ✓
- composite_score for fund 4: round((88.5 + 55.0 + 60.5 + 82.0)/4, 1) = round(71.5, 1) = 71.5 ✓
- composite_score for fund 5: round((79.5 + 66.0 + 69.0 + 75.5)/4, 1) = round(72.5, 1) = 72.5 ✓
- All factors in 0..100: ✓
- Funds sorted by composite desc (81.5, 76.0, 73.5, 72.5, 71.5) — funds 4+5 rank 5 vs 4 determined by tie-break

## Approach

### HTML file
- Follow explore-sector.html pattern exactly for DP component slots
- Follow mf-detail.html pattern for dense CSS in <style> block
- Nav: copy inline nav from explore-sector.html (sentinels pattern with aria-hidden for checker, plus real visible nav)
- Method footer: copy from _shared.html
- No Math.random(), no unseeded Date()
- Script section fetches fixture via fetch() and populates table dynamically

### DOM structure
1. Standard head with 3 CSS links + page-specific style block
2. Inline nav sentinels (aria-hidden) for criteria checker
3. Visible topbar nav with all 10 links + search
4. main.page with DP component slots block at top
5. Filter rail (aside) + rank table (div)
6. Factor legend with data-factor attrs for all 4 factors
7. Tie-break indicator (span[data-role="tie-break"])
8. Formula disclosure section.explain-block[data-topic="mf-rank-formula"]
9. rec-slot div
10. Methodology footer

### Key criteria to hit
- fe-p9-01: 4 data-factor elements (returns/risk/resilience/consistency)
- fe-p9-02: span[data-role="tie-break"]
- fe-p9-03: section.explain-block[data-topic="mf-rank-formula"] with formula text
- fe-p9-04: aside[data-block="filter-rail"] + div[data-block="rank-table"] with 8+ th
- fe-mob-11: table wrapped in .mobile-scroll
- fe-g-04: Only CSS vars, no raw hex
- fe-g-06: No BUY/HOLD/SELL/RECOMMEND language
- fe-dp-01/02/03/05: DP component slots

### Test file
- tests/unit/fe_pages/ directory needs to be created with __init__.py
- 9 tests using re/string matching on raw HTML
- No beautifulsoup, no external DOM libs

## Wiki patterns used
- static-html-mockup-react-spec: HTML mockup as spec before React impl
- regex-html-nested-depth-counter: stdlib-only selector pattern

## Edge cases
- The formula disclosure text must include z_cat, Composite, and tie-break order
- All factor scores must be 0–100 range (fixture validates this)
- rank table tbody populated by JS fetch, but HTML structure (thead) is static

## Expected runtime
- Creating HTML: ~5 min
- Creating test file: ~3 min
- Pytest run: <5s
