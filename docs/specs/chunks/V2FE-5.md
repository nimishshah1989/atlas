---
id: V2FE-5
title: "Stock detail (hub-and-spoke equity terminal) page data wiring"
status: PENDING
estimated_hours: 4
deps: [V2FE-0, V2FE-1]
gate_criteria:
  - Every data-block / data-component in §3.3 table carries data-endpoint attribute
  - No data-endpoint points at a 404
  - scripts/check-frontend-criteria.py (V1 gate) still exits 0 for stock-detail.html
  - scripts/check-frontend-v2.py --page stock-detail exits 0
  - hero block resolves data-state=ready|stale on live backend for default symbol HDFCBANK
  - peers table block binds to POST /api/v1/query with entity_type=equity
---

## Objective

Wire `frontend/mockups/stock-detail.html` from static fixtures to live ATLAS APIs per §3.3. The stock detail page is the hub-and-spoke equity terminal — it has the largest `include=` surface of any page (hero, chart, RS, peers, fundamentals, corporate actions, news, divergences, signal history, conviction, dual-axis). The default symbol is `HDFCBANK`; the `{symbol}` path variable must be readable from `window.location.search` or a `data-symbol` attribute on the page root.

## Punch list

1. [ ] Audit `stock-detail.html` against the §3.3 binding table (17 blocks). Note which already have `data-block` attrs from V1FE-8.
2. [ ] Add `data-symbol` attribute to the page root `<main>` or `<body>` with value `HDFCBANK`. The loader reads this as the default `{symbol}` and overrides with `?symbol=X` URL param if present.
3. [ ] Add `data-endpoint` + `data-params` to each block per §3.3:
   - `[data-block=hero]` → `data-endpoint="/api/v1/stocks/${symbol}"` `data-params='{"include":"price,chips,rs,gold_rs,conviction"}'` `data-fixture="fixtures/reliance_close_5y.json"` `data-data-class="intraday"`
   - `[data-component=regime-banner]` → composite; primary `/api/v1/stocks/breadth` + `/api/v1/sectors/rrg` data joined client-side; set `data-endpoint` to breadth and carry sector context separately `data-data-class="daily_regime"`
   - `[data-component=signal-strip]` → `data-endpoint="/api/v1/stocks/${symbol}"` `data-params='{"include":"rs_strip"}'` `data-data-class="intraday"`
   - `[data-component=four-universal-benchmarks]` → `data-endpoint="/api/v1/stocks/${symbol}"` `data-params='{"include":"rs_panels"}'` `data-data-class="daily_regime"`
   - Chart with events (5Y candle + MAs) → `data-endpoint="/api/v1/stocks/${symbol}/chart-data"` `data-params='{"range":"5y","overlays":"50dma,200dma,events"}'` `data-fixture="fixtures/reliance_close_5y.json"` `data-data-class="eod_breadth"`
   - RS panel (5Y right-rail) → `data-endpoint="/api/v1/stocks/${symbol}/rs-history"` `data-params='{"range":"5y","include":"gold_rs"}'` `data-data-class="daily_regime"`
   - `[data-block=peers]` → `data-endpoint="/api/v1/query"` `data-params='{"entity_type":"equity","filters":[{"field":"sector","op":"=","value":"${sector}"}],"fields":["symbol","rs_composite","gold_rs","momentum","volume","breadth","conviction"],"sort":[{"field":"rs_composite","direction":"desc"}],"limit":15}'` `data-data-class="daily_regime"`
   - Fundamentals tab → `data-endpoint="/api/v1/stocks/${symbol}"` `data-params='{"include":"fundamentals"}'` `data-data-class="fundamentals"`
   - Corporate actions → `data-endpoint="/api/v1/stocks/${symbol}"` `data-params='{"include":"corporate_actions","range":"5y"}'` `data-data-class="daily_regime"`
   - Insider + bulk/block → `data-endpoint="/api/v1/insider/${symbol}"` `data-data-class="daily_regime"`
   - News feed → `data-endpoint="/api/v1/stocks/${symbol}"` `data-params='{"include":"news","limit":"30"}'` `data-data-class="eod_breadth"`
   - `[data-component=divergences-block]` → `data-endpoint="/api/v1/stocks/${symbol}"` `data-params='{"include":"divergences"}'` `data-data-class="daily_regime"`
   - Dual-axis overlay (RSI/MACD) → `data-endpoint="/api/v1/stocks/${symbol}/chart-data"` `data-params='{"range":"5y","overlays":"rsi14,macd"}'` `data-data-class="eod_breadth"`
   - `[data-component=signal-history-table]` → `data-endpoint="/api/v1/stocks/${symbol}"` `data-params='{"include":"signal_history"}'` `data-data-class="daily_regime"`
4. [ ] Whitelist blocks with no `data-endpoint`:
   - `[data-component=signal-playback][data-mode=compact]` — client-side sim, `data-v2-derived="true"`.
   - simulate-this affordance → static link to `lab.html?symbol=${symbol}`, `data-v2-deferred="true"`.
   - `[data-component=interpretation-sidecar]` — client-derived, `data-v2-derived="true"`.
   - All rec-slots (`[data-slot-id=*]`) — V1.1, `data-v2-deferred="true"`.
5. [ ] Implement `${symbol}` substitution in `atlas-data.js` param builder: read `data-symbol` from `<main data-symbol="HDFCBANK">` and substitute `${symbol}` in all `data-params` strings.
6. [ ] Similarly implement `${sector}` substitution: the hero response `_meta` or `records[0].sector` field populates `window.__stockSector`; peers block defers its load until hero is done and sector is known.
7. [ ] Extract inline JS to `frontend/mockups/assets/stock-detail.js`. Add deferred script tags.
8. [ ] Write `tests/unit/v2fe/test_stock_detail_bindings.py` — ≥8 tests covering: hero endpoint, chart-data endpoint, rs-history endpoint, peers UQL query, divergences include, fundamentals include, signal-history include, insider endpoint.
9. [ ] Confirm `scripts/check-frontend-criteria.py --only 'fe-p7-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.

## Exit criteria

- `grep -c "data-endpoint"` on `stock-detail.html` returns ≥12.
- `pytest tests/unit/v2fe/test_stock_detail_bindings.py -v` passes ≥8 tests.
- `scripts/check-frontend-criteria.py --only 'fe-p7-*,fe-g-*,fe-dp-*,fe-mob-*'` exits 0.
- `[data-block=peers]` carries `data-endpoint="/api/v1/query"` with `entity_type=equity` in `data-params`.
- 3 rec-slots carry `data-v2-deferred="true"`.
- `simulate-this` affordance links to `lab.html?symbol=...` (not a backend endpoint).

## Domain constraints

- Do NOT modify the hub-and-spoke navigation or tab structure locked by V1FE-8.
- `{symbol}` is always a path variable — never a query param for the primary stock endpoint.
- Sector derivation for peers query is a client-side step reading hero response; no extra backend call.
- All financial values in rendered output: `Decimal` on backend, rendered as rupee lakh/crore in Indian notation by existing renderer.
- `de_adjustment_factors_daily` is 0 rows — if any chart block requests adjusted prices, it must handle `insufficient_data:true` gracefully.
- V1FE void-sentinel pattern: all existing `data-block` void sentinels from V1FE-8 must remain.
- 7 tabs and 3 rec-slots DOM contract locked by V1FE-8 must not regress.
