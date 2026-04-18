# S1-PRE-1: Component library — tokens.css v1.1 + components.html + fixtures bootstrap

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-0 DONE
**Blocks:** S1-0..S1-10 (every page consumes tokens + component snippets)
**Complexity:** L (10–12 hours)
**Quality targets:** code: 85, architecture: 90, frontend: 90, security: 85

---

## Step 0 — Boot context (read in order, fresh session)

1. `cat CLAUDE.md` — Four Laws, especially No-Synthetic-Data
2. `cat docs/design/design-principles.md` **in full** — this chunk is the
   canonical materialisation of DP §3, §10, §11, §12, §13, §14, §15, §16, §18
3. `cat docs/design/frontend-v1-spec.md` §1.2, §1.2.1, §1.2.2, §1.5, §1.8,
   §1.9, §1.10, §1.11
4. `cat docs/design/frontend-v1-mobile.md` — §1.8 mobile breakpoints + rules
5. `cat docs/design/frontend-v1-states.md` — §1.9 canonical states
6. `cat docs/specs/frontend-v1-criteria.yaml` — GROUP 3, GROUP 9, GROUP 11
   (these are the checks your output must pass)
7. `cat frontend/mockups/tokens.css` current — this chunk extends it, doesn't
   rewrite it. Diff must be additive.
8. `cat ~/.forge/knowledge/wiki/index.md` → `design-language-locked` article

## Goal

One place that defines every reusable visual primitive the 10 V1 pages
compose from. Ship it *before* any page chunk, so every page chunk
consumes pre-reviewed, gate-passing components.

Three outputs:
1. `tokens.css` v1.1 — additive tokens for staleness, regime bands,
   7-chip color palette, tap-target min sizes, breakpoint variables.
2. `components.html` — visible component gallery/styleguide with every
   DP-mandated component rendered once, in every canonical state
   (default / empty / loading / error). Used by S1-0..S1-10 authors
   as the copy-paste source.
3. Two new seed fixtures: `mf_rank_universe.json` and `sector_rrg.json`
   (schemas already exist from prior Agent deliverable).

## Files

### New
- `frontend/mockups/components.html` (≥ 700 lines)
- `frontend/mockups/fixtures/mf_rank_universe.json` (≥ 30 funds, JIP-sourced via /api/v1/mf/search)
- `frontend/mockups/fixtures/sector_rrg.json` (12 sectors, 8-week tails each)
- `frontend/mockups/components/_chip.html` (copy-paste snippet block)
- `frontend/mockups/components/_regime-banner.html`
- `frontend/mockups/components/_signal-strip.html`
- `frontend/mockups/components/_interpretation-sidecar.html`
- `frontend/mockups/components/_signal-history-table.html`
- `frontend/mockups/components/_divergences-block.html`
- `frontend/mockups/components/_four-decision-card.html`
- `frontend/mockups/components/_simulate-this.html`
- `frontend/mockups/components/_four-universal-benchmarks.html`
- `frontend/mockups/components/_empty-state.html`
- `frontend/mockups/components/_skeleton.html`
- `frontend/mockups/components/_error-state.html`
- `frontend/mockups/components/_staleness-badge.html`
- `frontend/mockups/components/_methodology-footer.html`

### Modified
- `frontend/mockups/tokens.css` (additive — never remove existing tokens)
- `frontend/mockups/base.css` (import the new tokens, add print-only rules, mobile breakpoints)

## tokens.css v1.1 additions (additive only)

```css
/* v1.1 — staleness palette */
--staleness-fresh-bg:     #E8F4EE;
--staleness-fresh-fg:     var(--rag-green-700);
--staleness-stale-bg:     #FFF5E6;
--staleness-stale-fg:     var(--rag-amber-700);
--staleness-very-bg:      #FDECEA;
--staleness-very-fg:      var(--rag-red-700);

/* regime bands (DP §12) */
--regime-risk-on-bg:      #E8F4EE;
--regime-risk-on-fg:      var(--rag-green-700);
--regime-risk-off-bg:     #FDECEA;
--regime-risk-off-fg:     var(--rag-red-700);
--regime-neutral-bg:      #F3F4F6;
--regime-neutral-fg:      #4B5563;
--regime-mixed-bg:        #FFF8EC;
--regime-mixed-fg:        var(--rag-amber-700);

/* 7-chip palette (DP §10 + §13) */
--chip-rs-fg:             var(--accent-700);
--chip-momentum-fg:       #7C3AED;
--chip-volume-fg:         #0EA5E9;
--chip-breadth-fg:        #059669;
--chip-gold-rs-fg:        #B45309;   /* gold amplifier */
--chip-conviction-fg:     #1A1F2B;   /* highest-contrast; score-band tinted */
--chip-divergence-fg:     var(--rag-red-700);

/* conviction score bands */
--conviction-low-bg:      #FDECEA;
--conviction-med-bg:      #FFF5E6;
--conviction-high-bg:     #E8F4EE;

/* accessibility */
--tap-min:                44px;

/* breakpoints (§1.8) — used in base.css media queries */
--bp-xs-max:   639px;
--bp-s-max:    959px;
--bp-m-max:   1199px;
--bp-l-max:   1439px;
```

