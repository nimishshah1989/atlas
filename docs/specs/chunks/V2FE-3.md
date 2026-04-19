---
id: V2FE-3
title: "Explore · Country (India deep dive) page data wiring"
status: PENDING
estimated_hours: 4
deps: [V2FE-0, V2FE-1]
gate_criteria:
  - Every data-block / data-component in §3.2 table carries data-endpoint attribute
  - No data-endpoint points at a 404
  - scripts/check-frontend-criteria.py (V1 gate) still exits 0 for explore-country.html
  - scripts/check-frontend-v2.py --page explore-country exits 0
  - breadth panel 3-KPI block resolves data-state=ready|stale on live backend
---

## Objective

Wire `frontend/mockups/explore-country.html` from static fixtures to live ATLAS APIs per §3.2. Add `data-endpoint`, `data-params`, `data-fixture`, and `data-data-class` attributes to every block in the §3.2 binding table. Extract inline JS to `frontend/mockups/assets/explore-country.js`.

## Punch list

1. [ ] Audit `explore-country.html` against the §3.2 binding table (15 blocks). Identify which already have `data-endpoint` from V1FE work and which are new.
2. [ ] Add `data-endpoint` + `data-params` to each block per §3.2:
   - `[data-component=regime-banner]` → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"nifty500"}'` `data-data-class="daily_regime"`
   - `[data-component=signal-strip]` → composite binding; primary endpoint `/api/v1/stocks/breadth`, fixture fallback
   - `[data-component=four-universal-benchmarks]` → `data-endpoint="/api/v1/query"` `data-params='{"entity_type":"index","filters":[{"field":"index_id","op":"=","value":"NIFTY_500"}],"include":["rs_msci_world","rs_sp500","rs_nifty50tri","rs_gold"]}'` `data-data-class="daily_regime"`
   - `[data-block=breadth-kpi]` (3×) → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"nifty500","range":"5y"}'` `data-fixture="fixtures/breadth_daily_5y.json"` `data-data-class="eod_breadth"`
   - `[data-component=dual-axis-overlay]` → `data-endpoint="/api/v1/stocks/breadth"` `data-params='{"universe":"nifty500","range":"5y","include":"index_close,zone_bands"}'` `data-fixture="fixtures/breadth_daily_5y.json"` `data-data-class="eod_breadth"`
   - `[data-component=signal-history-table]` → `data-endpoint="/api/v1/stocks/breadth/zone-events"` `data-params='{"universe":"nifty500","range":"5y"}'` `data-fixture="fixtures/zone_events.json"` `data-data-class="daily_regime"`
   - Derivatives block → `data-endpoint="/api/v1/derivatives/summary"` `data-data-class="intraday"` (note: `de_fo_bhavcopy` is empty — block will receive `insufficient_data:true` and render empty-state)
   - Yield curve → `data-endpoint="/api/v1/macros/yield-curve"` `data-params='{"tenors":"2Y,10Y,30Y,real"}'` `data-data-class="daily_regime"`
   - INR chart → UQL query for USDINR timeseries; note USDINR has only 3 rows — block will render "3-session sample" banner from insufficient_data guard
   - `[data-block=flows]` → `data-endpoint="/api/v1/global/flows"` `data-params='{"scope":"india","range":"5y"}'` `data-data-class="daily_regime"`
   - `[data-block=sectors-rrg]` → `data-endpoint="/api/v1/sectors/rrg"` `data-params='{"include":"gold_rs,conviction"}'` `data-fixture="fixtures/sector_rrg.json"` `data-data-class="daily_regime"`
   - `[data-component=divergences-block]` → `data-endpoint="/api/v1/stocks/breadth/divergences"` `data-params='{"universe":"nifty500"}'` `data-data-class="daily_regime"`
   - Events overlay → `data-endpoint="/api/v1/global/events"` `data-params='{"scope":"india"}'` `data-fixture="fixtures/events.json"` `data-data-class="events"`
3. [ ] Whitelist client-derived blocks: `[data-component=interpretation-sidecar]` (add `data-v2-derived="true"`), `[data-component=signal-playback][data-mode=compact]` (stays client-side sim, add `data-v2-derived="true"`), rec-slot (add `data-v2-deferred="true"`).
4. [ ] Add known-sparse-source `data-sparse="true"` attribute to derivatives block and INR block to signal to the loader that `insufficient_data:true` is the expected steady-state, not an error.
5. [ ] Extract inline JS to `frontend/mockups/assets/explore-country.js`; add deferred script tags for `atlas-data.js` and `atlas-states.js`.
6. [ ] Write `tests/unit/v2fe/test_explore_country_bindings.py` — ≥6 tests asserting `data-endpoint` values on key blocks.
7. [ ] Confirm `scripts/check-frontend-criteria.py --only 'fe-p5-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.

## Exit criteria

- `grep -c "data-endpoint"` on `explore-country.html` returns ≥10.
- `pytest tests/unit/v2fe/test_explore_country_bindings.py -v` passes ≥6 tests.
- `scripts/check-frontend-criteria.py --only 'fe-p5-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.
- Derivatives block carries `data-sparse="true"` and a whitelisted entry in the V2 criteria YAML.
- INR block carries `data-sparse="true"` with appropriate note about 3-row dataset.

## Domain constraints

- Do NOT hand-edit fixtures. Fixture files stay as offline fallback (§10.1).
- Do NOT change layout or visual design — V2 swaps data only.
- `de_fo_bhavcopy` is 0 rows: derivatives block MUST be tagged as sparse; renders empty-state not error.
- USDINR has only 3 rows: INR chart block MUST be tagged sparse; renders "3-session sample" banner.
- All V1FE void-sentinel DOM contracts preserved.
- Rec-slot `country-breadth` stays empty (V1.1).
- `signal-playback compact` stays client-side simulation — do not add a `data-endpoint` to it.
