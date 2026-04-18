# Chunk V1FE-5 Approach: explore-global.html criteria fixes + unit tests

## Summary
Pure frontend mockup fix — no backend changes, no DB, no migrations.

## Data scale
N/A — static HTML file (~1551 lines, 124KB). No DB queries needed.

## Wiki patterns checked
- **Void Sentinel for Regex-Parser DOM Attributes** (5th sighting) — V1FE-4 established
  the pattern for `data-block` attributes and rec-slot sentinels. This chunk follows
  the same approach for explore-global.html.
- **Criteria-as-YAML Executable Gate** — `scripts/check-frontend-criteria.py` reads
  YAML criteria and checks HTML via regex; void sentinels at top of `<body>` make
  `data-*` attributes visible to the `_VOID_TAG_RE` parser.

## Approach

### fe-p4-01: data-block attributes
Add `data-block="<name>"` directly to each `<section class="sect" id="sect-*">` tag
(not as void sentinels — the section tags themselves are the elements to annotate):
- `id="sect-macros"` → add `data-block="macros"`
- `id="sect-yields"` → add `data-block="rates"`
- `id="sect-fx"` → add `data-block="fx"`
- `id="sect-commod"` → add `data-block="commodities"`
- `id="sect-credit"` → add `data-block="credit"`

Also add void sentinels near the existing DP component slot area (line 444) since the
regex parser may not reach deeply nested section tags. Use the void sentinel pattern
as belt-and-suspenders.

### fe-g-06: HOLD kill-list
Line 1460: `<span class="act act--hold">HOLD</span>` → `<span class="act act--neutral">—</span>`
Line 1472: `<span class="act act--hold">HOLD</span>` → `<span class="act act--neutral">—</span>`

### fe-g-07: Dollar signs before digits
- Signal strip (lines 584, 589, 599): `$88.4` → `88.4`, `$2,412` → `2,412`, `$4.32` → `4.32`
- Macro table (lines 634-636): `$88.4` → `88.4`, `$2,412` → `2,412`, `$4.32` → `4.32`
- Table headers (line 634): `$/bbl` → `USD/bbl`, `$/oz` → `USD/oz`, `$/lb` → `USD/lb`
- Threshold (line 634): `< $95` → `< 95`
- FX reserves (lines 968-969): `$642.4 bn` → `642.4 bn`, `+$1.4 bn wk` → `+1.4 bn wk`
- Commodity matrix (lines 1003-1074): remove `$` prefix from all `cm-num` cells
  Also update commodity sub-labels: `$/oz` → `USD/oz`, `$/lb` → `USD/lb`, `$/bbl` → `USD/bbl`
  `$/tonne` → `USD/tonne`, `$/MMBtu` → `USD/MMBtu`

### fe-g-19: rec-slot global-regime
Add void sentinel after the existing DP component slots (after line 444):
```html
<div class="rec-slot" data-rule-scope="global-regime" data-page="explore-global" data-slot-id="global-regime" />
```

## Existing code reused
- Pattern from breadth.html / today.html for void sentinels and rec-slots
- Test pattern from `tests/unit/fe_pages/test_today_structure.py`

## Edge cases
- `$` in non-numeric contexts (e.g. CSS variables like `var(--...)`) — not affected
- `$/bbl`, `$/oz`, `$/lb` in table row names/headers — change to `USD/bbl` etc.
- The criteria regex for fe-g-07 is `\$[0-9]` — only matches `$` immediately before digit
- Kill-list check uses `\bHOLD\b` word boundary — only standalone HOLD, not "THRESHOLD"

## Expected runtime
Sub-second — pure file edits, no DB, no network.

## Tests
11 tests in `tests/unit/fe_pages/test_explore_global_structure.py`
All pure string/regex checks on the HTML file, no external dependencies.
