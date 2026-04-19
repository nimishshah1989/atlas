---
id: V2FE-8
title: "States rollout: loading/empty/stale/error across all 6 pages + staleness banners"
status: PENDING
estimated_hours: 3
deps: [V2FE-2, V2FE-3, V2FE-4, V2FE-5, V2FE-6, V2FE-7]
gate_criteria:
  - Every non-whitelisted block on all 6 pages carries data-state attribute set by the loader
  - loading skeleton renders within 100ms of page load for every block
  - empty-state subtree renders when API returns records:[]
  - stale banner renders when _meta.staleness_seconds exceeds threshold
  - error card renders when API returns non-200 or times out after 8s
  - data-as-of attribute on each block matches _meta.data_as_of from response
  - No block remains in data-state=loading past 10s (hard cut-off to error)
  - scripts/check-frontend-criteria.py still exits 0 for all 6 pages
---

## Objective

The per-page wiring chunks (V2FE-2..7) added `data-endpoint` attributes and imported the loader. This chunk does the integration pass: verify the four canonical states (loading, empty, stale, error) actually render correctly on every non-whitelisted block across all 6 pages. Extend `atlas-states.js` if any state rendering is incomplete, and add `data-state-tested="true"` annotations to blocks whose state transitions have been manually verified or smoke-tested.

## Punch list

1. [ ] Audit all 6 pages: for each `[data-endpoint]` block, verify the loader (`atlas-data.js`) correctly calls all four state renderers. Use a checklist per page (mark as `[x]` in spec after verification).
2. [ ] **Loading state**: verify `renderSkeleton(el)` injects a `<div class="skeleton-block">` with correct height hint. Ensure the skeleton matches the block's rough layout (full-width bar for tables, square for charts). Update `atlas-states.js` if any skeleton is missing or misshapen.
3. [ ] **Empty state**: verify `renderEmpty(el)` injects the `empty-state` subtree from `components.html` with correct label. For known-sparse blocks (`data-sparse="true"`), verify empty-state renders without error card when `insufficient_data:true`.
4. [ ] **Stale state**: verify `renderStaleBanner(el, json)` prepends the amber `data-staleness-banner` above block content with correct `data_as_of` text and elapsed time. Verify the banner uses the staleness threshold from `STALENESS_THRESHOLDS` matching `el.dataset.dataClass`.
5. [ ] **Error state**: verify `renderError(el, err)` injects the error card with `err.code` visible and a retry affordance. Verify 8s AbortController timeout triggers the error state (not infinite spinner).
6. [ ] **Hard cut-off guard**: in `atlas-data.js`, add a `setTimeout(10000, () => { if (el.dataset.state === "loading") { el.dataset.state = "error"; el.dataset.errorCode = "TIMEOUT"; renderError(el, {code:"TIMEOUT"}); } })` for every block.
7. [ ] **`data-as-of` sync**: verify that after every `loadBlock()` success, `el.dataset.asOf` is set from `json._meta.data_as_of`. Add `data-as-of` fallback text to each block if `json._meta.data_as_of` is absent (log warning, set `"unknown"`).
8. [ ] **Dev-mode state simulation**: add URL param `?sim_state=loading|empty|stale|error` support to `atlas-data.js`. When param is present, `loadBlock()` skips the fetch and directly renders the requested state (for QA and §8.3 gate verification). This must be **dev-mode only** — gate on `window.location.hostname === "localhost"` or `"127.0.0.1"`.
9. [ ] **Whitelist audit**: confirm all whitelisted blocks (`data-v2-derived="true"`, `data-v2-deferred="true"`, `data-v2-static="true"`) do NOT have `data-endpoint` and are exempt from state rendering. The V2 criteria YAML (authored in V2FE-0) must enumerate these exemptions; update it if any new exemptions emerged during V2FE-2..7.
10. [ ] Write `tests/unit/v2fe/test_states_contract.py` — ≥10 tests covering:
    - Loading state: skeleton element present immediately after `loadBlock()` called.
    - Empty state: empty-state subtree present when `hasData(json)` returns false.
    - Stale state: amber banner present when `staleness_seconds > threshold`.
    - Error state: error card present on fetch rejection.
    - Timeout: error card present after 10s when fetch never resolves.
    - `data-as-of` sync: attribute updated to `_meta.data_as_of` value.
    - `insufficient_data=true` → empty-state, not error.
    - Dev-mode `?sim_state=stale` renders stale without fetch.
    - Known-sparse block renders empty (not error) on `insufficient_data:true`.
    - Whitelist: `data-v2-derived` block has no state set.
11. [ ] Update `docs/specs/frontend-v2-criteria.yaml` with any new states-contract check IDs that emerged from this review.
12. [ ] Run `scripts/check-frontend-criteria.py` across all 6 pages — must exit 0.

## Exit criteria

- `pytest tests/unit/v2fe/test_states_contract.py -v` passes ≥10 tests.
- `scripts/check-frontend-criteria.py` exits 0 for all 6 pages (no V1 regression).
- All 6 pages: every `[data-endpoint]` block has `data-state` attribute (verified by grep or parser test).
- `atlas-data.js` contains 10s hard cut-off setTimeout guard.
- `atlas-data.js` contains `?sim_state=` dev-mode support.
- Known-sparse blocks (`data-sparse="true"`) render empty-state on `insufficient_data:true` in test simulation.

## Domain constraints

- Do NOT change any data binding from V2FE-2..7 — this chunk is integration-only, no new endpoints.
- The dev-mode `?sim_state=` param MUST be gated to localhost only — never expose simulated state on production.
- `STALENESS_THRESHOLDS` in `atlas-states.js` must match §6.3 exactly (set in V2FE-0); do not change the threshold values here.
- Block whitelist exemptions must be declared in `frontend-v2-criteria.yaml`, not hard-coded in the loader script.
- The skeleton height hints should approximate the block's expected content height to minimize layout shift (CLS < 0.1 budget from §8.4).
- No new backend calls or new `atlas_*` tables.
