# ATLAS Frontend V2 — Specification (Stage 2: data wiring)

**Version:** v2.0 (19 Apr 2026). Chunkmaster input for the V2FE slice.
**Predecessor:** `docs/design/frontend-v1-spec.md` (Stage 1, mockups landed
V1FE-1..V1FE-13). Stage 1 is complete: `.quality/report.json` fe dim = 100,
all 10 HTML mockups pass the `frontend-v1-criteria.yaml` gate.
**Scope:** wire 6 deep pages from static fixtures to live ATLAS APIs,
implement the §1.9 states contract, add the staleness/provenance/caching
layer, close 4 backend gaps called out in V1 §15. Preserve every DOM
contract locked by V1FE — no visual drift, no criteria regressions.

**Target pages (locked, 6 of 10):**

1. `today.html`           (Pulse)
2. `explore-country.html` (India deep dive + embedded breadth)
3. `stock-detail.html`    (hub-and-spoke equity terminal)
4. `mf-detail.html`       (hub-and-spoke MF terminal)
5. `mf-rank.html`         (4-factor composite ranking)
6. `breadth.html`         (canonical Breadth Terminal)

**Deferred to Stage 2.5** (explicit, by FM decision 19-Apr-2026):
`portfolios.html`, `lab.html`. Both have live mockups but depend on
unresolved product choices (shadow-NAV methodology signoff; rule engine
V1.1 landing first). They ride a separate chunk slice.

**Out of scope V2 entirely** (deferred to V3+):
`explore-global.html` (4-universal-benchmarks macro dashboard; JIP global
data sparse per `project_jip_empty_tables` memory — USDINR=X has 3 rows,
INDIAVIX lags 4 days, de_adjustment_factors_daily is empty). Revisit
after V11 data enrichment tranche 2. `explore-sector.html` (per-sector
deep dive; scope overlaps stock-detail peers + country sectors RRG,
defer consolidation to V3 hub-and-spoke merge). `index.html` (landing
hub; no data wiring needed).

---

## §0 · Context and non-goals

### What V2 is
- The Stage 2 of the V1 spec's §15 endpoint plan. V1 froze the DOM, V2
  fills it with real JIP-derived data.
- A data-contract delivery. Every `data-block` on every target page
  gains a `data-endpoint` attribute whose resolution produces schema-
  validated bytes.
- The point at which `frontend-v1-criteria.yaml` graduates into a
  live-probe regime — DOM checks stay page-scoped, but every data-block
  now MUST respond 200 with a payload that parses against its paired
  schema under `frontend/mockups/fixtures/schemas/`.
- The state-machine layer: loading skeletons, empty states, stale
  banners, error cards, all per `docs/design/frontend-v1-states.md`.

### What V2 is NOT
- Not a rebuild. The HTML mockups stay the shipped artifact for these
  6 pages — V2 swaps the data source, not the surface. The S1 React
  port (`docs/specs/chunks/s1-*.md`) is a separate track; V2 precedes
  it because the S1 React chunks consume the same endpoints V2 lights
  up, and shipping live APIs first means S1 can mirror the V2
  contract byte-for-byte.
- Not a new design system. `tokens.css` + `components.css` stay locked.
  Every visual change is forbidden in this slice.
- Not V1.1 rule-engine work. `rec-slot` placeholders stay empty. See
  `project_rule_engine_v1_1` memory.
- Not Reports, Watchlist, Monte Carlo standalone. Those are V3.
- Not `Portfolios` or `Lab`. Stage 2.5 owns them.

### Non-goals for this chunk slice
- No new Pydantic response models that duplicate existing V1 shapes.
- No bypass of the API design standard (spec §17 UQL, §18 include
  system, §20 principles). Every new route MUST go through
  `backend/routes/query.py` where the payload fits UQL; bespoke routes
  only for shapes UQL cannot express (charts with denormalised event
  marker overlays, zone-event logs with traceability guarantees).
- No LLM commentary, no AI narrative, no RECOMMEND-tier prose. Same
  invariants as V1.
- No Redis proliferation. Use existing redis hiredis client where
  caching is needed (V7 already wired it for Gold RS); reuse the
  cache-key discipline, do not add a second cache layer.

---

## §1 · Glossary (V2-specific)

| Term | Meaning |
|---|---|
| **block** | A single `data-block="X"` or `data-component="X"` DOM node on a mockup page that corresponds to one data source. V1FE void sentinels MUST have a 1:1 mapping to exactly one endpoint. |
| **endpoint** | Either a FastAPI route (`/api/v1/...`) or a UQL template key (`template: top_rs_gainers`) called via `POST /api/v1/query/template`. |
| **binding** | The resolved attribute triplet on each block: `data-endpoint="/api/v1/..."` + `data-params='{"universe":"nifty500"}'` + `data-fixture="fixtures/breadth_daily_5y.json"` (fallback). |
| **staleness threshold** | Per-data-source max age before the block renders the amber stale banner (per §1.9). Mandatory values in §6.3. |
| **freshness stamp** | `data-as-of` attribute already present on every block from V1FE; V2 extends it to reflect the upstream `_meta.data_as_of` from the API response. |
| **envelope** | Every V2 response MUST include `_meta.data_as_of`, `_meta.source`, `_meta.includes_loaded` (for `include=`), `_meta.staleness_seconds`, and `records`/`series` payload. Spec §18.1. |

---

## §2 · Architectural stance

### 2.1 Keep HTML mockups; inject data via a thin loader

The six target pages are static HTML files under `frontend/mockups/`.
V2 adds a single `frontend/mockups/assets/atlas-data.js` loader whose
job is to:

1. Walk the DOM for every `[data-block]` + `[data-component]` that
   declares a `data-endpoint`.
2. Resolve the endpoint URL (relative `/api/v1/...` in prod, fall back
   to the fixture file locally if offline).
3. `fetch()` with an AbortController, 8s timeout.
4. Render the four canonical states (loading skeleton / empty card /
   stale banner / error card) per `frontend-v1-states.md`.
