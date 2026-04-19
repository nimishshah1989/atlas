---
id: V2FE-0
title: "Criteria YAML + loader skeleton + §6 states contract"
status: PENDING
estimated_hours: 4
deps: []
gate_criteria:
  - frontend-v2-criteria.yaml exists and parses without error
  - scripts/check-frontend-v2.py --list exits 0 and prints at least 9 backend check IDs
  - atlas-data.js exists and exports loadBlock, renderSkeleton, renderEmpty, renderStaleBanner, renderError
  - atlas-states.js exists and exports STALENESS_THRESHOLDS keyed by data class
  - No V1FE criteria regressions (scripts/check-frontend-criteria.py still exits 0)
---

## Objective

Author the `docs/specs/frontend-v2-criteria.yaml` acceptance-criteria file that gates the entire V2FE slice, plus the two new loader JS assets that every V2FE page chunk will reference. This chunk must land before any per-page wiring starts.

## Punch list

1. [ ] Create `docs/specs/frontend-v2-criteria.yaml` encoding §8.1 (9 backend checks), §8.2 (per-page binding checks for all 6 pages), §8.3 (states contract checks), §8.4 (integration/smoke checks), §8.5 (regression checks). Each entry must have: `id`, `title`, `check_type`, `severity` (critical | high | medium), `page` (or `global`), optional `whitelist`.
2. [ ] Create `scripts/check-frontend-v2.py` — minimal runner that loads the criteria YAML, runs each check against the live API (for backend checks) or the HTML files (for DOM checks), and emits `.forge/frontend-v2-report.json` following the same runner-report-json-contract as `scripts/check-frontend-criteria.py`.
3. [ ] Create `frontend/mockups/assets/atlas-data.js` implementing the §6.2 loader:
   - `loadBlock(el)` — fetches `data-endpoint`, applies 8s AbortController timeout, sets `data-state`, calls per-state renderers
   - `fetchWithTimeout(url, ms)` — AbortController wrapper
   - `buildUrl(endpoint, params)` — merges endpoint path with param object
   - `hasData(json)` — checks `json.records?.length > 0 || json.series?.length > 0 || json.divergences?.length > 0`
   - `isStale(el, json)` — compares `json._meta.staleness_seconds` against `STALENESS_THRESHOLDS[el.dataset.dataClass]`
   - Offline fallback: if fetch fails with network error AND `el.dataset.fixture` is set, load fixture JSON via `fetch(el.dataset.fixture)`
4. [ ] Create `frontend/mockups/assets/atlas-states.js` implementing:
   - `STALENESS_THRESHOLDS` map per §6.3: intraday=3600, eod_breadth=21600, daily_regime=86400, fundamentals=604800, events=604800, holdings=604800, system=21600
   - `renderSkeleton(el)` — injects `<div class="skeleton-block">` placeholder
   - `renderEmpty(el)` — injects the `empty-state` subtree from `components.html`
   - `renderStaleBanner(el, json)` — prepends amber `data-staleness-banner` with `data_as_of` text
   - `renderError(el, err)` — injects error card with `err.code`
   - Known-sparse-source guard: if `json._meta.insufficient_data === true`, call `renderEmpty(el)` regardless of `records` length
5. [ ] Wire `atlas-data.js` and `atlas-states.js` as `<script>` tags (deferred) in each of the 6 target HTML pages — only add the script tags, do not modify existing content.
6. [ ] Write `tests/unit/v2fe/test_atlas_data_js.py` — 8 unit tests using `pyduktape` or `js2py` verifying loader state transitions (loading→ready, loading→empty, loading→stale, loading→error, offline fixture fallback, insufficient_data short-circuit, timeout, abort).
7. [ ] Confirm `scripts/check-frontend-criteria.py` still exits 0 (no V1FE regression).

## Exit criteria

- `docs/specs/frontend-v2-criteria.yaml` exists, parses with `yaml.safe_load`, contains ≥30 entries.
- `scripts/check-frontend-v2.py --list` prints ≥9 backend check IDs.
- `frontend/mockups/assets/atlas-data.js` exports `loadBlock` (verified by `grep -c "function loadBlock"` ≥1).
- `frontend/mockups/assets/atlas-states.js` exports `STALENESS_THRESHOLDS` (verified by grep).
- `pytest tests/unit/v2fe/test_atlas_data_js.py -v` passes ≥8 tests.
- `scripts/check-frontend-criteria.py` exits 0 (V1 gate unchanged).

## Domain constraints

- No new Pydantic models in this chunk — criteria YAML is data, not code.
- JS files must be plain ES2020 (no TypeScript, no bundler) — the mockups are static HTML.
- `STALENESS_THRESHOLDS` values must match §6.3 exactly; any deviation blocks downstream chunks.
- Financial display: not applicable (this chunk has no data rendering).
- Known-sparse guard: `de_adjustment_factors_daily` (0 rows), `de_fo_bhavcopy` (0 rows), USDINR (3 rows) — the insufficient_data branch must short-circuit to empty-state, never to error.
