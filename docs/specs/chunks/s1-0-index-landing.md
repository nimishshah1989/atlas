# S1-0: index.html — landing page + link audit

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE
**Blocks:** None directly, but unblocks forge-browser-preview reachability tests
**Complexity:** S (2 hours)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 85, architecture: 85, frontend: 90

## Page-specific goal

One index file at `frontend/mockups/index.html` that links to every
Stage-1 mockup in IA order, annotated with its DP §ref and the V8 page
it maps to (per `project_atlas_frontend_pages.md`). Acts as both a
developer entry point and the link-integrity anchor.

## Files

### New
- `frontend/mockups/index.html`
- `tests/unit/fe_pages/test_index_structure.py`

## Page skeleton (mandatory)

- header: ATLAS wordmark + "frontend V1 — Stage 1 mockups" subtitle
- 3 groups of links (matches §2.1 hub-and-spoke IA):
  - **Pulse**: today.html
  - **Explorer**: explore-global.html, explore-country.html, explore-sector.html, breadth.html
  - **Deep dives**: stock-detail.html, mf-detail.html, mf-rank.html, portfolios.html, lab.html
- `components.html` linked in a "design artefacts" strip
- every link annotates: DP §ref · spec §ref · target V8 route
- methodology footer

## Criteria ids this chunk must pass

- `fe-l-01` — all 10 page links present
- `fe-l-02` — zero dead links
- `fe-g-*` critical subset (html5_valid, tokens, methodology footer)
- `fe-mob-*` — no horizontal scroll at 360px (S1 applies the global check
  to every page; verify index is lightweight enough to pass trivially)

## Points of success (in addition to s1-common baseline)

1. `scripts/check-frontend-criteria.py --only fe-l-01,fe-l-02` exits 0
2. Every `<a href>` in index.html resolves to an actual file in `frontend/mockups/`
3. `tests/unit/fe_pages/test_index_structure.py` — ≥ 3 cases:
   - all 10 hrefs present
   - every link row carries DP §ref + spec §ref
   - no external links (keep V1 self-contained)