5. Hand the parsed JSON to the existing per-component renderer (already
   in each page's inline `<script>` or pulled into a shared
   `atlas-components.js`).
6. Update the block's `data-as-of` attribute from `_meta.data_as_of`.

Why keep HTML: the V1FE gate validates DOM contracts against the
static files. Re-routing to React in the same slice triples blast
radius and forks the criteria YAML. V2 stays HTML; S1 will port to
React consuming the V2 endpoints.

### 2.2 No direct SQL in routes

Per CLAUDE.md + api-standard-criteria.yaml. Every new SQL access for
V2 goes through the shared UQL service (`backend/services/uql/`) or a
dedicated per-entity service under `backend/services/`. No route
handler constructs SQL. V2FE-backend chunks MUST extend services, not
routes, when adding filter/aggregation capability.

### 2.3 Include-composable responses

Where V1 §15 mapped a single page to multiple routes, V2 prefers one
entity-detail route with `?include=<modules>` per §18. E.g. stock
detail's hero + chart + RS panel + peer list fetches ONE request:
`GET /api/v1/stocks/HDFCBANK?include=rs,conviction,chart,peers,
corporate_actions,divergences`. `_meta.includes_loaded` proves which
modules resolved. Frontend binding table below records the intended
include set per block.

### 2.4 UQL over bespoke routes for list+aggregate shapes

Today's sector-board, movers, fund-strip — every "sorted/filtered list
of entities" — MUST hit `POST /api/v1/query` or
`POST /api/v1/query/template`, never a new bespoke list route. V2FE-1
will seed templates: `sector_rotation`, `top_rs_gainers`, `top_rs_losers`,
`fund_1d_movers`, `mf_rank_composite`.

### 2.5 Determinism + staleness

Every GET endpoint is deterministic given `(path, query_string, day)`.
Responses carry `_meta.data_as_of` (IST calendar date) and
`_meta.staleness_seconds` (age of underlying JIP tick). Cache layer is
Redis with TTL = staleness_threshold per source (see §6.3). No cache
bypass except via explicit `?fresh=true` (not exposed in mockups).

---

## §3 · Per-page data audit

Format: **block-id** · DOM selector · V1 fixture → V2 endpoint (params,
include set) · staleness threshold · states contract.

Each page's "Blocks deferred to V2.5/V3" section at bottom notes any
V1-spec'd block that this slice explicitly does NOT wire. Those keep
fixture-backed placeholder rendering until their owning slice lands.

### 3.1 `today.html` — Pulse (30-second morning open)

Source: `frontend/mockups/today.html` (1604 lines). V1FE-4 commit a8c0339.

| Block | Selector | V1 fixture | V2 endpoint | Params | Staleness |
|---|---|---|---|---|---|
| regime-banner | `[data-component=regime-banner]` | *(hardcoded)* | `GET /api/v1/stocks/breadth` (regime field) | `universe=nifty500` | 24h |
| signal-strip | `[data-component=signal-strip]` | *(hardcoded)* | `GET /api/v1/stocks/breadth` + `/api/v1/macros/vix` + `/api/v1/macros/fx?pairs=USDINR` + `/api/v1/macros/yield-curve?tenor=10Y` | composite | 1h |
| universe selector / data_as_of | hero strip | — | `GET /api/v1/system/data-health` (pick EOD slot) | — | 6h |
| rrg quartet + gold amplifier | `[data-component=four-universal-benchmarks]` ancestor | — | `GET /api/v1/stocks/breadth?include=rs,gold_rs,conviction` | `universe=nifty500` | 24h |
| breadth mini (3 KPIs) | `[data-role=breadth-mini]` | `breadth_daily_5y.json` (latest row) | `GET /api/v1/stocks/breadth?range=1d&include=deltas` | `universe=nifty500` | 6h |
| sector board | `[data-role=sector-board]` | `sector_rrg.json` | `POST /api/v1/query/template` `{template:"sector_rotation", params:{include_gold_rs:true}}` | returns 11 sectors | 24h |
| movers | `[data-role=movers]` | *(none — hard-coded)* | 2× `POST /api/v1/query/template` `{template:"top_rs_gainers"/"top_rs_losers", params:{limit:10}}` | — | 6h |
| fund strip | `[data-role=fund-strip]` | *(none)* | `POST /api/v1/query/template` `{template:"fund_1d_movers", params:{limit:5}}` | — | 24h |
| divergences-block | `[data-component=divergences-block]` | — | `GET /api/v1/stocks/breadth/divergences` (**new**, §4.2.3) | `universe=nifty500` | 24h |
| interpretation-sidecar | `[data-component=interpretation-sidecar]` | — | *derived from breadth payload client-side* (template string only, AUTO tag) | — | matches source |
| events (for any 5Y overlay) | — | `events.json` | `GET /api/v1/global/events` (**new**, §4.2.2) | `scope=india,global` | 7d |

**Pulse 4-decision cards** (`[data-component=four-decision-card]`, 4×):
remain **empty slots** — bound by V1.1 rule engine, not V2. Keep the
V1FE void sentinels as-is. `data-endpoint` attribute absent is legal
for rec-slots specifically (criteria YAML exemption, §8.2).

**Deferred on this page:** the "11 sector tiles with Gold RS chip" card
grid depends on `sectors_rotation` template returning a `rs_gold` field
per sector. V7 Gold RS is live; template needs the join.

### 3.2 `explore-country.html` — India deep dive

Source: `frontend/mockups/explore-country.html` (1174 lines). V1FE-6
commit ddf3cc8.

