---
id: V2FE-6
title: "MF detail (hub-and-spoke MF terminal) page data wiring"
status: PENDING
estimated_hours: 4
deps: [V2FE-0, V2FE-1]
gate_criteria:
  - Every data-block / data-component in §3.4 table carries data-endpoint attribute
  - No data-endpoint points at a 404
  - scripts/check-frontend-criteria.py (V1 gate) still exits 0 for mf-detail.html
  - scripts/check-frontend-v2.py --page mf-detail exits 0
  - returns block binds to GET /api/v1/mf/{id}/nav-history?range=5y&include=rolling_returns
  - hero block binds to GET /api/v1/mf/{id}?include=hero,chips,rs,gold_rs,conviction
---

## Objective

Wire `frontend/mockups/mf-detail.html` from static fixtures to live ATLAS APIs per §3.4. The MF detail page is the hub-and-spoke MF terminal — structurally mirrors stock-detail but with MF-specific blocks (returns, alpha/risk, holdings, sector allocation, weighted technicals, rolling alpha/beta, peers, NAV chart, suitability). Default fund is `PPFAS_FLEXI` (or equivalent `mstar_id`). The `{id}` param is the Morningstar ID read from `data-mstar-id` attribute or URL param.

## Punch list

1. [ ] Audit `mf-detail.html` (1449 lines post V1FE-9) against the §3.4 binding table (16 blocks). List existing `data-block` attrs from V1FE-9 work.
2. [ ] Add `data-mstar-id` attribute to the page root `<main>` with a default Morningstar ID (use PPFAS Flexi Cap Fund's mstar_id from the existing `ppfas_flexi_nav_5y.json` fixture).
3. [ ] Add `data-endpoint` + `data-params` to each block per §3.4:
   - Hero strip → `data-endpoint="/api/v1/mf/${mstar_id}"` `data-params='{"include":"hero,chips,rs,gold_rs,conviction"}'` `data-data-class="daily_regime"`
   - `[data-component=regime-banner]` → composite: `/api/v1/stocks/breadth` (India) + category regime from hero response; primary `data-endpoint` is breadth, `data-data-class="daily_regime"`
   - `[data-component=signal-strip]` → `data-endpoint="/api/v1/mf/${mstar_id}"` `data-params='{"include":"rs_strip"}'` `data-data-class="intraday"`
   - `[data-component=four-universal-benchmarks]` → `data-endpoint="/api/v1/mf/${mstar_id}"` `data-params='{"include":"rs_panels"}'` `data-data-class="daily_regime"`
   - `[data-block=returns]` (Section A) → `data-endpoint="/api/v1/mf/${mstar_id}/nav-history"` `data-params='{"range":"5y","include":"rolling_returns"}'` `data-fixture="fixtures/ppfas_flexi_nav_5y.json"` `data-data-class="daily_regime"`
   - `[data-block=alpha]` (Section B + C) → `data-endpoint="/api/v1/mf/${mstar_id}"` `data-params='{"include":"alpha,risk_metrics"}'` `data-data-class="daily_regime"`
   - `[data-block=holdings]` (Section D) → `data-endpoint="/api/v1/mf/${mstar_id}/holdings"` `data-params='{"limit":"20","include":"concentration"}'` `data-data-class="holdings"`
   - Sector allocation (Section E) → `data-endpoint="/api/v1/mf/${mstar_id}/sectors"` `data-data-class="holdings"`
   - `[data-block=weighted-technicals]` → `data-endpoint="/api/v1/mf/${mstar_id}/weighted-technicals"` `data-data-class="daily_regime"`
   - Rolling alpha/beta (Section F) → `data-endpoint="/api/v1/mf/${mstar_id}"` `data-params='{"include":"rolling_alpha_beta","range":"5y"}'` `data-data-class="daily_regime"`
   - Peer table → `data-endpoint="/api/v1/query"` `data-params='{"entity_type":"mutual_fund","filters":[{"field":"category","op":"=","value":"${category}"}],"fields":["mstar_id","name","category","composite_score","rs_composite","gold_rs_state","risk_grade","returns_grade"],"sort":[{"field":"composite_score","direction":"desc"}],"limit":20}'` `data-data-class="daily_regime"`
   - NAV chart (5Y) → `data-endpoint="/api/v1/mf/${mstar_id}/nav-history"` `data-params='{"range":"5y","include":"benchmark_tri,events"}'` `data-fixture="fixtures/ppfas_flexi_nav_5y.json"` `data-data-class="daily_regime"`
   - Suitability matrix → `data-endpoint="/api/v1/mf/${mstar_id}"` `data-params='{"include":"suitability"}'` `data-data-class="daily_regime"`
   - `[data-component=divergences-block]` → `data-endpoint="/api/v1/mf/${mstar_id}"` `data-params='{"include":"divergences"}'` `data-data-class="daily_regime"`
4. [ ] Whitelist client-derived blocks: `[data-component=signal-playback][data-mode=compact]` (`data-v2-derived="true"`), `[data-component=interpretation-sidecar]` (`data-v2-derived="true"`), rec-slots (`data-v2-deferred="true"`).
5. [ ] Implement `${mstar_id}` and `${category}` substitution in `atlas-data.js` param builder: read from `<main data-mstar-id="...">`. Category is derived from hero response and stored in `window.__mfCategory`.
6. [ ] Peers block defers its load until hero response resolves and `__mfCategory` is set.
7. [ ] Extract inline JS to `frontend/mockups/assets/mf-detail.js`. Add deferred script tags.
8. [ ] Write `tests/unit/v2fe/test_mf_detail_bindings.py` — ≥8 tests covering: hero endpoint with include, nav-history returns endpoint, nav-history chart endpoint, holdings endpoint, alpha/risk endpoint, rolling-alpha-beta endpoint, peers UQL query, divergences include.
9. [ ] Confirm `scripts/check-frontend-criteria.py --only 'fe-p8-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.

## Exit criteria

- `grep -c "data-endpoint"` on `mf-detail.html` returns ≥12.
- `pytest tests/unit/v2fe/test_mf_detail_bindings.py -v` passes ≥8 tests.
- `scripts/check-frontend-criteria.py --only 'fe-p8-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.
- `[data-block=returns]` carries `data-endpoint` pointing to `/api/v1/mf/{id}/nav-history`.
- `[data-block=peers]` carries `data-endpoint="/api/v1/query"` with `entity_type=mutual_fund`.
- 2 rec-slots carry `data-v2-deferred="true"`.

## Domain constraints

- `ppfas_flexi_nav_5y.json` stays as offline fallback only — do not regenerate it in this chunk.
- All V1FE-9 hub-and-spoke void sentinels (8 sentinels in DP COMPONENT SLOTS) must remain intact.
- Kill-list tokens already scrubbed by V1FE-9 must not reappear ("Atlas Verdict", "HOLD / ADD ON DIPS").
- `[data-component=signal-playback][data-mode=compact]` stays client-side simulation. 4 params from the compact sim stay as `data-param-id` (not `id=`), per duplicate-id-sentinel-vs-data-param-id pattern.
- Holdings data class is `holdings` (7d staleness threshold), not `daily_regime` (24h).
- Financial values on backend are Decimal; rendered as rupee lakh/crore (AUM) or percentage by existing renderer.
- No new `atlas_*` tables in this chunk.
