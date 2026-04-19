---
id: V2FE-2
title: "Today / Pulse page data wiring"
status: PENDING
estimated_hours: 4
deps: [V2FE-0, V2FE-1]
gate_criteria:
  - Every data-block / data-component in §3.1 table carries data-endpoint attribute
  - No data-endpoint points at a 404 (all V2FE-1 endpoints must be live)
  - scripts/check-frontend-criteria.py (V1 gate) still exits 0 for today.html
  - scripts/check-frontend-v2.py --page today exits 0
  - All non-whitelisted blocks reach data-state=ready|stale on live backend
---

## Objective

Wire `frontend/mockups/today.html` from static fixtures to live ATLAS APIs per §3.1. Add `data-endpoint`, `data-params`, `data-fixture`, and `data-data-class` attributes to every block in the §3.1 binding table. Extract any inline rendering JS to `frontend/mockups/assets/today.js`. Import `atlas-data.js` and `atlas-states.js`.

## Punch list

1. [ ] Audit `today.html` against the §3.1 binding table. List every `[data-block]` / `[data-component]` node and its current state (has endpoint? has fixture fallback?).
2. [ ] Add `data-endpoint` + `data-params` to each block per §3.1:
   - `[data-component=regime-banner]` → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"nifty500"}'` `data-data-class="daily_regime"`
   - `[data-component=signal-strip]` → composite; set `data-endpoint="/api/v1/stocks/breadth"` for regime signal, `data-fixture="fixtures/breadth_daily_5y.json"` for offline fallback.
   - `[data-role=breadth-mini]` → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"nifty500","range":"1d","include":"deltas"}'` `data-data-class="eod_breadth"`
   - `[data-role=sector-board]` → `data-endpoint="/api/v1/query/template"` `data-params='{"template":"sector_rotation","params":{"include_gold_rs":true}}'` `data-fixture="fixtures/sector_rrg.json"` `data-data-class="daily_regime"`
   - `[data-role=movers]` (2 blocks, gainers/losers) → `data-endpoint="/api/v1/query/template"` with respective template params
   - `[data-role=fund-strip]` → `data-endpoint="/api/v1/query/template"` `data-params='{"template":"fund_1d_movers","params":{"limit":5}}'` `data-data-class="daily_regime"`
   - `[data-component=divergences-block]` → `data-endpoint="/api/v1/stocks/breadth/divergences"` `data-params='{"universe":"nifty500"}'` `data-data-class="daily_regime"`
   - `[data-component=four-universal-benchmarks]` → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"nifty500","include":"rs,gold_rs,conviction"}'` `data-data-class="daily_regime"`
   - Events overlay in any 5Y chart → `data-endpoint="/api/v1/global/events"` `data-params='{"scope":"india,global"}'` `data-fixture="fixtures/events.json"` `data-data-class="events"`
3. [ ] Whitelist blocks that intentionally have no `data-endpoint`:
   - `[data-component=four-decision-card]` (4×) — V1.1 rec-slots, keep void sentinel as-is, add `data-v2-deferred="true"` attribute.
   - `[data-component=interpretation-sidecar]` — client-derived, add `data-v2-derived="true"`.
4. [ ] Extract inline rendering scripts to `frontend/mockups/assets/today.js`. The inline `<script>` block stays as a thin bootstrap that calls `atlas-data.js` `loadBlock()` for each block.
5. [ ] Add `<script src="assets/atlas-data.js" defer></script>` and `<script src="assets/atlas-states.js" defer></script>` to `<head>` if not already present (step 5 of V2FE-0 may have done this).
6. [ ] Update `data-as-of` attributes to be dynamically set from `_meta.data_as_of` by the loader (V2FE-0 loader handles this; verify the attribute is present on each block).
7. [ ] Verify `universe selector / data_as_of` hero strip is bound to `GET /api/v1/system/data-health` (pick EOD slot) per §3.1.
8. [ ] Write `tests/unit/v2fe/test_today_bindings.py` — ≥6 tests: each test opens `today.html` with `html.parser` and asserts that a specific block carries the correct `data-endpoint` value.
9. [ ] Confirm `scripts/check-frontend-criteria.py --only 'fe-p1-*,fe-g-*,fe-dp-*'` still exits 0 (no V1 regression).

## Exit criteria

- `grep -c "data-endpoint"` on `today.html` returns ≥8 (one per non-whitelisted block in §3.1).
- `pytest tests/unit/v2fe/test_today_bindings.py -v` passes ≥6 tests.
- `scripts/check-frontend-criteria.py --only 'fe-p1-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.
- No `data-endpoint` attribute points to a URL not in §4.1 or §4.2.
- Four-decision-card slots carry `data-v2-deferred="true"` (not `data-endpoint`).

## Domain constraints

- Do NOT hand-edit fixtures — they stay as offline fallback only, per §10.1.
- Do NOT add new DOM elements or change layout — V2 swaps data source, not surface (§0 What V2 is NOT).
- The V1FE void-sentinel DOM contracts must remain intact (no removal of existing `data-block` attrs).
- Rec-slots (`data-slot-id=*`) stay empty — V1.1 rule engine owns them (§0 Non-goals).
- `interpretation-sidecar` stays client-derived — no `data-endpoint` on it.
- Indian formatting and IST dates are enforced by the existing rendering JS, not this chunk.