| Block | Selector | V1 fixture | V2 endpoint | Params | Staleness |
|---|---|---|---|---|---|
| regime-banner (India-scope) | `[data-component=regime-banner]` | — | `GET /api/v1/stocks/breadth?universe=nifty500` (regime) | — | 24h |
| signal-strip | `[data-component=signal-strip]` | — | composite (breadth + vix + fx) | — | 1h |
| four-universal-benchmarks row (Nifty 500) | `[data-component=four-universal-benchmarks]` | — | `POST /api/v1/query` `{entity_type:"index", filters:[{field:"index_id", op:"=", value:"NIFTY_500"}], include:["rs_msci_world","rs_sp500","rs_nifty50tri","rs_gold"]}` | — | 24h |
| breadth panel 3-KPI | `[data-block=breadth-kpi]` (3×) | `breadth_daily_5y.json` | `GET /api/v1/stocks/breadth?universe=nifty500&range=5y` (latest + deltas) | — | 6h |
| breadth dual-axis-overlay chart | `[data-component=dual-axis-overlay]` | `breadth_daily_5y.json` | `GET /api/v1/stocks/breadth?universe=nifty500&range=5y&include=index_close,zone_bands` | — | 6h |
| signal-history-table (breadth) | `[data-component=signal-history-table]` | `zone_events.json` | `GET /api/v1/stocks/breadth/zone-events?universe=nifty500&range=5y` (**new**, §4.2.1) | — | 24h |
| derivatives (PCR, VIX, max pain) | *(sect)* | — | `GET /api/v1/derivatives/summary` (EXISTS — `backend/routes/derivatives.py`) | — | 1h |
| rates · G-Sec yield curve | — | — | `GET /api/v1/macros/yield-curve?tenors=2Y,10Y,30Y,real` | — | 24h |
| INR (USDINR 5Y + events) | — | — | `POST /api/v1/query {entity_type:"fx_pair", mode:"timeseries", filters:[{field:"pair", op:"=", value:"USDINR"}], fields:["date","close"], time_range:{from:"2021-04-01", to:"today"}}` + `/api/v1/global/events?scope=india` | — | 24h |
| FII / DII flows | `[data-block=flows]` | — | `GET /api/v1/global/flows` (**new**, §4.2.4) | `scope=india&range=5y` | 24h |
| sectors RRG (12 sectors) | `[data-block=sectors-rrg]` | `sector_rrg.json` | `GET /api/v1/sectors/rrg?include=gold_rs,conviction` | — | 24h |
| divergences-block | `[data-component=divergences-block]` | — | `GET /api/v1/stocks/breadth/divergences?universe=nifty500` | — | 24h |
| events overlay | — | `events.json` | `GET /api/v1/global/events?scope=india` | — | 7d |
| signal-playback compact embed | `[data-component=signal-playback][data-mode=compact]` | *(inline)* | *stays client-side simulation*; underlying breadth series from `/api/v1/stocks/breadth` | — | 6h |
| interpretation-sidecar | `[data-component=interpretation-sidecar]` | — | client-derived from breadth + regime | — | — |
| rec-slot country-breadth | — | — | empty (V1.1) | — | — |

### 3.3 `stock-detail.html` — equity hub-and-spoke

Source: `frontend/mockups/stock-detail.html` (1037 lines post V1FE-8).

| Block | Selector | V1 fixture | V2 endpoint | Params | Staleness |
|---|---|---|---|---|---|
| hero (symbol, price, chips) | `[data-block=hero]` | `reliance_close_5y.json` (tail) | `GET /api/v1/stocks/{symbol}?include=price,chips,rs,gold_rs,conviction` | path: `symbol=HDFCBANK` | 1h |
| regime-banner (India + sector) | `[data-component=regime-banner]` | — | composite: `/api/v1/stocks/breadth` (India) + `/api/v1/sectors/rrg` (sector regime derivation) | — | 24h |
| signal-strip (4 readings) | `[data-component=signal-strip]` | — | `GET /api/v1/stocks/{symbol}?include=rs_strip` | — | 1h |
| four-universal-benchmarks | `[data-component=four-universal-benchmarks]` | — | `GET /api/v1/stocks/{symbol}?include=rs_panels` (returns `rs_msci_world`, `rs_sp500`, `rs_nifty50tri`, `rs_gold`) | — | 24h |
| chart-with-events (5Y candle + MAs) | `[class*=chart-with-events]` | `reliance_close_5y.json` | `GET /api/v1/stocks/{symbol}/chart-data?range=5y&overlays=50dma,200dma,events` | — | 6h |
| RS panel (5Y) | right-rail RS card | — | `GET /api/v1/stocks/{symbol}/rs-history?range=5y&include=gold_rs` | — | 24h |
| peers table | `[data-block=peers]` | — | `POST /api/v1/query` `{entity_type:"equity", filters:[{field:"sector", op:"=", value:"<sector>"}], fields:["symbol","rs_composite","gold_rs","momentum","volume","breadth","conviction"], sort:[{field:"rs_composite", direction:"desc"}], limit:15}` | — | 24h |
| fundamentals tab (EPS/PE/ROE/DE/FCF) | — | — | `GET /api/v1/stocks/{symbol}?include=fundamentals` | — | 7d |
| corporate actions | right-rail card | — | `GET /api/v1/stocks/{symbol}?include=corporate_actions&range=5y` | — | 24h |
| insider + bulk/block (events tab) | — | — | `GET /api/v1/insider/{symbol}` (EXISTS — `backend/routes/insider.py`, V11-8) | — | 24h |
| news feed | news tab | — | `GET /api/v1/stocks/{symbol}?include=news&limit=30` | — | 6h |
| divergences-block | `[data-component=divergences-block]` | — | `GET /api/v1/stocks/{symbol}?include=divergences` | — | 24h |
| dual-axis-overlay (RSI/MACD) | `[data-component=dual-axis-overlay]` | — | `GET /api/v1/stocks/{symbol}/chart-data?range=5y&overlays=rsi14,macd` | — | 6h |
| signal-history-table | `[data-component=signal-history-table]` | — | `GET /api/v1/stocks/{symbol}?include=signal_history` | — | 24h |
| signal-playback compact | `[data-component=signal-playback]` | `breadth_daily_5y.json` + `reliance_close_5y.json` | breadth API + chart-data (client-side sim) | — | 6h |
| simulate-this | right-aligned affordance | — | links to `/mockups/lab.html?symbol=HDFCBANK` (deferred to S2.5) | — | — |
| interpretation-sidecar | `[data-component=interpretation-sidecar]` | — | client-derived | — | — |
| rec-slots (technical/fundamental/peer-compare/news/playback) | `[data-slot-id=*]` | — | empty (V1.1) | — | — |