## components.html structure

Each component demoed in a `<section data-component="<name>">` with:
- heading + DP §ref link
- default state
- empty state
- loading state
- error state
- code-snippet pre block (for copy-paste)

Every component carries the exact semantic class name and `data-component`
attribute the GROUP 9 checks look for. No inline styles.

## Fixture authoring — ZERO synthetic data (Law 2)

Both new fixtures must be sourced from real JIP data via the read-only
client (`backend/clients/jip_data_service.py`). Author script committed
alongside the fixtures:

- `scripts/seed-mf-rank-universe.py` — query `de_mf_*` tables,
  compute Returns / Risk / Resilience / Consistency scores using the
  v1.1 dimensional-fix formula (z_cat per factor → Φ → average), emit 30
  funds across 5 categories. Every row carries `scheme_code` traceable
  to the source table.
- `scripts/seed-sector-rrg.py` — query `de_stock_price_daily` for the
  12 canonical NIFTY sector indices, compute 8-week RS-ratio + RS-momentum
  tails, classify into quadrants. Every tail row is a real close, never
  interpolated.

Both fixtures carry top-level `data_as_of` + `source` fields (fe-f-09/10).
Re-running the seed scripts against the same `data_as_of` date must
produce byte-identical JSON (determinism).

## Tests (≥ 8 cases)

1. `test_tokens_css_is_additive` — parse old + new, assert no removed keys
2. `test_components_html_renders_every_dp_component` — BeautifulSoup parse, assert every component slug from §1.10 matrix present
3. `test_components_html_every_component_shows_all_4_states` — default/empty/loading/error each ≥ 1
4. `test_mf_rank_fixture_schema_valid` — jsonschema against mf_rank_universe.schema.json
5. `test_mf_rank_fixture_composite_matches_factor_mean` — for 3 sampled rows, composite = round((r+k+s+c)/4, 1)
6. `test_sector_rrg_fixture_schema_valid`
7. `test_sector_rrg_fixture_tail_length_ge_8` — every sector has ≥ 8 tail entries
8. `test_seed_scripts_deterministic_given_same_date` — re-run, diff produces zero bytes

## Points of success (all required for DONE)

1. `python scripts/check-frontend-criteria.py --only $(grep -o 'fe-dp-[0-9]*' docs/specs/frontend-v1-criteria.yaml | sort -u | tr '\n' ',')` — every DP check runs green against `components.html` (**meta-requirement**: GROUP 9 is satisfied by the library alone, before any page consumes it)
2. `python scripts/check-frontend-criteria.py --only fe-f-03,fe-f-04,fe-f-05,fe-f-06,fe-f-07,fe-f-08,fe-f-09,fe-f-10` — both new fixtures present, schema-valid, v1.1 compliant
3. `html5validator frontend/mockups/components.html` exits 0
4. `pytest tests/unit/fe_components/ -v` — all ≥8 tests green
5. `ruff check scripts/seed-mf-rank-universe.py scripts/seed-sector-rrg.py` clean
6. Opening `frontend/mockups/components.html` in a browser (use Playwright headed for the design-review pass) shows the gallery; every component renders all 4 states without console errors
7. Zero new tokens defined outside `tokens.css` (grep check included in runner via `design_tokens_only`)
8. No component uses an inline `style=` attribute

## Post-chunk sync invariant

`scripts/post-chunk.sh S1-PRE-1` green — forge-ship commit, service
restart, smoke (open components.html via the static server used for
Playwright checks, assert 200 + title "ATLAS Components"),
forge-compile, MEMORY.md entry `reference_fe_component_library.md`.
