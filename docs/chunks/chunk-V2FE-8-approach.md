---
chunk: V2FE-8
project: atlas
date: 2026-04-19
---

# V2FE-8 Approach: States rollout integration pass

## Scope
Frontend-only integration pass. No new backend calls, no new tables.

## Data scale
Not applicable — frontend JS file modifications only. No DB queries.

## Chosen approach

### atlas-data.js extensions (3 features)
1. **10s hard cut-off**: Add `setTimeout(10000, ...)` inside `loadBlock()` after skeleton render.
   Store timer on `el._hardCutoffTimer`, clear in both `.then()` success path and `.catch()` error path.
2. **data-as-of sync**: At the VERY START of `_handleSuccess()`, set `el.setAttribute('data-as-of', asOf)`
   from `json._meta.data_as_of`. Log warn if absent. Runs before any state branching.
3. **Dev-mode sim_state**: At the BEGINNING of `loadBlock()` (before skeleton), check `window.location.hostname`
   for localhost/127.0.0.1. Read `?sim_state=` URL param. Branch to appropriate state renderer.
   Gated strictly to localhost — safe for production.

### atlas-states.js improvements (2 changes)
1. **renderError retry button**: Add `<button data-retry="true">` to error card innerHTML.
   Add delegated click handler that calls `window.loadBlock(el)`.
2. **renderSkeleton block-type variants**: Read `el.dataset.blockType` to select chart/table/generic skeleton.
   Chart: square block. Table: 3 full-width lines. Generic: wide/medium/narrow lines (existing default).

## Wiki patterns checked
- `inline-script-to-iife-asset-defer` (V2FE-3..7) — not applicable here, no new IIFE extraction
- `void-sentinel-regex-parser-dom` — not applicable, no HTML changes
- `static-html-mockup-react-spec` — this chunk extends loader/state contracts only

## Existing code reused
- `_handleError(el, err)` — existing function, called from the 10s guard and sim_state=error
- `renderSkeleton/renderEmpty/renderStaleBanner/renderError` — existing functions, extended not replaced
- `test_atlas_data_js.py` — existing pattern for structural Python tests

## Edge cases
- `el._hardCutoffTimer` must be cleared in BOTH the `.then()` success path AND `.catch()` path
  to avoid double-firing after a late TIMEOUT abort
- `data-as-of` set BEFORE state branching so it's always present regardless of insufficient_data/empty/stale/ready
- `sim_state` guard checks `typeof window !== 'undefined'` for non-browser contexts
- `renderError` retry click handler scoped to `el` (closure), no global listener pollution
- renderSkeleton with `el.dataset.blockType` uses conditional to keep default (generic) backward-compatible

## Test strategy
10 structural Python tests in `tests/unit/v2fe/test_states_contract.py`.
Tests use file content reading + regex. No JS runtime needed.
Tests cover: loading/empty/stale/error states, retry affordance, 10s guard, data-as-of, insufficient_data, sim_state, whitelist exemption.

## Expected runtime
File edits: < 1 second. Tests: < 0.5 seconds.