### 3.4 `mf-detail.html` — MF hub-and-spoke

Source: `frontend/mockups/mf-detail.html` (1449 lines post V1FE-9).

| Block | Selector | V1 fixture | V2 endpoint | Params | Staleness |
|---|---|---|---|---|---|
| hero (fund name, AUM, Sharpe, α) | hero strip | — | `GET /api/v1/mf/{mstar_id}?include=hero,chips,rs,gold_rs,conviction` | — | 24h |
| regime-banner (India + category) | `[data-component=regime-banner]` | — | composite: `/api/v1/stocks/breadth` + `/api/v1/mf/{id}?include=category_regime` | — | 24h |
| signal-strip | `[data-component=signal-strip]` | — | `GET /api/v1/mf/{id}?include=rs_strip` | — | 1h |
| four-universal-benchmarks | `[data-component=four-universal-benchmarks]` | — | `GET /api/v1/mf/{id}?include=rs_panels` | — | 24h |
| returns (Section A) | `[data-block=returns]` | `ppfas_flexi_nav_5y.json` | `GET /api/v1/mf/{id}/nav-history?range=5y&include=rolling_returns` | — | 24h |
| alpha / risk (Section B + C) | `[data-block=alpha]` | — | `GET /api/v1/mf/{id}?include=alpha,risk_metrics` (Jensen α, Treynor, IR, capture ratios, vol, max DD, downside dev) | — | 24h |
| holdings (Section D) | `[data-block=holdings]` | — | `GET /api/v1/mf/{id}/holdings?limit=20&include=concentration` | — | 7d |
| sector allocation (Section E) | — | — | `GET /api/v1/mf/{id}/sectors` (EXISTS) | — | 7d |
| weighted technicals | `[data-block=weighted-technicals]` | — | `GET /api/v1/mf/{id}/weighted-technicals` (EXISTS) | — | 24h |
| rolling α/β (Section F) | — | — | `GET /api/v1/mf/{id}?include=rolling_alpha_beta&range=5y` | — | 24h |
| peer table | — | — | `POST /api/v1/query {entity_type:"mutual_fund", filters:[{field:"category", op:"=", value:"<cat>"}], fields:[...], sort:[{field:"composite_score", direction:"desc"}], limit:20}` | — | 24h |
| NAV chart (5Y) | chart embed | `ppfas_flexi_nav_5y.json` | `GET /api/v1/mf/{id}/nav-history?range=5y&include=benchmark_tri,events` | — | 24h |
| suitability matrix | — | — | `GET /api/v1/mf/{id}?include=suitability` | — | 24h |
| signal-playback compact (4 params) | `[data-component=signal-playback]` | `breadth_daily_5y.json` + `ppfas_flexi_nav_5y.json` | breadth API + nav-history (client sim) | — | 24h |
| divergences-block | `[data-component=divergences-block]` | — | `GET /api/v1/mf/{id}?include=divergences` | — | 24h |
| interpretation-sidecar | `[data-component=interpretation-sidecar]` | — | client-derived | — | — |
| rec-slots (alpha-thesis, risk-flag, suitability, playback) | — | — | empty (V1.1) | — | — |

### 3.5 `mf-rank.html` — 4-factor composite

Source: `frontend/mockups/mf-rank.html` (697 lines post V1FE-10).

| Block | Selector | V1 fixture | V2 endpoint | Params | Staleness |
|---|---|---|---|---|---|
| regime-banner (MF-universe-scoped) | `[data-component=regime-banner]` | — | `GET /api/v1/stocks/breadth?universe=nifty500` (regime) | — | 24h |
| signal-strip | `[data-component=signal-strip]` | — | composite (breadth + VIX) | — | 1h |
| filter rail | `[data-block=filter-rail]` | — | `GET /api/v1/mf/categories` (EXISTS) + static AUM bands + `/api/v1/mf/universe?facets=benchmark,age_band,risk_level` | — | 24h |
| rank table | `[data-block=rank-table]` | `mf_rank_universe.json` | `POST /api/v1/query/template {template:"mf_rank_composite", params:{category:[..], aum_band:[..], min_age_years:X, benchmark:X, limit:100}}` (**new template**, §4.3.2) | — | 24h |
| sparkline per fund (rank history) | `[data-role=rank-sparkline]` | *(derived)* | `POST /api/v1/query/template {template:"mf_rank_history", params:{mstar_ids:[..], range:"1y"}}` | batched | 24h |
| formula disclosure | `[data-role=formula]` | *(literal)* | static — no endpoint | — | — |
| interpretation-sidecar | `[data-component=interpretation-sidecar]` | — | client-derived | — | — |
| methodology footer (data_as_of, last rebuild) | `footer.methodology-footer` | — | `GET /api/v1/system/data-health` (pick `mf_rank` job) | — | 6h |

### 3.6 `breadth.html` — canonical Breadth Terminal

Source: `frontend/mockups/breadth.html` (1326 lines post V1FE-11).

