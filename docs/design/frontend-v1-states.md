---
title: ATLAS Frontend V1 — Empty, Loading, Stale, Error States
status: draft (slated for §1.9 of frontend-v1-spec.md)
last-updated: 2026-04-18
owner: frontend-v1
---

# §1.9 · Empty, loading, stale, and error states

A data platform is judged on what it shows when the data is missing,
late, or broken, not on what it shows on a perfect day. Multiple JIP
source tables are known to be empty or stale as of V11-5 — any hero
KPI chip on Today that binds to `de_adjustment_factors_daily`,
`de_global_price_daily` (USDINR), or `de_fo_bhavcopy` will render
broken unless we spec exact handling.

Global rule (from `financial-domain.md`): NULL in a financial calc must
produce NULL, not 0 or NaN. Every API response must carry
`data_as_of` timestamp + staleness indicator. This section translates
those backend rules into mandatory UI states.

---

## 1.9.1 Four canonical non-happy states

Every data-bound block on every page MUST handle all four. Never
collapse them into "loading" or "error" — they are distinct.

### Loading

**What it means:** Data is en-route. The request has been made, the
response has not arrived. Normal happy-path transient (typically
<800ms, bounded at 5s before becoming "error").

**Visual treatment:**
- Skeleton screen, not spinner (rule from `frontend-viz.md`:
  "Loading: skeleton screens, not spinners")
- Skeleton shape matches the final component silhouette (KPI tile,
  chart, table row) — not a generic shimmering rectangle
- Pulse animation: 1.4s ease-in-out, `opacity 0.4 → 0.8 → 0.4`; respects
  `prefers-reduced-motion` (static muted grey if reduced)
- Skeleton colour: `--bg-inset` (`#F2F4F7`)

**Copy:** No copy. Skeleton is silent.

**Accessibility:** Container has `aria-busy="true"` during loading. Drop
the attribute when data loads.

**Design-principles.md reference:** §1 (grey-on-white surface), §7
(motion budget).

### Empty

**What it means:** The request succeeded and returned zero rows. This
is a legitimate no-data case — not an error. Examples: "no corporate
actions in this window", "no sells → no realised gains", "no funds
match your filter".

