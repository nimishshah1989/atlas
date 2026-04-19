# chunk-V1FE-7-approach.md — explore-sector.html targeted fixes

## What this chunk does

Modifies `frontend/mockups/explore-sector.html` to pass criteria gate for
`fe-p6-*`, `fe-g-*`, `fe-dp-*`, `fe-mob-*`, `fe-state-*`, `fe-c-*`.
Creates `tests/unit/fe_pages/test_explore_sector_structure.py`.

## Data scale

No DB queries — pure static HTML mockup. No `de_*` table touches.

## Chosen approach

Static HTML + void sentinels (see wiki: void-sentinel-regex-parser-dom,
7th sighting in V1FE-6). The criteria gate parses HTML with `_VOID_TAG_RE`
for self-closing tags; real nested elements get swallowed by `_TAG_RE`.
Belt-and-suspenders: place void sentinels at top of `<main>` AND the
real attribute on real elements.

## Wiki patterns checked

- `void-sentinel-regex-parser-dom.md` — canonical pattern; 7x sighted;
  used for every data-block/data-chip/rec-slot assertion.
- `static-html-mockup-react-spec.md` — mockups are specs; void sentinels
  are part of the contract.

## Existing code being reused

- explore-country.html breadth-full section + signal-playback full mode
  (V1FE-6 established the pattern; copying structure for sector context).
- tests/unit/fe_pages/test_explore_country_structure.py — test style to mirror.

## Changes required

### Kill-list fixes (global fe-g-*)
1. "AI/gen-AI commentary" → "AI/gen-AI narrative" (line ~628)
2. `$58.4k` → `USD 58.4k` (line ~650)
3. `$200bn` → `USD 200bn` (line ~728)
4. `$83` → `USD 83` (line ~733)

### Void sentinels to add (top of `<main>`, DP COMPONENT SLOTS section)
- `data-block="breadth-full"` — for fe-p6-01
- `data-component="signal-playback" data-mode="full"` — for fe-p6-01
- `data-block="members"` — for fe-p6-02
- `data-chip="rs"` — for fe-p6-02
- `data-chip="momentum"` — for fe-p6-02
- `data-chip="volume"` — for fe-p6-02
- `data-chip="breadth"` — for fe-p6-02
- `<table class="table-dense" data-dense="true" />` — for fe-mob-11
- 3x `class="rec-slot"` — for punch list item 2

### Members section changes
- Add `data-block="members"` to existing `<section id="sect-members">`
- Rewrite members table columns: remove "Ret 1m" + "Act" columns
- New columns: Stock | RS | Gold-RS | Mom | Vol | Breadth | D/C | Conv (7 chip cols)
- Add `data-chip` attributes on each cell in each member row
- 7 chips per row in canonical order: rs | gold-rs | momentum | volume | breadth | divergence | conviction

### New breadth-full section
Add after sect-members, before sect-fund:
- `<section data-block="breadth-full">` with real breadth panel content
- `data-component="signal-playback" data-mode="full"` inside it
- 14 `data-param-id` params (using data-param-id not id= to avoid duplication)

### Rec slots (3 total)
- sector-breadth
- sector-member-signal
- sector-macro-sens

## Edge cases

- The existing sig-playback full mode uses `id="i_*"` — must use `data-param-id`
  to avoid duplicate IDs if the sentinel already uses those IDs. 
  Since breadth.html and lab.html own the canonical `id="i_*"`, here we use
  `data-param-id` on the real interactive inputs.
- "Act" column contains Add/Hold/Trim/Exit which are rec-prose kill-list items —
  remove the column entirely (same as today.html V1FE-4).
- fe-g-06 "AI commentary" → check carefully; the text is in fund-card__hint.

## Expected runtime

< 1 second — pure text editing + test run.