| Block | Selector | V1 fixture | V2 endpoint | Params | Staleness |
|---|---|---|---|---|---|
| universe-selector + ma-selector | `[data-role=universe-selector]`, `[data-role=ma-selector]` | static | static pill group | — | — |
| hero (3 headline counts) | `.hero-card` | `breadth_daily_5y.json` (latest) | `GET /api/v1/stocks/breadth?universe=${u}&range=1d&include=counts` | from selectors | 6h |
| regime-banner | `[data-component=regime-banner]` | — | `GET /api/v1/stocks/breadth?universe=${u}&include=regime` | — | 24h |
| signal-strip (4 readings) | `[data-component=signal-strip]` | — | composite | — | 1h |
| 3 KPI cards (21EMA/50DMA/200DMA) | `[data-block=breadth-kpi]` (3×) | `breadth_daily_5y.json` | same `breadth` call | — | 6h |
| oscillator chart (5Y primary) | `[data-block=oscillator]` | `breadth_daily_5y.json` + `events.json` | `GET /api/v1/stocks/breadth?universe=${u}&range=5y&include=index_close,events` | — | 6h |
| ROC panel (5-day rate-of-change) | `.oscillator-panel[data-block=oscillator]` | *(derived)* | same call, client derives ROC from `ema21_count` series | — | 6h |
| zone-reference panel | `[data-block=zone-reference]` | *(derived)* | same call (latest + 60d summary) | — | 6h |
| signal-history-table | `[data-block=signal-history]` | `zone_events.json` | `GET /api/v1/stocks/breadth/zone-events?universe=${u}&range=5y` (**new**, §4.2.1) | — | 24h |
| interpretation-sidecar | `[data-component=interpretation-sidecar]` | — | client-derived from breadth + zone-events | — | — |
| divergences-block | *(right rail)* | — | `GET /api/v1/stocks/breadth/divergences?universe=${u}` (**new**, §4.2.3) | — | 24h |
| signal-playback full (14 params) | `[data-component=signal-playback]` | `breadth_daily_5y.json` + NAV/price (by instrument picker) | breadth API + instrument API (client sim). For shareable runs V3+: `POST /api/v1/simulate/breadth-strategy` (exists partial in `backend/routes/simulate.py`, extend for the 14-param shape). | — | 24h |
| conviction halo on trade points | sim chart annotations | — | derived from `/api/v1/stocks/breadth?include=conviction_series` (**new include**, §4.2.5) | — | 24h |
| methodology footer | — | — | `GET /api/v1/system/data-health?job=breadth_compute` | — | 6h |

---

## §4 · Endpoint registry (V2 authoritative)

### 4.1 Existing routes used as-is (18)

Verified live in `backend/routes/` at HEAD 8bb9bc0. No contract change.

```
GET  /api/v1/stocks/breadth                           # stocks.py
GET  /api/v1/stocks/movers                            # stocks.py
GET  /api/v1/stocks/{symbol}                          # stocks.py (supports ?include=)
GET  /api/v1/stocks/{symbol}/chart-data               # stocks.py
GET  /api/v1/stocks/{symbol}/rs-history               # stocks.py
GET  /api/v1/stocks/universe                          # stocks.py
GET  /api/v1/sectors/rrg                              # sectors.py
GET  /api/v1/mf/universe                              # mf.py
GET  /api/v1/mf/categories                            # mf.py
GET  /api/v1/mf/{id}                                  # mf.py  (?include=)
GET  /api/v1/mf/{id}/nav-history                      # mf.py
GET  /api/v1/mf/{id}/holdings                         # mf.py
GET  /api/v1/mf/{id}/sectors                          # mf.py
GET  /api/v1/mf/{id}/weighted-technicals              # mf.py
GET  /api/v1/mf/{id}/rs-history                       # mf.py
GET  /api/v1/macros/vix                               # macros.py
GET  /api/v1/macros/fx                                # macros.py
GET  /api/v1/macros/yield-curve                       # macros.py
GET  /api/v1/macros/policy-rates                      # macros.py
GET  /api/v1/derivatives/summary                      # derivatives.py
GET  /api/v1/insider/{symbol}                         # insider.py
GET  /api/v1/system/data-health                       # system_data_health.py
POST /api/v1/query                                    # query.py (UQL)
POST /api/v1/query/template                           # query.py
```

### 4.2 New bespoke routes required (5)

Rationale for each: the shape is either (a) a denormalised join of
event markers onto a timeseries (cannot be UQL), (b) a derived log with
traceability guarantees (zone events must match chart annotations 1:1),
or (c) a separate JIP scrape (flows, global events) that needs its own
service.

#### 4.2.1 `GET /api/v1/stocks/breadth/zone-events`

- Owner: `backend/routes/stocks.py`
- Service: `backend/services/breadth_zone_detector.py` (**new**)
- Params: `universe` (enum: nifty50 | nifty500 | nifty_midcap150 | nifty_smallcap250 | sector:<slug>), `range` (1y | 5y | all), `indicator` (21ema | 50dma | 200dma | all, default all)
- Response: schema-identical to `fixtures/schemas/zone_events.schema.json`. MUST include `prior_zone_duration_days` and `thresholds` block.
- Source: derived from `de_equity_technical_daily` breadth counts (already
  what `/stocks/breadth` reads). Edge-triggered detector replays the 5Y
  series and emits every zone entry/exit row. Deterministic.
- Caching: Redis TTL = 24h keyed on `(universe, range, indicator, eod_date)`.

#### 4.2.2 `GET /api/v1/global/events`

- Owner: `backend/routes/global_intel.py`
- Service: `backend/services/event_marker_service.py` (**new**)
- Params: `scope` (csv of `india, global, sector:<slug>`), `range` (default 5y), `categories` (optional csv)
- Response: schema-identical to `fixtures/schemas/events.schema.json`.
- Storage: new `atlas_key_events` table (UUID, date, category, severity, affects jsonb, label, source). Seeded from the V1 hand-curated `events.json` via Alembic migration. Admin-only POST to append (V1.1).
- Caching: 7d TTL (events are slow-moving reference data).

#### 4.2.3 `GET /api/v1/stocks/breadth/divergences`

- Owner: `backend/routes/stocks.py`
- Service: `backend/services/breadth_divergence_detector.py` (**new**)
- Params: `universe`, `window` (days, default 20), `lookback` (months, default 3)
- Response:
  ```
  {
    "_meta": {...},
    "universe": "nifty500",
    "window_days": 20,
    "divergences": [
      { "date": "2026-04-12", "type": "price_strong_breadth_weak", "severity": "high",
        "explanation": "Nifty 500 +2.1% while % above 50-DMA fell from 58% → 47%",
        "evidence": {"price_delta": 0.021, "breadth_delta": -0.11}, "scope": "nifty500" }
    ]
  }
  ```