**Visual treatment:**
- Neutral illustration NOT used (we're not a consumer app). Instead: a
  neutral grey block with a single-line message, icon optional (20×20
  SVG, `currentColor`, `--text-tertiary`)
- Block height matches what the component would have been (don't
  collapse the layout — the FM is expecting this space)

**Copy conventions (see §1.9.5 for full list):**
- Lead with the fact: "No corporate actions in the selected window."
- Offer the next move, if any: "Widen the date range or pick another
  symbol."
- No apology ("Sorry..."), no exclamation marks

**Accessibility:** `role="status"` on the empty block. Empty state
announced via `aria-live="polite"` once.

**Design-principles.md reference:** §6 (reading primitive — every block
carries a reading, even if the reading is "nothing here").

### Stale

**What it means:** Data exists but is older than the category's
freshness expectation (see §1.9.2 threshold table). The block renders
normally but is decorated with a freshness indicator.

**Visual treatment:**
- Normal component renders as usual with all values
- **Amber pill** (`.freshness-pill.freshness-pill--amber`) in the
  top-right of the card: `"as of 14-Apr · 4 sessions old"`
- Source attribution footer (`data-source-note`) shows the full
  details: `"Source: JIP de_global_price_daily · as of 14-Apr-2026
  16:05 IST · next refresh: 18-Apr EOD"`
- If stale crosses the **red threshold** (see §1.9.2), pill switches to
  red and the component adds a top-border accent in `--rag-red-500`

**Copy:** Amber: `"Data lag: N days"`. Red: `"Feed delayed: last
update N days ago"`.

**Accessibility:** Pill has `role="status"` and `aria-label` with the
full staleness text.

**Design-principles.md reference:** §2 (RAG is never decorative — amber
means "this needs a decision").

### Error

**What it means:** The data fetch failed. HTTP 5xx, network timeout,
schema mismatch, or the backend returned a structured error payload
(e.g. the inline DB health gate's `{"reason": "..."}` 503).

**Visual treatment:**
- Red-bordered card (`--rag-red-500` top border, 3px) replaces the
  component
- Error icon (20×20 alert triangle, `--rag-red-700`)
- One-line error summary in body text
- One-line secondary: the error code and retry guidance
- "Retry" button (primary, petrol) + "Report" link (opens pre-filled
  bug-report with page + block + error code in URL params)

**Copy conventions (see §1.9.5 for full list):**
- Declarative, no apology: `"Data feed unavailable · last seen 14:00
  IST · retry"`
- Always include: **what**, **when last seen**, **action**
- Never "Oops!", "Sorry!", "Something went wrong"

**Accessibility:** Error block has `role="alert"`. Error summary text
announced immediately on mount. "Retry" button autofocused when it's
the only action.

**Design-principles.md reference:** §2 (RAG — red means breach/alert),
§6 (every block carries a reading — error is a reading).

---

## 1.9.2 Staleness thresholds per data category

Every JIP / ATLAS data category has a known update cadence. The
thresholds below determine when a block goes amber vs red. Thresholds
measured as **business days or calendar days as specified**, not hours,
because data arrival is EOD-batched except where noted.

| Category | JIP table | Expected freshness | Amber threshold | Red threshold | Permanent note |
|---|---|---|---|---|---|
| EOD stock prices | `de_stock_price_daily` | Same-day by 17:30 IST | > 1 trading day | > 3 trading days | — |
| MF NAV | `de_mf_nav_daily` | T+1 by 21:00 IST | > 2 calendar days | > 5 calendar days | — |
| Index daily | `de_index_daily` | Same-day by 17:30 IST | > 1 trading day | > 3 trading days | — |
| Sector breadth | derived from `de_stock_price_daily` | Same-day by 18:00 IST | > 1 trading day | > 3 trading days | — |
| India VIX | `de_volatility_index` (INDIAVIX) | Same-day by 17:00 IST | > 7 days | > 10 days | **"Data lag: 4 days baseline"** footnote on every VIX render (per JIP empty-tables memory) |
| USDINR spot | `de_global_price_daily` (USDINR=X) | Intraday (every 15 min) | > 1 hour | > 24 hours | **"Feed sparse · using RBI reference-rate fallback"** footnote; fallback = `de_rbi_fx_rate`. Only 3 rows in primary table per V11-5. |
| RBI FX reference | `de_rbi_fx_rate` | Daily EOD | > 2 days | > 5 days | Healthy (~1028 rows) |
| RBI policy rate | `de_rbi_policy_rate` | Event-driven (on RBI announcement) | > 1 calendar quarter | > 6 months | Expected gaps; show "as of last RBI policy date" always |
| 10Y G-Sec yield | `de_gsec_yield` | Same-day by 18:00 IST | > 1 trading day | > 3 trading days | **Table empty per V11-6 → route returns 503 → block renders ERROR state with "G-Sec feed unavailable" copy** |
| FII / DII flows | `de_fii_dii_flows_daily` | T+1 by 10:00 IST | > 2 trading days | > 5 trading days | — |
| F&O / PCR / OI | `de_fo_bhavcopy` | Same-day by 19:00 IST | > 1 trading day | > 3 trading days | **Table empty per V11-4 → derivatives routes return 503 → block renders ERROR state with "F&O feed offline" copy** |
| Adjustment factors | `de_adjustment_factors_daily` | Daily EOD | — | — | **Table empty permanently per V11-2.** Every corporate-action-sensitive chart (stock detail, RS calc) must display: `"Adjusted prices unavailable — raw prices shown. Corporate actions computed on-the-fly from de_corporate_actions."` |
| Corporate actions | `de_corporate_actions` | Event-driven | > 30 days since last | > 90 days | Healthy (~14,964 rows) |
| MF weighted technicals | `atlas_mf_weighted_technicals` | T+1 | > 2 calendar days | > 5 calendar days | — |
| Breadth counts | `atlas_breadth_daily` | Same-day by 18:00 IST | > 1 trading day | > 3 trading days | — |
| Benchmark TRI (Nifty 50 / 500) | `de_index_daily` | Same-day by 17:30 IST | > 1 trading day | > 3 trading days | — |
| Gold (LBMA / MCX) | `de_commodity_daily` | Same-day by 18:00 IST | > 1 trading day | > 3 trading days | Critical for §10 Gold RS amplifier — if red, disable Gold RS column and show `"Gold feed unavailable · RS amplifier suspended"` |

### Display format — the freshness pill

Every data-bound card header includes the pill at top-right:

| State | Pill colour | Example text |
|---|---|---|
| Fresh | Hidden | — (no pill when within expected window) |
| Amber | `--rag-amber-300` bg, `--rag-amber-900` text | `"as of 16-Apr · 2 sessions old"` |
| Red | `--rag-red-300` bg, `--rag-red-900` text | `"Feed delayed · 5 sessions"` |

Pill is always accompanied by the full source footer at the bottom of
the card, never rendered alone.

### Fallback sources (locked)

When a primary JIP table is empty/stale, the UI may fall back to a
named alternate source. The fallback must be **declared** in the
footer, never silent.

| Primary (stale/empty) | Fallback source | UI footer copy |
|---|---|---|
| `de_global_price_daily` (USDINR=X) | `de_rbi_fx_rate` (USD row) | `"Source: RBI reference rate · {date}"` |
| `de_adjustment_factors_daily` | Computed on-the-fly from `de_corporate_actions` | `"Adjustment factors computed from corporate-action ledger"` |
| `de_gsec_yield` (if populated later) | Show ERROR state (no fallback) | `"G-Sec yield feed unavailable — check back EOD"` |
| `de_fo_bhavcopy` | Show ERROR state (no fallback) | `"F&O feed offline — derivatives view unavailable"` |

Fallbacks never override — primary data, even if stale within amber
threshold, is preferred over fallback. Fallback only invoked when
primary is empty (0 rows for the requested window) OR past red
threshold.

---

## 1.9.3 Per-page empty / stale behaviour

Every block on every page that reads JIP or atlas_* tables. For each:
which state is realistic, and what the treatment is.

### 1. Today / Pulse

| Block | Binding | Realistic states | Treatment |
|---|---|---|---|
| Nifty 50 level + Δ (hero chip) | `de_index_daily` | Fresh (expected) · Amber (rare, >1 trading day old) | Amber: pill on chip + footer |
| USDINR (hero chip) | `de_global_price_daily` USDINR=X → fallback `de_rbi_fx_rate` | **Likely fallback (only 3 rows in primary per V11-5)** | Render from fallback; footer: `"Source: RBI reference rate · {date}"`. If fallback also >24h stale: skeleton chip with copy `"FX feed unavailable · check back 10:00 IST"` |
| 10Y G-Sec yield (hero chip) | `de_gsec_yield` | **Empty per V11-6 → ERROR state** | Render red chip: `"G-Sec feed unavailable"` + retry |
| India VIX (hero chip) | `de_volatility_index` | **Baseline 4-day lag** | Render number; pill: `"4-day lag"` (permanent). If >10 days: red `"VIX provider outage"` |
| Regime band (Expansion/Correction/Distress) | `atlas_breadth_daily` + regime classifier | Fresh · Amber (>1 trading day) · Empty (if atlas_breadth_daily empty) | Amber: pill on band. Empty: ERROR `"Regime classifier unavailable"` |
| Breadth mini (3 KPI cards) | `atlas_breadth_daily` | Fresh · Amber | Amber per-card pill |
| Sector board (11 tiles) | `atlas_sector_rrg_daily` | Fresh · Amber · Partial (some sectors missing) | Amber: pill per tile. Partial: missing sector rendered as EMPTY tile with `"RRG data missing · check JIP coverage"` |
| Movers (gainers / losers) | `de_stock_price_daily` | Fresh · Empty (pre-market window) | Pre-market empty: `"Movers unavailable before 09:15 IST"` |
| Fund mover strip | `de_mf_nav_daily` (sorted 1D) | Fresh · Amber (>2 days) · Empty (weekend) | Weekend empty: `"NAV static over the weekend — last update: Fri 12-Apr"` |

### 2. Explore · Global

| Block | Binding | Realistic states | Treatment |
|---|---|---|---|
| Regime (global) | Derived from MSCI World + DXY + VIX z-scores | Fresh · Partial (one input missing) | Partial: band renders with amber + footer `"Computed on {n} of {n_total} inputs · {missing list}"` |
| Macros (DXY, Copper/Gold ratio, etc.) | `de_global_price_daily` | Fresh · Amber · Empty per-ticker | Per-row pill; empty ticker rendered as grey cell with `"no data"` |
| Yields (UST 2Y/10Y) | `de_global_rates_daily` (if exists) or placeholder | **Likely empty in V1** → show "V1.1" grey state per §14 | `rec-slot` placeholder pattern applies |
| FX (G10 currencies) | `de_global_price_daily` | Fresh · Partial (USDINR sparse) | Per-row; USDINR row uses RBI fallback |
| Commodities (Gold, Brent) | `de_commodity_daily` | Fresh · Amber | Amber pill per tile |
| Credit (HY spreads) | External | **Likely empty in V1** | "V1.1" grey state |
| Risk (VIX, MOVE) | `de_volatility_index` + external MOVE | VIX: 4-day lag baseline; MOVE likely empty | VIX: `"4-day lag"` pill. MOVE: `"MOVE feed V1.1"` grey |
| RRG (global sectors) | External / derived | **Likely empty in V1** | "V1.1" grey tile with explainer |

### 3. Explore · Country (India)

| Block | Binding | Realistic states | Treatment |
|---|---|---|---|
| Regime (India) | `atlas_breadth_daily` | Fresh · Amber | Amber pill on band |
| Breadth panel (oscillator + 3 KPIs + zone history) | `atlas_breadth_daily` | Fresh · Amber · Partial (zone-events empty) | Zone-events partial: `"Zone history unavailable · run backfill"` |
| Derivatives (PCR, India VIX, max pain) | `de_fo_bhavcopy`, `de_volatility_index` | **F&O empty per V11-4 → ERROR for PCR/max pain**; VIX 4-day lag | PCR block: red ERROR `"F&O feed offline"`. VIX: `"4-day lag"` pill |
| Rates · G-Sec yield curve | `de_gsec_yield` | **Empty per V11-6 → ERROR** | Full block: `"G-Sec yield curve unavailable · feed offline"` + retry |
| INR chart (5Y) | `de_global_price_daily` USDINR=X → fallback `de_rbi_fx_rate` | **Primary sparse → use fallback for historical** | Chart renders from RBI fallback; footer: `"Historical INR from RBI reference rate · {first_date} to {last_date}"` |
| FII / DII flows | `de_fii_dii_flows_daily` | Fresh · Amber (>2 trading days) | Amber pill |
| Sectors RRG (12 tiles) | `atlas_sector_rrg_daily` | Fresh · Partial | Per-tile state |

### 4. Explore · Sector

| Block | Binding | Realistic states | Treatment |
|---|---|---|---|
| State card (4 chips) | `atlas_sector_rrg_daily` (filtered) | Fresh · Amber · Empty (if sector not tracked) | Empty: `"Sector not in coverage — request via ops ticket"` |
| Breadth panel (sector universe) | `atlas_breadth_daily` filtered | Fresh · Amber · Partial (sparse universe < 5 stocks) | Partial: show but with caveat `"Small universe: {n} stocks · breadth signal noisy"` |
| Member stocks table | `de_stock_price_daily` joined | Fresh · Stale-per-row | Per-row amber for any stock with stale price |
| Fundamentals (sector P/E, EPS growth) | `de_stock_fundamentals_quarterly` | Often stale (quarterly cadence) | Baseline footer: `"As of last reported quarter · {quarter}"` |
| Macro sensitivities | Derived from `de_stock_price_daily` + macros | Fresh · Partial (some macro inputs empty) | Partial: fewer rows with footer `"Shown: {n} of {n_expected} sensitivities"` |

### 5. Stock detail

| Block | Binding | Realistic states | Treatment |
|---|---|---|---|
| Hero (price + chips) | `de_stock_price_daily` | Fresh · Amber | Amber pill on hero |
| Chart (5Y candle) | `de_stock_price_daily` + `de_corporate_actions` | Fresh · Amber · **Adjustment factor note always present** | Footer: `"Adjusted prices computed from de_corporate_actions. de_adjustment_factors_daily empty — using on-the-fly computation."` |
| News | External / placeholder | Likely empty in V1 | `"News feed V1.1 · no items"` grey state |
| Risk snapshot (vol, DD, VaR) | Derived from prices | Fresh · Partial (if < 252 trading days of data) | Partial: `"Risk metrics computed on {n} sessions · minimum 252 required for 1Y"` |
| Technical snapshot (RSI, MACD, MAs) | Derived | Fresh · Partial | Partial: per-metric empty cell |
| Fundamental snapshot | `de_stock_fundamentals_quarterly` | Often stale | Quarter footer always present |
| RS panel (4 benchmarks) | Derived from `de_stock_price_daily` vs 4 benchmarks | Fresh · Partial (Gold stale → RS vs Gold suspended) | Gold row: `"RS vs Gold unavailable"` if Gold feed red |
| Corporate Actions | `de_corporate_actions` | Fresh · Empty (legit) | Empty: `"No corporate actions in last 5 years."` |
| Peer comparison | `de_stock_price_daily` + peer universe | Fresh · Partial | Partial: fewer peer rows |

### 6. MF detail

| Block | Binding | Realistic states | Treatment |
|---|---|---|---|
| Hero (fund + AUM + chips) | `de_mf_scheme_info`, `de_mf_nav_daily` | Fresh · Amber (>2 calendar days) | Amber pill |
| Returns table | `de_mf_nav_daily` | Fresh · Partial (fund age < 5Y → no 5Y row) | Partial: "–" in 5Y cell with tooltip `"Fund age < 5Y"` |
| Rolling returns chart | `de_mf_nav_daily` | Fresh · Partial | Partial: shorter chart with footer `"Fund inception: {date} · chart shows available window"` |
| Alpha quality (Jensen, Treynor, IR, capture) | Derived vs benchmark TRI | Fresh · Partial (missing benchmark days → NULL output) | Partial: per-metric "–" with tooltip |
| Risk (vol, DD, downside dev, VaR) | Derived | Fresh · Partial | Per-metric |
| Holdings (top 20) | `de_mf_portfolio_monthly` | Stale (monthly cadence) | Baseline footer: `"Holdings as of {month} · monthly disclosure"` |
| Sector allocation | `de_mf_portfolio_monthly` joined | Stale (monthly) | Same footer |
| Rolling alpha/beta | Derived | Fresh · Partial | Partial: shorter chart |
| Suitability (SIP outcomes, peers) | Derived | Fresh · Partial | Peer table partial: fewer rows |

### 7. MF rank

| Block | Binding | Realistic states | Treatment |
|---|---|---|---|
| Hero + universe size | `de_mf_scheme_info` | Fresh | — |
| Scoring panel (EXPLAIN) | Static | N/A | — |
| Rank table | `/api/v1/mf/rank` (new, fixture in V1) | V1: fixture OK. Stage 2: Partial (funds with < 1Y track: excluded) | Excluded count footer: `"{n} funds excluded · insufficient history"` |
| Per-row sparkline | `atlas_mf_rank_history` (new) | Partial (first 30 days post-launch will be sparse) | Sparkline renders with footer `"Rank history builds over {n} days"` |
| 4 RRG chips per row | `atlas_mf_weighted_technicals` | Fresh · Amber · Partial | Per-row; missing chip renders as `—` |

### 8. Breadth Terminal

| Block | Binding | Realistic states | Treatment |
|---|---|---|---|
| Hero (3 headline counts) | `atlas_breadth_daily` | Fresh · Amber · Empty (ERROR) | Amber pill on hero |
| Regime band | Derived | Fresh · Amber | Amber on band |
| 3 KPI cards | `atlas_breadth_daily` | Fresh · Amber | Per-card pill |
| Breadth oscillator chart (5Y) | `atlas_breadth_daily` | Fresh · Partial (first 60 days post-launch if new universe) | Partial: chart with footer `"Series starts {date} · {n} sessions"` |
| Zone reference panel | Derived | Fresh · Partial | — |
| DESCRIBE block | Derived | Fresh · Empty (if current value NULL) | Empty: block reads `"No current reading — data pending"` |
| Signal history table | `atlas_breadth_zone_events` (new) | Fresh · Partial | Partial: footer `"{n} events in window"` |
| EXPLAIN block | Static | N/A | — |
| Signal Playback embed | Mixed (breadth + NAV) | See §1.9.4 | See §1.9.4 |

### 9. Portfolios

| Block | Binding | Realistic states | Treatment |
|---|---|---|---|
| Hero (aggregate AUM, last reconciled) | `atlas_portfolio_*` | Fresh · Stale (if reconciliation lagging) | Stale: amber pill on "Last reconciled" chip |
| Book grid (4 books) | `atlas_portfolio_books` | Fresh | — |
| Per-book holdings table | `atlas_portfolio_holdings` joined `de_stock_price_daily` | Fresh · Per-row stale | Per-row amber for any holding with stale price |
| Per-book weight chart | Derived | Fresh | — |
| Per-book performance vs benchmark | Derived | Fresh · Partial (benchmark mismatch) | — |

### 10. Lab / Simulations

| Block | Binding | Realistic states | Treatment |
|---|---|---|---|
| Mode tabs | Static | N/A | — |
| Strategy config | User input | N/A | — |
| Results: equity curve + DD | `/api/v1/simulate/run` | Fresh · Empty (no trades) · Error (sim failed) | See §1.9.4 |
| Performance KPIs | Derived | Fresh · Partial | — |
| Trade log | Derived | Fresh · Empty (no trades) | Empty per §1.9.4 |
| Monte Carlo overlay | Derived | Fresh · Toggle off by default | — |

### Global search

| Result group | Realistic states | Treatment |
|---|---|---|
| All groups empty (query < 2 chars) | Expected | Empty block: `"Start typing to search stocks, funds, sectors, indices, currencies, macros"` |
| All groups empty (query ≥ 2 chars, no hits) | Expected | Empty block: `"No matches for '{query}' · try a symbol, AMC name, or sector"` |
| Partial results (some groups empty) | Expected | Per-group empty row: `"No {entity_type} match"` |
| Search index load failure | Error | Red block: `"Search index unavailable · retry"` |

---

## 1.9.4 Simulator empty states (§10.5)

The Signal Playback simulator has distinct non-happy states that the
regular card patterns don't cover. Spec'd explicitly.

### State: No data loaded yet (initial mount)

Simulator renders with:
- Equity curve chart skeleton (pulse animation)
- Run button visible but **disabled**, with tooltip `"Load a fixture
  or enter parameters to simulate"`
- Input panel filled with defaults
- KPI tile row shows `—` in every tile
- Tabs (Transaction Log, Cashflow, Tax Analysis) visible, contents
  replaced by a single-line prompt: `"Run a simulation to see
  results"`

Copy on the chart area:

```
Load fixture → Nifty 500 breadth  (5Y, 2021-04 → 2026-04)
or click Run Simulation with current parameters.
```

### State: Simulation completed with zero trades

All deposits happened, but no breadth zone was crossed in the window,
so no sells/redeploys fired. Equity curve = pure B&H = close to
benchmark.

Treatment:
- Equity curve renders normally (strategy line tracks benchmark)
- Banner above chart:

```
No signals fired on this window.
The strategy ran as buy-and-hold (initial + SIP + no triggers).
Widen the date range or loosen threshold parameters to see rule activity.
```

- Transaction Log tab: only shows initial + monthly SIPs (those are
  still "events", just not rule-triggered) — no `Sell@≥L_ob`,
  `Sell@<fLvl`, `Redeploy@...` rows
- Tax Analysis tab: EMPTY state (see next)
- KPIs populate normally

### State: Tax Analysis empty (no realised gains)

When no sells have fired, there are no realised STCG/LTCG — Tax
Analysis has nothing to table.

Treatment: replace FY table with:

```
No realised gains in this window.
Total invested: ₹{total_invested}.  Unrealised-if-sold-today: STCG
₹{stcg}, LTCG ₹{ltcg}, total tax ₹{total}.
```

"Unrealised-if-sold-today" summary card stays visible.

### State: Fixture load failure

Fixture JSON failed to fetch (404, network error, malformed).

Treatment: error card replaces chart:

```
[ALERT]  Fixture load failed
         breadth_daily_5y.json · 404 Not Found · 14:12 IST
         [Retry]   [Report issue]
```

Input panel remains editable (user can paste data, or choose another
fixture from dropdown).

### State: Simulation compute error (Stage 2)

Backend `/api/v1/simulate/breadth-strategy` returned 500 or timed out.

Treatment: error card replaces chart:

```
[ALERT]  Simulation failed
         Server error · request id {uuid} · 14:12 IST
         [Retry]   [Report issue with request id]
```

Input panel remains editable. Previous successful result (if any)
retained in a collapsed "Previous run" drawer for comparison.

### State: Benchmark overlay unavailable

Strategy equity curve computes fine, but Nifty 50 TRI or Nifty 500 TRI
series is stale/missing — the §10.5.4 mandatory overlay has to degrade
gracefully.

Treatment:
- Strategy line renders in full
- Benchmark lines render partially up to last-available date, then
  dashed light-grey projection labeled `"benchmark data unavailable
  from {date}"`
- Legend shows benchmark line with amber pill
- KPI "vs Nifty 50 B&H" shows `—` with tooltip explaining the gap
- Footer note: `"Benchmark series stale — strategy comparison shown
  only to {date}"`

---

## 1.9.5 Copy conventions

The exact words are part of the spec. Not "write something
appropriate."

### Six rules

1. **Declarative, never apologetic.** No "Oops", "Sorry", "Something
   went wrong", "Uh oh".
2. **What, when, action.** Every non-happy state answers three
   questions in order: what is the state (feed stale, no data, error),
   when was it last OK, what can the user do now.
3. **Name the source.** If the data comes from `de_global_price_daily`,
   that's what the footer says. Acronyms are fine, they're the FM's
   vocabulary.
4. **No exclamation marks.** Ever. This is a wealth-management tool.
5. **Sentence case, not Title Case.** "Data feed unavailable" not
   "Data Feed Unavailable".
6. **Numbers preserved.** Copy includes actual numbers wherever
   possible — "4 sessions old" not "a few days old".

### Canonical phrases (bad vs good)

| Situation | BAD copy (banned) | GOOD copy |
|---|---|---|
| Loading (skeleton, silent) | "Loading…" spinner | (no copy, skeleton) |
| Empty (no rows) | "Oops, nothing here!" | "No corporate actions in the selected window." |
| Empty (filter returns 0) | "No results :(" | "No funds match your filter. Try widening AUM band or category." |
| Stale (amber) | "Data might be a bit old" | "Data lag: 2 sessions · as of 16-Apr-2026" |
| Stale (red) | "Uh oh, data is old!" | "Feed delayed: last update 5 sessions ago. Check JIP ingest." |
| Error (5xx) | "Sorry, something went wrong!" | "Data feed unavailable · last seen 14:00 IST · retry" |
| Error (network) | "Network error" | "Could not reach server · check connection · retry" |
| Error (503 from DB health gate) | "Server error" | "F&O feed offline · derivatives view unavailable · retry" |
| Simulator no trades | "No trades!" | "No signals fired on this window · widen thresholds or pick a longer range" |
| Simulator no tax | "Nothing to see here" | "No realised gains in this window" |
| Simulator fixture fail | "File not found" | "Fixture load failed · {filename} · 404 · retry" |
| VIX permanent lag | (no note) | "Data lag: 4 days" (always present under VIX render) |
| USDINR fallback | (no note) | "Source: RBI reference rate · 17-Apr-2026" |
| Adjustment factors note | (silent / broken chart) | "Adjusted prices computed from corporate-action ledger (de_adjustment_factors_daily empty)" |
| Gold RS suspended | "N/A" | "RS vs Gold unavailable · feed delayed" |
| Fund < 5Y on 5Y return | "N/A" | "–" in cell, tooltip: "Fund age < 5Y · inception {date}" |
| Pre-market empty movers | "No data" | "Movers unavailable before 09:15 IST" |
| Weekend NAV static | "Fund closed" | "NAV static over weekend · last update Fri 12-Apr" |
| Search no match | "No results" | "No matches for '{query}' · try a symbol, AMC name, or sector" |
| Search too short | "Keep typing" | "Start typing to search stocks, funds, sectors, indices, currencies, macros" |
| Sim compute error | "Error!" | "Simulation failed · server error · request id {uuid} · retry" |
| Benchmark stale in sim | "Benchmark missing" | "Benchmark series stale · strategy comparison shown only to {date}" |
| Chart empty (new universe) | "Chart has no data" | "Series starts {date} · {n} sessions available" |
| Regime classifier down | "?" | "Regime classifier unavailable · check breadth feed" |

### Timestamp formatting in copy

- Absolute: `"14-Apr-2026 16:05 IST"` — dash-separated DD-MMM-YYYY per
  §1.6 of main spec
- Relative: `"4 sessions old"`, `"2 calendar days old"`, `"14 minutes
  ago"` — explicit unit
- NEVER "recently", "a while ago", "soon", "shortly"

### Action copy on retry buttons

- Primary action: `"Retry"` (not "Try again", not "Reload")
- Secondary: `"Report"` (not "Report bug", not "Tell us")
- Destructive: `"Discard"` (not "Cancel", not "Nevermind")

---

## 1.9.6 Accessibility

Every non-happy state must be perceivable by screen readers and
keyboard users.

### ARIA live regions

- **Loading**: container has `aria-busy="true"`. No live announcement
  (skeleton is silent).
- **Empty**: container has `role="status"` and `aria-live="polite"`.
  Announcement happens once on mount.
- **Stale**: freshness pill has `role="status"` with full
  `aria-label="Data lag: 2 sessions, as of 16-Apr-2026"`.
- **Error**: container has `role="alert"`. Announcement is immediate
  and interrupts. Error copy is the first thing announced.

```html
<!-- Loading skeleton -->
<div class="card card--md" aria-busy="true" aria-label="Loading breadth data">
  <div class="skeleton skeleton--chart"></div>
</div>

<!-- Empty state -->
<div class="card card--md" role="status" aria-live="polite">
  <p class="empty-msg">No corporate actions in the selected window.</p>
</div>

<!-- Stale state -->
<div class="card card--md">
  <header>
    <h3>USDINR</h3>
    <span class="freshness-pill freshness-pill--amber"
          role="status"
          aria-label="Data lag: 2 sessions, as of 16-Apr-2026">
      as of 16-Apr · 2 sessions old
    </span>
  </header>
  ...
</div>

<!-- Error state -->
<div class="card card--md error-card" role="alert">
  <p class="error-summary">Data feed unavailable · last seen 14:00 IST</p>
  <button class="btn btn--primary">Retry</button>
</div>
```

### Keyboard interaction

- "Retry" button is autofocused when error state mounts and there's no
  other primary action
- "Report" link is always focusable, opens in new tab with
  `rel="noopener"`
- Skeleton screens do not trap focus; the user can Tab past them

### Colour and contrast

- Amber pill text: `--rag-amber-900` on `--rag-amber-300` — verified
  ≥ 4.5:1
- Red error text: `--rag-red-900` on `--bg-surface` — verified ≥ 4.5:1
- Empty-state grey text: `--text-secondary` on `--bg-surface` —
  verified ≥ 4.5:1
- Never convey state by colour alone — always accompany with icon +
  text (RAG rule §2 of design-principles.md)

### Reduced motion

- Skeleton pulse animation: disabled if `prefers-reduced-motion:
  reduce` — skeleton renders as flat `--bg-inset` fill
- Error card: no shake-on-mount animation (even if motion OK)
- Freshness pill: no pulse

---

## 1.9.7 Telemetry

Every non-happy state emits a structured event so we can measure real
data-quality impact and the dashboard `/forge` route can harvest.

### Event schema

```typescript
interface StateEvent {
  ts: string;               // ISO8601 IST
  page: string;             // "today" | "stock-detail" | "breadth" | ...
  block: string;            // "hero-usdinr" | "sector-board" | "breadth-oscillator" | ...
  state: "loading" | "empty" | "stale" | "error";
  data_as_of: string | null; // ISO8601 of the underlying data's timestamp (null on error)
  freshness_seconds: number | null;  // age of data in seconds (null for empty/error)
  source_table: string | null;       // "de_global_price_daily" | "atlas_breadth_daily" | ...
  fallback_used: string | null;      // "de_rbi_fx_rate" if fallback, else null
  error_code: string | null;         // "503" | "network_timeout" | "fixture_404" | ...
  threshold_level: "fresh" | "amber" | "red" | null;  // for stale states
}
```

### Emission rules

- **V1 Stage 1 (mockup):** emit to `console.debug` with a structured
  JSON payload. Prefix: `"[atlas-state]"` for easy grep.
- **V1 Stage 2:** wire to a real sink — POST to
  `/api/v1/telemetry/state-events` (new backlog route). Sink
  deduplicates by (page, block, state, minute-bucket) to prevent
  volume blow-up.
- Every state entry emits once per state transition (not per render).
  Debounced at 500ms.
- Fresh → stale transition: emit `stale`
- Stale (amber) → stale (red): emit `stale` with new `threshold_level`
- Any → error: emit `error`
- Any → fresh: emit nothing (no "back to normal" event)

### Example emissions

```js
// On Today page, USDINR chip loads via fallback
console.debug("[atlas-state]", {
  ts: "2026-04-18T09:12:04+05:30",
  page: "today",
  block: "hero-usdinr",
  state: "stale",
  data_as_of: "2026-04-17T18:00:00+05:30",
  freshness_seconds: 54244,
  source_table: "de_rbi_fx_rate",
  fallback_used: "de_rbi_fx_rate",
  error_code: null,
  threshold_level: "amber",
});

// Breadth Terminal oscillator errors out
console.debug("[atlas-state]", {
  ts: "2026-04-18T09:15:11+05:30",
  page: "breadth",
  block: "breadth-oscillator",
  state: "error",
  data_as_of: null,
  freshness_seconds: null,
  source_table: "atlas_breadth_daily",
  fallback_used: null,
  error_code: "503",
  threshold_level: null,
});
```

### Dashboard harvesting (/forge)

`/forge` reads the telemetry stream in Stage 2 and renders:
- Top 10 blocks by error count (last 24h)
- Top 10 blocks by stale-red incidence
- Fallback-usage heatmap (which blocks are riding fallbacks, and how
  often)
- Data-quality SLA board (% time each JIP table was within amber
  threshold)

This closes the loop: the product complains about itself, and the
dashboard publishes the complaints.

---

## 1.9.8 Acceptance criteria (add to main spec §18)

- [ ] Every data-bound block on every page has an explicit state
      treatment per §1.9.3
- [ ] Skeleton screens render instead of spinners on every loading state
- [ ] Freshness pill appears on every stale state with exact copy per
      §1.9.5
- [ ] Fallback sources (RBI FX, corporate-actions-on-the-fly)
      declared in footer copy whenever used
- [ ] Every error state has Retry + Report + error code visible
- [ ] Signal Playback simulator handles all five sub-states per §1.9.4
- [ ] Every non-happy state announces via correct ARIA role
      (`status` / `alert` / `aria-busy`)
- [ ] Telemetry events log to console in Stage 1 per §1.9.7 schema
- [ ] Permanent notes (VIX 4-day lag, adjustment-factors computed)
      render on every applicable page
- [ ] No use of "Oops", "Sorry", exclamation marks, or relative
      timestamps like "recently"

---

**End of §1.9.** Empty / stale / error are first-class UI states, not
afterthoughts. A block that does not handle all four does not ship.
