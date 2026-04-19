---
id: V2FE-7
title: "MF rank (4-factor composite ranking) page data wiring"
status: PENDING
estimated_hours: 3
deps: [V2FE-0, V2FE-1]
gate_criteria:
  - Every data-block / data-component in §3.5 table carries data-endpoint attribute
  - No data-endpoint points at a 404
  - scripts/check-frontend-criteria.py (V1 gate) still exits 0 for mf-rank.html
  - scripts/check-frontend-v2.py --page mf-rank exits 0
  - rank-table block binds to POST /api/v1/query/template with template=mf_rank_composite
  - methodology footer binds to GET /api/v1/system/data-health
---

## Objective

Wire `frontend/mockups/mf-rank.html` from static fixtures to live ATLAS APIs per §3.5. This is the lightest-weight page of the 6 (697 lines post V1FE-10) — it has fewer blocks than the hub-and-spoke pages. The key block is the rank table driven by the new `mf_rank_composite` UQL template. Extract inline JS to `frontend/mockups/assets/mf-rank.js`.

## Punch list

1. [ ] Audit `mf-rank.html` against the §3.5 binding table (8 blocks). Identify which have existing `data-block` attrs from V1FE-10.
2. [ ] Add `data-endpoint` + `data-params` to each block per §3.5:
   - `[data-component=regime-banner]` → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"nifty500"}'` `data-data-class="daily_regime"`
   - `[data-component=signal-strip]` → composite breadth + VIX; `data-endpoint="/api/v1/stocks/breadth"` `data-data-class="intraday"`
   - `[data-block=filter-rail]` → multiple sources: categories from `GET /api/v1/mf/categories`, AUM bands static, universe facets from `GET /api/v1/mf/universe?facets=benchmark,age_band,risk_level`. Use `data-endpoint="/api/v1/mf/categories"` as primary, facets loaded separately via `data-endpoint-facets="/api/v1/mf/universe"` (custom multi-source attribute, read by `mf-rank.js`). `data-data-class="daily_regime"`
   - `[data-block=rank-table]` → `data-endpoint="/api/v1/query/template"` `data-params='{"template":"mf_rank_composite","params":{"limit":100}}'` `data-fixture="fixtures/mf_rank_universe.json"` `data-data-class="daily_regime"`
   - `[data-role=rank-sparkline]` (per-fund, batched) → loaded by `mf-rank.js` after rank table renders, using `POST /api/v1/query/template` with `template="mf_rank_history"` and `mstar_ids` array from the rendered table. These are secondary loads, not primary `data-endpoint` blocks.
   - `[data-role=formula]` → static block, no `data-endpoint`. Add `data-v2-static="true"`.
   - `[data-component=interpretation-sidecar]` → client-derived, `data-v2-derived="true"`.
   - `footer.methodology-footer` → `data-endpoint="/api/v1/system/data-health"` `data-params='{"job":"mf_rank"}'` `data-data-class="system"`
3. [ ] Implement filter-rail interaction in `mf-rank.js`: when user changes category/AUM/benchmark filter, re-fire `loadBlock()` on `[data-block=rank-table]` with updated params object (merge base params with filter state).
4. [ ] Implement batched sparkline loading: after rank table renders, collect all `mstar_id` values from rows and fire one `POST /api/v1/query/template` with `template="mf_rank_history"` and `mstar_ids` array. Render sparklines per row.
5. [ ] Extract inline JS to `frontend/mockups/assets/mf-rank.js`. Add deferred script tags.
6. [ ] Write `tests/unit/v2fe/test_mf_rank_bindings.py` — ≥6 tests covering: rank-table endpoint and template name, regime-banner endpoint, methodology-footer endpoint, formula block has no data-endpoint, filter-rail primary endpoint, interpretation-sidecar has no data-endpoint.
7. [ ] Confirm `scripts/check-frontend-criteria.py --only 'fe-p9-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.

## Exit criteria

- `grep -c "data-endpoint"` on `mf-rank.html` returns ≥5 (regime, signal-strip, filter-rail, rank-table, methodology-footer).
- `pytest tests/unit/v2fe/test_mf_rank_bindings.py -v` passes ≥6 tests.
- `scripts/check-frontend-criteria.py --only 'fe-p9-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.
- `[data-block=rank-table]` carries `data-endpoint="/api/v1/query/template"` and `data-params` containing `"template":"mf_rank_composite"`.
- `footer.methodology-footer` carries `data-endpoint="/api/v1/system/data-health"`.
- `[data-role=formula]` has no `data-endpoint` (whitelisted as static).

## Domain constraints

- `mf_rank_universe.json` stays as offline fallback only; do not regenerate in this chunk.
- The 4-factor composite formula display block is **static** — it must never have a `data-endpoint`. Its content is hardcoded HTML.
- Sparkline batching MUST use a single template call with `mstar_ids` array, not N individual calls (N+1 guard).
- Tie-break ordering implemented by existing renderer in V1FE-10 must not be disrupted.
- Filter rail interaction MUST update `data-params` on the rank-table block and call `loadBlock()` again — do not reload the entire page.
- V1FE-10 DOM contracts (composite recomputed from `*_cdf` fields, formula disclosure block, rec-slot `mfrank-screens`) must remain intact.
- No new `atlas_*` tables.
