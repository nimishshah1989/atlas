---
chunk: V1FE-2
project: ATLAS
date: 2026-04-18
---

# Approach: V1FE-2 Component Library

## Task Summary
1. Update 7 existing HTML pages with DP component data attributes
2. Create components.html component library page
3. Update tokens.css (additive only)
4. Create 8 fixture JSON data files
5. Update 2 schemas (mf_rank_universe, sector_rrg)
6. Create seed_fixtures.py deterministic script
7. Create test_v1fe2_fixtures.py (≥8 tests)

## Scale
No database queries needed — pure HTML/CSS/JSON file generation.

## Approach

### Phase 1: DOM updates to existing HTML pages
The dom_checks.py checker uses regex-based matching. Key insight: it checks
`data-component="regime-banner"` and `data-regime` and `data-as-of` attributes.
The checker resolves selectors like `[data-component='regime-banner']` which
maps to elements that have `data-component="regime-banner"` (note: single-quote
in selector matches double-quote in HTML because _parse_attrs() strips both).

For each page, I add minimal HTML elements with the required data attributes.
I will add them at the TOP of the `<main>` or content area to avoid disrupting
existing layout.

### Phase 2: components.html
Valid HTML5 — must pass html5validator. Follow same CSS import pattern as
existing pages (tokens.css → base.css → components.css). Show each DP
component with name labels and state variants.

### Phase 3: tokens.css v1.1
Only ADD new tokens. The chunk spec says "consider adding tokens for Signal
strip sizing". I'll add minimal tokens for chip-gap and signal-strip layout.

### Phase 4: Fixture JSON files
The 8 fixtures must be deterministic. Use `random.seed()` from date string.
The fixture_schema check validates the 4 "new" fixtures: mf_rank_universe.json,
sector_rrg.json, ppfas_flexi_nav_5y.json, reliance_close_5y.json.

Critical: mf_rank_universe needs both existing required fields AND new aliases
(scheme_name, tie_break_rank). sector_rrg needs sector_code and tail array ≥8.

### Phase 5: Schema updates
- mf_rank_universe.schema.json: add scheme_name, tie_break_rank to properties and required
- sector_rrg.schema.json: add sector_code, tail, source to properties; add sector_code to required

Must update additionalProperties:false blocks to include new properties.

### Phase 6: seed_fixtures.py
Deterministic: `random.seed(as_of_str)` for any random data.
json.dumps with sort_keys=True, indent=2 for byte-identical output.

### Phase 7: Tests
pytest unit tests in tests/unit/test_v1fe2_fixtures.py loading JSON directly.

## Edge Cases
- Selector matching is case-sensitive for attribute values
- The checker uses single/double quote stripping so `[data-component='regime-banner']`
  matches `data-component="regime-banner"` in HTML
- must_carry_attrs checks ALL matched elements have those attrs
- composite_score must be round((r+k+s+c)/4, 1) to exactly 0.1 precision
- sector_rrg tail must have ≥8 entries per sector
- fe-f-03 is a file_exists check — just need the files to exist
- fe-f-04..fe-f-10 are fixture data checks that need schema compliance
- sector_rrg schema has `additionalProperties: false` at sector item level

## Files Modified
- frontend/mockups/today.html
- frontend/mockups/explore-global.html
- frontend/mockups/explore-country.html
- frontend/mockups/explore-sector.html
- frontend/mockups/stock-detail.html
- frontend/mockups/mf-detail.html
- frontend/mockups/portfolios.html
- frontend/mockups/components.html (new)
- frontend/mockups/tokens.css
- frontend/mockups/fixtures/events.json (new)
- frontend/mockups/fixtures/breadth_daily_5y.json (new)
- frontend/mockups/fixtures/zone_events.json (new)
- frontend/mockups/fixtures/search_index.json (new)
- frontend/mockups/fixtures/ppfas_flexi_nav_5y.json (new)
- frontend/mockups/fixtures/reliance_close_5y.json (new)
- frontend/mockups/fixtures/mf_rank_universe.json (new)
- frontend/mockups/fixtures/sector_rrg.json (new)
- frontend/mockups/fixtures/schemas/mf_rank_universe.schema.json
- frontend/mockups/fixtures/schemas/sector_rrg.schema.json
- scripts/seed_fixtures.py (new)
- tests/unit/test_v1fe2_fixtures.py (new)