- Empty case: `divergences: []` plus `_meta.insufficient_data: false`.
- Stale/missing underlying: `_meta.insufficient_data: true` and block MUST render the "insufficient data" branch per §1 Divergences rule.

#### 4.2.4 `GET /api/v1/global/flows`

- Owner: `backend/routes/global_intel.py`
- Service: `backend/services/flows_service.py` (**new**)
- Params: `scope` (csv: `fii_equity, fii_debt, dii_equity, dii_debt`), `range` (default 1y)
- Response: series `{date, fii_equity_net, fii_debt_net, dii_equity_net, dii_debt_net, cumulative_*}` — decimals, INR crore at API boundary.
- Source: JIP `de_fii_dii_daily` (verify table exists; if empty per `project_jip_empty_tables` — route MUST return empty-state with `_meta.insufficient_data: true`).

#### 4.2.5 Extension: `include=conviction_series` on `GET /api/v1/stocks/breadth`

- Not a new route. Adds a new include key returning per-date conviction
  chip state alongside the breadth counts. Needed by breadth.html
  signal-playback halo annotations. Lives in existing breadth service;
  requires joining with `atlas_gold_rs_cache` (V7).

### 4.3 New UQL templates required (5)

Per spec §17.7, adding a template is config + SQL file, not a route
edit. Owner file: `backend/services/uql/templates/`.

| Template | Purpose | Params | Returns |
|---|---|---|---|
| `sector_rotation` | Today sector board; country sectors RRG | `{include_gold_rs?: bool, limit?: int}` | rows: `sector_id, name, rs, rs_gold, momentum, volume, breadth, conviction, rs_spark` |
| `top_rs_gainers` | Today top movers | `{limit?: int=10, universe?: string}` | rows: `symbol, name, sector, delta_pct, vol_ratio, rs_state, gold_rs_state, conviction` |
| `top_rs_losers` | Today bottom movers | same | same |
| `fund_1d_movers` | Today fund strip | `{limit?: int=5, universe?: string}` | rows: `mstar_id, name, category, ret_1d, ret_1m, rs_composite, gold_rs_state` |
| `mf_rank_composite` | MF rank page full table | `{category?: [string], aum_band?: [string], min_age_years?: number, benchmark?: string, sebi_risk?: [string], limit?: int=100, order_by?: enum(composite|returns|risk|resilience|consistency)}` | rows matching `fixtures/schemas/mf_rank_universe.schema.json` funds entries |
| `mf_rank_history` | MF rank sparklines (batched) | `{mstar_ids: [string], range?: string}` | rows: `mstar_id, date, composite_rank` |

---

## §5 · Fixture → endpoint swap table

8 fixtures under `frontend/mockups/fixtures/`. After V2, the fixtures
stay as offline fallback (see §2.1 loader logic) but the canonical
source is the API.

| Fixture | V2 endpoint | Schema stays | Owning chunk |
|---|---|---|---|
| `breadth_daily_5y.json` | `GET /api/v1/stocks/breadth?universe=X&range=5y` | `breadth_daily_5y.schema.json` | V2FE-4 (breadth), V2FE-3 (country) |
| `zone_events.json` | `GET /api/v1/stocks/breadth/zone-events?...` (**new**) | `zone_events.schema.json` | V2FE-1 backend, V2FE-4 wire |
| `events.json` | `GET /api/v1/global/events?scope=...` (**new**) | `events.schema.json` | V2FE-1 backend, all |
| `sector_rrg.json` | `GET /api/v1/sectors/rrg?include=gold_rs,conviction` | `sector_rrg.schema.json` | V2FE-2 (today), V2FE-3 (country) |
| `mf_rank_universe.json` | `POST /api/v1/query/template {template:"mf_rank_composite"}` (**new template**) | `mf_rank_universe.schema.json` | V2FE-1 template, V2FE-7 wire |
| `ppfas_flexi_nav_5y.json` | `GET /api/v1/mf/{id}/nav-history?range=5y` | `nav_series.schema.json` | V2FE-6 |
| `reliance_close_5y.json` | `GET /api/v1/stocks/{symbol}/chart-data?range=5y` | `price_series.schema.json` | V2FE-5 |
| `search_index.json` | `GET /api/v1/search?q=X` — **deferred to S2.5** (no target page in this slice uses search as primary data; top-nav search stays fixture-backed until S2.5) | `search_index.schema.json` | — |

