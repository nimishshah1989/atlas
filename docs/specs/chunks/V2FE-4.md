---
id: V2FE-4
title: "Breadth Terminal page data wiring"
status: PENDING
estimated_hours: 4
deps: [V2FE-0, V2FE-1]
gate_criteria:
  - Every data-block / data-component in §3.6 table carries data-endpoint attribute
  - No data-endpoint points at a 404
  - scripts/check-frontend-criteria.py (V1 gate) still exits 0 for breadth.html
  - scripts/check-frontend-v2.py --page breadth exits 0
  - oscillator chart block resolves data-state=ready|stale on live backend
  - zone-events signal-history-table block binds to /api/v1/stocks/breadth/zone-events
---

## Objective

Wire `frontend/mockups/breadth.html` from static fixtures to live ATLAS APIs per §3.6. The Breadth Terminal has the richest block inventory of all 6 pages (14 blocks including dynamic universe/MA selectors). Extract the substantial inline JS to `frontend/mockups/assets/breadth.js` so the HTML stays readable and the loader integration is clean.

## Punch list

1. [ ] Audit `breadth.html` against the §3.6 binding table (14 blocks). The universe selector (`[data-role=universe-selector]`) and MA selector (`[data-role=ma-selector]`) are **static pill groups** — no `data-endpoint`, but their selected value is read by other blocks as the `universe` / `indicator` param.
2. [ ] Implement param injection in `atlas-data.js` (or `breadth.js`): when a universe-selector or ma-selector pill changes, re-fire `loadBlock()` on all blocks that reference `${universe}` or `${indicator}` in their `data-params`. Store selected values as `window.__breadthUniverse` and `window.__breadthIndicator`.
3. [ ] Add `data-endpoint` + `data-params` to each block per §3.6:
   - `.hero-card` (3 headline counts) → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"${universe}","range":"1d","include":"counts"}'` `data-data-class="eod_breadth"`
   - `[data-component=regime-banner]` → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"${universe}","include":"regime"}'` `data-data-class="daily_regime"`
   - `[data-component=signal-strip]` → composite, primary breadth endpoint
   - `[data-block=breadth-kpi]` (3×) → same breadth call (21EMA/50DMA/200DMA share one fetch, client slices)
   - `[data-block=oscillator]` (primary 5Y chart) → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"${universe}","range":"5y","include":"index_close,events"}'` `data-fixture="fixtures/breadth_daily_5y.json"` `data-data-class="eod_breadth"`
   - ROC panel → same call as oscillator (client derives 5-day ROC from `ema21_count` series)
   - Zone reference panel → same call (client uses latest + 60d summary)
   - `[data-block=signal-history]` → `data-endpoint="/api/v1/stocks/breadth/zone-events"` `data-params='{"universe":"${universe}","range":"5y"}'` `data-fixture="fixtures/zone_events.json"` `data-data-class="daily_regime"`
   - `[data-component=divergences-block]` (right rail) → `data-endpoint="/api/v1/stocks/breadth/divergences"` `data-params='{"universe":"${universe}"}'` `data-data-class="daily_regime"`
   - Conviction halo on sim chart → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"${universe}","include":"conviction_series"}'` `data-data-class="daily_regime"`
   - Methodology footer → `data-endpoint="/api/v1/system/data-health"` `data-params='{"job":"breadth_compute"}'` `data-data-class="system"`
4. [ ] `[data-component=signal-playback]` — full 14-param simulator stays client-side; breadth series comes from the oscillator block's already-fetched payload (no second fetch). Add `data-v2-derived="true"`. For V3+ shareable runs: leave `data-endpoint` absent with a `<!-- TODO V3: POST /api/v1/simulate/breadth-strategy -->` comment.
5. [ ] Extract inline JS from `breadth.html` to `frontend/mockups/assets/breadth.js`. The inline `<script>` becomes a thin bootstrap that calls `atlas-data.js` after DOMContentLoaded. All chart rendering (Recharts / D3) stays in `breadth.js`.
6. [ ] Add deferred script tags for `atlas-data.js` and `atlas-states.js`.
7. [ ] Implement `${universe}` / `${indicator}` template substitution in the param object at `loadBlock()` time, reading from `window.__breadthUniverse` defaults to `"nifty500"`.
8. [ ] Write `tests/unit/v2fe/test_breadth_bindings.py` — ≥8 tests covering: oscillator block endpoint, zone-events endpoint, divergences endpoint, conviction_series include, hero-card endpoint, methodology footer endpoint, regime-banner endpoint, signal-history endpoint.
9. [ ] Confirm `scripts/check-frontend-criteria.py --only 'fe-p10-*,fe-p10_5-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.

## Exit criteria

- `grep -c "data-endpoint"` on `breadth.html` returns ≥9.
- `pytest tests/unit/v2fe/test_breadth_bindings.py -v` passes ≥8 tests.
- `scripts/check-frontend-criteria.py --only 'fe-p10-*,fe-p10_5-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.
- `[data-block=signal-history]` carries `data-endpoint="/api/v1/stocks/breadth/zone-events"`.
- Universe-selector pill change triggers re-load of all universe-dependent blocks (verified by test or comment).

## Domain constraints

- Do NOT modify the 14-param signal-playback simulator inputs (`data-param-id="i_*"`). V1FE-11 locked those IDs and duplicate-id-sentinel-vs-data-param-id pattern mandates they stay as `data-param-id`, not `id=`.
- Fixture files remain untouched as offline fallback only.
- `breadth.html` has 1326 lines; keep the HTML footprint close to current. JS extraction to `breadth.js` is the right mechanism to control line count.
- Do NOT add a new bespoke route for the universe-selector response. The selector is static HTML — only the downstream blocks need endpoints.
- All V1FE `fe-p10-*` and `fe-p10_5-*` DOM contracts (14 sim-param IDs, zone-event dots, 3 KPI cards) must remain intact.
- 3 rec-slots stay empty (V1.1). Do not add `data-endpoint` to them.
