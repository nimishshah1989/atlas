# Chunk V1FE-12 Approach: portfolios.html structural fixes + rec-slots

## Data scale
No database interaction. Pure static HTML mockup edit + unit tests.
No `psql` check needed.

## Chosen approach
Edit `frontend/mockups/portfolios.html` via targeted string replacements:
1. Add `data-book="N"` to each of 4 `.book` anchor elements
2. Add `data-block="holdings"` to each of 4 `.book__holdings` divs
3. Add `data-role="benchmark"` to each of 4 `.book__meta` divs
4. Add 4 rec-slot divs (one inside each book card, before closing `</a>`)
5. Add `.rec-slot { display: none; }` CSS rule to the `<style>` block
6. Strip `.acc-banner*` CSS rules (lines 38-46) — dead CSS, DOM never had those elements
7. Strip ledger CSS (lines 91-130) — dead CSS cleanup

Create `tests/unit/fe_pages/test_portfolios_structure.py` following exact
pattern from `test_breadth_structure.py` and `test_mf_rank_structure.py`:
- Regex/string matching only (no BeautifulSoup)
- 10+ tests covering all acceptance criteria

## Wiki patterns checked
- `static-html-mockup-react-spec` (PROMOTED): Static HTML + approach.md is the standard
- `criteria-as-yaml-quality-gate` (PROMOTED): criteria YAML drives what tests verify
- `verifier-dir-exemption` (PROMOTED): mockups/ exempt from dirty_working_tree check

## Existing code reused
- `tests/unit/fe_pages/test_breadth_structure.py` — exact test pattern
- `tests/unit/fe_pages/test_mf_rank_structure.py` — exact test pattern

## Edge cases
- CSS block still references `.acc-banner*` selectors — stripping them is safe (DOM never had them)
- Ledger CSS selectors (.ledger, .ledger-row, etc.) are referenced nowhere in DOM after strip
- `data-book`, `data-block`, `data-role` attributes must be on element open tags
- rec-slot `data-page` must be `"portfolios"` (not `"portfolio"`)
- rec-slot `data-rule-scope` must be `"book"` for all 4

## fe-p11-02 status
CSS classes `.acc-banner` and DOM elements are separate. The criteria check
for DOM element presence, NOT CSS rules. The current file has no `.acc-banner`,
`data-block=rec-ledger`, or `data-block=pending-recs` elements — criteria #2
ALREADY passes. Stripping the CSS is cleanup only.

## Expected runtime
Under 1 second. Pure string replacement on a 527-line HTML file.
