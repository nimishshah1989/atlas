# Chunk V1FE-3 Approach — index.html landing + link audit

## Summary

Build `frontend/mockups/index.html` as the hub/landing page linking to all 10 Stage-1 mockups,
plus `tests/unit/fe_pages/test_index_structure.py` with ≥3 test cases.

## Data scale

No database touched. Pure static HTML file + test file only.

## Chosen approach

**Static HTML** — no Python, no data pipelines, no DB. The file is a clean hub page
using the same CSS token system as every other mockup.

Wiki patterns checked:
- `static-html-mockup-react-spec` — self-contained HTML with tokens.css; approach.md
  doubles as spec for any downstream React chunk
- `criteria-as-yaml` — the `fe-l-01` check uses `dom_required` + `must_include_href_any`;
  the 10 hrefs must appear literally in `a[href*='.html']` elements

## Criteria gate analysis

| Criterion | Check type | What index.html must have |
|---|---|---|
| fe-l-01 | dom_required file=index.html, selector=`a[href*='.html']`, must_include_href_any | All 10 page hrefs |
| fe-l-02 | link_integrity files=`frontend/mockups/*.html` | No broken local links from any .html |
| fe-g-03 | html5_valid files=`frontend/mockups/*.html` | Valid HTML5 doctype/structure |
| fe-g-04 | design_tokens_only files=`frontend/mockups/*.html` | No raw hex/rgb/hsl outside CSS vars |
| fe-g-05 | grep_forbid `prefers-color-scheme: dark`, etc. | No dark-mode residue |
| fe-g-06 | kill_list files=`frontend/mockups/*.html` | No BUY/SELL/HOLD/verdict language |
| fe-g-07 | i18n_indian files=`frontend/mockups/*.html` | No $, million, billion |
| fe-g-18 | grep_forbid `Math.random()`, unseeded `new Date()` | No random JS |
| fe-mob-* | Playwright on specific pages | index.html NOT in scope for mob checks |

fe-g-08 (explain-block), fe-g-09 (methodology-footer), fe-g-10 (tooltips),
fe-g-15 (nav-shell), fe-g-16 (search box) all use `pages_from: settings.all_pages`
which does NOT include index.html — so those do NOT apply to index.html.

## HTML structure

- DOCTYPE html, `<html lang="en">`, `<meta charset="UTF-8">`, `<meta name="viewport">`
- Title: `ATLAS · Home`
- Link: tokens.css, base.css, components.css
- `<style>` with CSS vars only — no raw hex/rgb/hsl
- `<body>` with:
  - Simple header with ATLAS wordmark
  - Grid/list of cards, each an `<a href="page.html">` link
  - No nav-shell, no methodology-footer (not required for index.html)
  - No charts, KPIs, regime banners
- No JavaScript at all (avoids fe-g-18 risk entirely)
- No dark-mode, no verdict prose, no dollar/million/billion

## 10 required links (literal hrefs)

1. today.html
2. explore-global.html
3. explore-country.html
4. explore-sector.html
5. stock-detail.html
6. mf-detail.html
7. mf-rank.html
8. breadth.html
9. portfolios.html
10. lab.html

## Edge cases

- The `design_tokens_only` check scans inline `style=` attributes for raw colors.
  Will use zero inline style attributes to be safe.
- The `link_integrity` check resolves hrefs relative to the HTML file's directory.
  All links are bare filenames — same directory — so they resolve correctly once
  all 10 target files exist.
- No `font-family:` declarations in `<style>` — use `var(--font-serif)` etc.
- No raw hex colors anywhere in the file. All colors via CSS vars.

## Files to create

1. `/home/ubuntu/atlas/frontend/mockups/index.html`
2. `/home/ubuntu/atlas/tests/unit/fe_pages/test_index_structure.py`

## Expected runtime

Instantaneous — pure file creation and pytest string matching. No DB, no network.