**Byte-identical invariant:** `scripts/seed_fixtures.py` regenerates every
fixture from the live API during V2FE-0 (replacing the current deterministic
RNG seed with a live-capture mode, `--source=api`), writes them back, and
`git diff` MUST be zero against the V1 frozen fixtures except where the
schema was extended in V2 (documented in that chunk's commit).

---

## §6 · States contract (loading / empty / stale / error)

### 6.1 DOM contract

Every block with a `data-endpoint` attribute MUST also expose:

- `data-state="loading|ready|empty|stale|error"` — set by the loader
- `data-as-of="YYYY-MM-DD"` — mirrors `_meta.data_as_of`
- `data-staleness-seconds` — mirrors `_meta.staleness_seconds`
- When `state=error`: `data-error-code="..."` set from response envelope
- When `state=empty`: block MUST render the `empty-state` subtree
  already templated in `components.html`
- When `state=stale`: block MUST render the amber `data-staleness-banner`
  above the block content (already styled in `tokens.css`)

### 6.2 Loader behaviour

`frontend/mockups/assets/atlas-data.js` (**new**, V2FE-0):

```js
async function loadBlock(el) {
  el.dataset.state = "loading";
  renderSkeleton(el);
  try {
    const url = buildUrl(el.dataset.endpoint, JSON.parse(el.dataset.params || "{}"));
    const res = await fetchWithTimeout(url, 8000);
    if (!res.ok) throw new EndpointError(res.status, await res.text());
    const json = await res.json();
    el.dataset.asOf = json._meta.data_as_of;
    el.dataset.stalenessSeconds = json._meta.staleness_seconds;
    if (!hasData(json)) { el.dataset.state = "empty"; renderEmpty(el); return; }
    if (isStale(el, json)) { el.dataset.state = "stale"; renderStaleBanner(el, json); }
    else { el.dataset.state = "ready"; }
    renderBlock(el, json);
  } catch (err) {
    el.dataset.state = "error";
    el.dataset.errorCode = err.code || "UNKNOWN";
    renderError(el, err);
  }
}
```

### 6.3 Staleness thresholds (hardcoded per data class)

Matches `frontend-v1-states.md` and `project_jip_empty_tables` memory.

| Data class | Threshold | Rationale |
|---|---|---|
| Intraday quote (price, VIX, FX 1d) | 1h | Market hours cadence |
| EOD breadth / chart / RS | 6h | JIP EOD+N close |
| Daily regime / sector RRG / gold RS | 24h | Daily compute cadence |
| Fundamentals (EPS, P/E, ROE) | 7d | Quarterly slowness is fine |
| Event markers | 7d | Reference data |
| Holdings | 7d | AMC monthly disclosure |
| System/data-health ping | 6h | Self-reporting cadence |

Known-sparse sources force the block to empty-state branch regardless
of threshold:

- `de_adjustment_factors_daily` (0 rows): any adjustment-factor block empty
- `de_fo_bhavcopy` (0 rows): derivatives subset empty
- `de_global_price_daily` USDINR (3 rows): USDINR FX series uses "3-session sample" banner
- `INDIAVIX` (2 rows / 4d lag): VIX banner reads "VIX updates at EOD+1 typically"

### 6.4 `_meta` envelope contract

Every V2 response MUST return:

```json
{
  "_meta": {
    "data_as_of": "2026-04-18",
    "source": "JIP de_equity_technical_daily",
    "staleness_seconds": 18432,
    "includes_loaded": ["rs", "gold_rs", "conviction"],
    "includes_failed": [],
    "insufficient_data": false,
    "cache_hit": true
  },
  "records": [...]  // or "series", or "divergences", etc.
}
```

---

## §7 · Security / auth / rate-limit

- V2 endpoints are read-only, unauthenticated for public mockup use
  through the existing nginx fronting `atlas.jslwealth.in`. Admin-only
  POST paths (e.g. `/api/v1/intelligence/findings`) already behind the
  `X-Atlas-Admin` header — V2 adds none.
- Rate limit: per-IP 60 req/min via existing middleware. No per-page
  override. Mockup pages batch their calls (≤6 endpoints per page on
  first paint) so one visitor ≈ 6 req.
- CORS: same-origin, no change from V1.
- No new secrets. Redis connection reused from V7. JIP credentials
  reused from existing client.

---

## §8 · Acceptance criteria (V2FE gate)

Encoded in `docs/specs/frontend-v2-criteria.yaml` (to be authored in
V2FE-0). All gate entries are page-scoped except the backend + states
rows (global).

### 8.1 Backend (global, 9 checks)

1. `/api/v1/stocks/breadth/zone-events` returns 200 for `universe=nifty500&range=5y`, payload parses against `zone_events.schema.json`, `_meta.data_as_of` within 24h of wall clock.
2. `/api/v1/global/events` returns 200 for `scope=india,global&range=5y`, payload parses against `events.schema.json`.
3. `/api/v1/stocks/breadth/divergences` returns 200 for `universe=nifty500`, payload shape per §4.2.3.
4. `/api/v1/global/flows` returns 200 (or empty + `insufficient_data:true` when JIP source empty).
5. `POST /api/v1/query/template {template:"sector_rotation"}` returns ≥11 rows with keys `{sector_id, rs, rs_gold, conviction}`.
6. `POST /api/v1/query/template {template:"top_rs_gainers", params:{limit:10}}` returns exactly 10 rows ordered desc by delta_pct.
7. `POST /api/v1/query/template {template:"fund_1d_movers", params:{limit:5}}` returns 5 rows with `rs_composite` + `gold_rs_state`.
8. `POST /api/v1/query/template {template:"mf_rank_composite"}` returns rows parsing against `mf_rank_universe.schema.json`.
9. Every V2 response carries the §6.4 `_meta` envelope (probe: first record `_meta` keys superset of `{data_as_of, source, staleness_seconds, includes_loaded}`).

### 8.2 Per-page DOM binding (page-scoped, 6 pages × N checks)

For each target page:

- Every `data-block` / `data-component` node in §3 table MUST carry
  `data-endpoint` attr whose value matches the audited endpoint.
- Exception list (rec-slots, static formula blocks, client-derived
  sidecars): whitelisted in criteria YAML by DOM selector.
- V1FE void-sentinel DOM checks MUST still pass (no fe-g-* or fe-p*
  regression).

### 8.3 States contract (global)

- For each block, simulate each of the 4 states (loading, empty, stale,
  error) by URL param (`?state=loading` etc., handled by loader in
  dev-mode only) and MUST render the corresponding subtree per §6.1.
- Every block's resolved `data-as-of` matches `_meta.data_as_of` on the
  responding call.
- No block remains in `data-state="loading"` past 10s (hard cut-off →
  error).

### 8.4 Integration / smoke

- Playwright E2E: open each of the 6 pages, wait for `[data-state=ready|stale]` on every non-whitelisted block, assert no `[data-state=error]`. (`tests/e2e/v2fe_*.spec.ts`, new dir, scaffold already present at `tests/e2e/`.)
- Lighthouse: keep V1 performance budget (LCP <2.5s, CLS <0.1). Loader cannot regress more than 200ms on any page.
- Deterministic replay: for a fixed `data_as_of`, two consecutive page loads return byte-identical `_meta` and identical payload records (modulo cache hit flag).

### 8.5 No frontend regressions

- `scripts/check-frontend-criteria.py` (V1 gate) stays green on every page.
- `scripts/check-api-standard.py` stays green (UQL templates + include
  system).
- `scripts/check-spec-coverage.py` stays green (V2 criteria YAML
  registered + cross-linked to `ATLAS-DEFINITIVE-SPEC.md` §15).

---

## §9 · Chunk plan (chunkmaster input)

Dependency graph: V2FE-0 must land first (criteria YAML + loader skeleton);
V2FE-1 lands in parallel (backend gaps, independent of frontend). V2FE-2..
V2FE-7 are per-page and can run in parallel once V2FE-0 + V2FE-1 are done.
V2FE-8 (states rollout) follows all per-page chunks. V2FE-9 (smoke) is
the integration gate at the end.

| ID | Title | Dep | Owner file(s) | Est hrs |
|---|---|---|---|---|
| V2FE-0 | Criteria YAML + loader skeleton + §6 states | — | `docs/specs/frontend-v2-criteria.yaml` (new), `scripts/check-frontend-v2.py` (new), `frontend/mockups/assets/atlas-data.js` (new), `frontend/mockups/assets/atlas-states.js` (new) | 4 |
| V2FE-1 | Backend gaps: zone-events + global-events + divergences + flows + `mf_rank_composite` template + `conviction_series` include | — | `backend/routes/stocks.py`, `backend/routes/global_intel.py`, `backend/services/breadth_zone_detector.py`, `backend/services/breadth_divergence_detector.py`, `backend/services/event_marker_service.py`, `backend/services/flows_service.py`, `backend/services/uql/templates/*.sql`, Alembic migration for `atlas_key_events` | 10 |
| V2FE-2 | Today / Pulse wiring | V2FE-0, V2FE-1 | `frontend/mockups/today.html`, `frontend/mockups/assets/today.js` | 4 |
| V2FE-3 | Explore · Country wiring | V2FE-0, V2FE-1 | `frontend/mockups/explore-country.html`, `frontend/mockups/assets/explore-country.js` | 4 |
| V2FE-4 | Breadth Terminal wiring | V2FE-0, V2FE-1 | `frontend/mockups/breadth.html`, `frontend/mockups/assets/breadth.js` (extract from inline) | 4 |
| V2FE-5 | Stock detail wiring | V2FE-0, V2FE-1 | `frontend/mockups/stock-detail.html`, `frontend/mockups/assets/stock-detail.js` | 4 |
| V2FE-6 | MF detail wiring | V2FE-0, V2FE-1 | `frontend/mockups/mf-detail.html`, `frontend/mockups/assets/mf-detail.js` | 4 |
| V2FE-7 | MF rank wiring | V2FE-0, V2FE-1 | `frontend/mockups/mf-rank.html`, `frontend/mockups/assets/mf-rank.js` | 3 |
| V2FE-8 | States rollout (loading/empty/stale/error across all 6 pages) + staleness banners per §6.3 | V2FE-2..V2FE-7 | all 6 pages, `atlas-states.js` | 3 |
| V2FE-9 | Integration gate: Playwright E2E + Lighthouse regression + API-standard + spec-coverage | all prior | `tests/e2e/v2fe_*.spec.ts`, `.quality/checks.py` dim update | 3 |

Total: ~43 hrs, 10 chunks.

---

## §10 · Migration notes for chunk authors

1. **Do not hand-edit fixtures during V2.** Any fixture update happens
   via the `seed_fixtures.py --source=api` path, and only once the
   backing endpoint is live + schema-parity-validated. This preserves
   the V1FE byte-identical fixture regen invariant (`project_v1fe2_component_gallery` memory).
2. **Do not add a bespoke route where UQL fits.** Grep for `@router.get` during review; anything returning a filtered list of entities MUST use `query.py` or a template, per api-standard-criteria.yaml `uql-01` / `uql-03`.
3. **Respect the "backend first always" Four Laws.** V2FE-1 lands before any per-page wiring chunk. No frontend commit should ship with a `data-endpoint` pointing at a 404.
4. **Preserve void sentinels.** V1FE DOM contracts are ratcheted. The V2 loader MUST read `data-block` attrs that already exist; if a page needs a new block, it goes through a V1FE-15 follow-up chunk, not a V2 chunk.
5. **Read `project_jip_empty_tables` before any data chunk.** Any block bound to a known-sparse source MUST default to empty-state + stale banner, not error state. The gate treats "insufficient_data: true" as ready, not error.
6. **Idempotency on the backend.** All new services MUST be pure functions of `(inputs, eod_date)`. No writes outside `atlas_key_events` (event marker table) during read-path requests.
7. **Post-chunk sync invariant (CLAUDE.md).** Every V2FE chunk DONE runs `scripts/post-chunk.sh <id>`: git push + backend service restart + smoke probe + `/forge-compile` + memory sync.

---

## §11 · Explicitly deferred

### Stage 2.5 (next slice after V2)
- `portfolios.html` — shadow-NAV methodology needs FM signoff.
- `lab.html` — depends on V1.1 rule engine landing.
- `/api/v1/search?q=X` — global search backing; fixture until S2.5.
- Simulation shareable runs (`POST /api/v1/simulate/breadth-strategy` full 14-param).

### V3+
- `explore-global.html` wiring (global JIP sources sparse; wait for V11 enrichment tranche 2).
- `explore-sector.html` full wiring (wait for hub-and-spoke merge).
- Reports page (V3 dedicated slice).
- Watchlist + TradingView 2-way (V3+).
- Market Sentiment standalone page (V3+ consolidation).
- Instrument Deep Dive unified hub (V3 merges stock-detail + mf-detail).
- LLM / AI narrative for interpretation sidecars (forever banned in current design; revisit iff design principles change).

---

## §12 · Out of scope (forever)

- LLM commentary anywhere. Sidecars stay templated, `AUTO` tagged.
- RECOMMEND-tier prose without rule engine backing. V1.1 owns that.
- Dark mode. Locked light system stays.
- Duplicating SQL in route handlers. Services or UQL templates only.
- Rewriting the 6 mockups as React in this slice. That is S1.

---

**End of V2 spec.** Feed to chunkmaster; expect 10 chunks V2FE-0..V2FE-9.
