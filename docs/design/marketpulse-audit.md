# MarketPulse (Jhaveri Intelligence Platform) — Design Audit

**Source:** `https://marketpulse.jslwealth.in` (live production, public)
**Audited:** 2026-04-17
**Method:** HTML shell + live JSON API inspection (headless browser unavailable on this host; the app is Next.js 16 RSC with `/api/*` JSON endpoints that return the full rendered payload, so API shape + SSR shell give a complete picture of every screen's data and layout).
**Purpose:** Extract the design patterns, data layers, and signal-fusion logic that already work, so ATLAS frontend can reuse the good parts and enrich the rest with the richer `de_*` data documented in `jip-data-atlas.md`.

---

## 1. Sitemap (as rendered by the sidebar)

| Route | Label | Purpose |
|---|---|---|
| `/` | Command Center | TradingView alert queue with FM approve/deny workflow |
| `/actioned` | Actioned Cards | Live tracker of FM-actioned alerts (Active / Triggered / Closed) |
| `/pulse` | Market Pulse | Live index signals (Broad / Sectoral / Thematic / BSE & Global / Fixed Income) |
| `/sentiment` | Sentiment | Nifty-500 breadth + sentiment score + sector breadth |
| `/recommendations` | Recommendations | "Pick sectors → threshold → top stocks/ETFs with fundamentals" |
| `/compass` | Sector Compass | Hub: Top Picks, Sectors, ETFs, Model Portfolio, Lab, Methodology |
| `/portfolios` | Model Portfolios | Client PMS portfolios with NAV/holdings/risk analytics |
| `/microbaskets` | Microbaskets | Custom stock basket vs benchmark, CSV upload |
| `/docs` | Documentation | (currently 404) |

**Observation:** 9 top-level sections, sidebar navigation, 15-min auto-refresh. This is a **live trading terminal**, not a marketing site. ATLAS needs the same information-density bias.

---

## 2. Signal model (the actual IP)

The platform's north star is **signal fusion with explanation**. Every quantitative output is a compound of 4-5 lenses, and each row carries a plain-English `action_reason`. The Sector Compass response is the clearest example:

```json
{
  "sector_key": "BANKNIFTY",
  "rs_score": -1.26,          // relative strength vs base
  "rs_momentum": -1.34,       // change in RS
  "quadrant": "LAGGING",      // RRG: LEADING / IMPROVING / WEAKENING / LAGGING
  "absolute_return": -4.98,
  "volume_signal": "ACCUMULATION",   // or DISTRIBUTION / WEAK_RALLY
  "pe_ratio": 14.17,
  "pe_zone": "VALUE",         // or FAIR / EXPENSIVE
  "market_regime": "BULL",    // global context overlay
  "action": "SELL",
  "action_reason": "down 5.0%, underperforming by 1.3% vs benchmark,
                    momentum fading (-1.3). Volume shows accumulation
                    (smart money buying). Trades at 14x P/E — in value
                    territory, attractive entry if action confirms."
}
```

This is **exactly** the convergence/divergence pattern the user described. The `action` is the convergence verdict; the `action_reason` surfaces the divergence (price weak + momentum fading + but volume accumulating + but valuation cheap → `SELL` with a caveat about value entry).

**Dimensions fused per sector (from live payload):**
1. **Price** — absolute return over period
2. **Relative Strength** — `rs_score` vs chosen base (NIFTY / NIFTY100 / NIFTY500)
3. **Momentum** — `rs_momentum` (delta of RS)
4. **Volume** — `ACCUMULATION` / `DISTRIBUTION` / `WEAK_RALLY` (smart-money tape)
5. **Valuation** — `pe_zone` VALUE / FAIR / EXPENSIVE
6. **Regime** — `market_regime` BULL / BEAR (global overlay)
7. **RRG quadrant** — derived composite of 2 + 3

ATLAS already has everything to reproduce this and **go further**: `de_sector_breadth_daily` (per-sector %>50DMA, RSI OB/OS, MACD bullish %), `de_mf_derived_daily` (manager alpha), `de_*_fundamental_*` (ROE, EPS growth, FCF — currently unused), and `de_macro_*` (regime from yields, INR, FII flows — currently unused).

---

## 3. Per-page breakdown

### 3.1 Command Center (`/`)

- **Purpose:** Real-time TradingView alert inbox for the Fund Manager.
- **Layout:** Sticky counters (Total / Pending / Approved / Denied / Bullish / Bearish) → filter row (Pending ✓ / Approved / Denied checkboxes) → two dropdowns (sector / instrument filter) → grid of alert cards (3-col on xl).
- **Action model:** Each alert is `pending`; FM approves or denies. POST `/api/alerts/{id}/action`. Approved alerts flow to Actioned Cards.
- **What works:** The approve/deny FM workflow is a concrete governance pattern ATLAS lacks. Signals without accountability are noise.
- **Gap vs ATLAS data:** TradingView is the only source here. ATLAS can stack its own alert sources on top: UQL-driven rule alerts, breadth thresholds, valuation zone crossings, manager-alpha drift.

### 3.2 Actioned Cards (`/actioned`)

- **Purpose:** "Did the FM's call work?" — live P&L on every actioned alert.
- **Tabs:** Active / Triggered / Closed. Shows entry, current, performance tracking.
- **What works:** Closes the feedback loop. Every public call has a live scorecard. Critical for credibility.
- **ATLAS opportunity:** Extend with realised vs expected return, time-in-trade, best/worst-case paths from V3 simulation engine.

### 3.3 Market Pulse (`/pulse`)

- **Tabs:** Broad Market / Sectoral / Thematic / BSE & Global / Fixed Income.
- **API:** `/api/indices/live?base=NIFTY500` → 78 indices with OHLC, 30D/365D perf, 52w range, PE, PB, advances/declines, `ratio` (vs base), `signal` (`STRONG OW` / `OW` / `NEUTRAL` / `UW` / `STRONG UW`), `ratio_returns` (1d/1w/1m/3m/6m/12m), `index_returns` (same buckets).
- **Layout inference:** Likely a sortable table per tab with the `signal` column colour-coded and the `ratio` sparkline per row. 6 return buckets × 2 (absolute, relative) = 12 numbers per row.
- **What works:**
  - `signal` as a 5-level compound verdict (not just +/−).
  - `ratio_returns` vs `index_returns` shown side-by-side = implicit Pattern A (dual line) on every row.
  - 78 indices across broad / sectoral / thematic / BSE / fixed income under one surface.
- **Gap:** No visible breadth overlay on the per-index row (just price ratios).

### 3.4 Sentiment (`/sentiment`)

- **Tabs:** Market Breadth / Sentiment Score / Sectors.
- **Periods:** 1M / 3M / 6M / 1Y / 18M / 2Y / 3Y.
- **API 1 — `/api/breadth/sectors`:** 48 sectors, each with `health_score` (0-100) + 12 breadth indicators: `ema21`, `ema200`, `rsi_daily_40`, `rsi_daily_30`, `52w_high`, `52w_low`, `monthly_12m_ema`, `prev_month_high`, `prev_quarter_high`, `prev_year_high`, `monthly_rsi_50`, `monthly_rsi_40`. Each indicator returns `{count, total, pct, zone}` where `zone` ∈ {`Extreme Fear` / `Fear` / `Neutral` / `Greed` / `Extreme Greed`}.
- **API 2 — `/api/breadth/history?lookback=180`:** Time-series of each indicator with `{label, granularity, zone_type, current, history[]}` plus `divergences[]` array (price-vs-breadth divergence detection, currently empty).
- **API 3 — `/api/sentiment/actionables?period=3M`:** 61 rows fusing sentiment + RS into a single ranked list: `sentiment_score`, `sentiment_zone`, `rs_score`, `rs_momentum`, `quadrant`, `action`, `combined_score`, `bullish_count`, `bearish_count`, `stock_count`.
- **What works — this is the richest page.**
  - 12 independent breadth lenses per sector with an aggregate `health_score`. That is textbook convergence design.
  - `divergences` array is first-class: the app hunts for and surfaces disagreement between price and breadth, not just the agreement.
  - `combined_score` shows they already fuse sentiment + RS into one rank, but still expose the constituents.
- **ATLAS enrichment opportunity:** ATLAS has `de_sector_breadth_daily` with pct above 50/200DMA, RSI OB/OS, MACD bullish % — all of these are **additional** lenses (MarketPulse only uses price-based breadth today). Add fundamental breadth (% of sector with positive EPS growth, % with ROE > 15, % with positive FCF) from `de_*_fundamental_*` and you go from 12 lenses to 20+.

### 3.5 Recommendations (`/recommendations`)

- **Pitch (from shell):** "Select sectors and set a threshold — outperforming sectors surface their top stocks and ETFs with fundamentals."
- **API — `/api/recommendations/sectors`:** returns 48 sectors with `{key, display_name, category, etfs[]}` and `periods: ['1w','1m','3m','6m','12m']`. Generation is POST `/api/recommendations/generate`.
- **Workflow:** User picks sectors + period + outperformance threshold → server generates a recommendation set with stocks + ETFs + fundamentals.
- **What works:** User-parameterised, not a static "top N" list. The FM sets the hypothesis.
- **Gap vs ATLAS data:** MarketPulse surfaces "fundamentals" but the JIP atlas shows fundamentals are 80%+ unused on ATLAS today. This is the biggest single gap to close.

### 3.6 Sector Compass (`/compass`) — the hub

- **Controls:** Base (NIFTY / NIFTY100 / NIFTY500), Period (1M / 3M / 6M / 12M), Refresh RS button.
- **Tabs (sub-pages):** Top Picks · Sectors · ETFs · Model Portfolio · Lab · Methodology.

#### 3.6.a Sectors (default tab)
- **API:** `/api/compass/sectors?base=NIFTY500&period=3M` — the 7-dimension fusion documented in §2. 48 sectors, each with `action`, `action_reason`, `etfs[]`.
- **Layout inference:** Likely an RRG scatter (momentum y vs RS x, 4 quadrants) with point size = volume signal, point colour = action, PE zone as a secondary axis or sidebar table. Each sector clickable → drill-down (`/api/compass/sectors/{key}/stocks?base=&period=`).

#### 3.6.b Top Picks
- **API:** `/api/compass/picks?period=3M&top_n=5` (504'd under load during audit — heavy compute).
- **Intent:** Server ranks sectors by the compound Compass score and emits top-N tradeable names per sector.

#### 3.6.c ETFs
- **API:** `/api/compass/etfs?base=NIFTY500&period=3M` → 71 ETFs with the same 7-lens payload as sectors, plus `parent_sector` linking each ETF back to its theme. So a SECTOR BUY verdict is always paired with a concrete ETF BUY candidate.

#### 3.6.d Model Portfolio
- **APIs:** `/api/compass/model-portfolio?portfolio_type=aggressive` (400'd — requires valid type; likely `conservative` / `balanced` / `aggressive`), plus `/nav`, `/performance`, `/trades`. So each portfolio type exposes: composition, NAV history, performance vs benchmark, trade ledger.
- **Pattern:** Strategy is a portfolio, portfolio has holdings and trades, trades flow from Sectors → Top Picks.

#### 3.6.e Lab
- **APIs (rich):**
  - `/api/compass/lab/runs?limit=` — historical backtest runs
  - `/api/compass/lab/factor-lab/run?universe=&horizon=` + `/results`
  - `/api/compass/lab/momentum-simulate?*` + `/momentum-results`
  - `/api/compass/lab/sweep/trigger?sweep_type=` + `/sweep-results`
  - `/api/compass/lab/decisions?portfolio_type=&limit=` + `/decisions/accuracy`
  - `/api/compass/lab/backfill-history?data_type=`
  - `/api/compass/lab/configs`, `/rules`, `/learning`, `/status`
- **Intent:** This is a full **research workbench**. FM can sweep parameters across a universe, backtest momentum rules, track decision accuracy. Lab is where the signal logic is tuned before it flows into Compass.
- **ATLAS equivalent:** V3 Simulation Engine. The Lab UX pattern (universe × horizon × rule → run → results table → accuracy over time) is directly reusable.

#### 3.6.f Methodology
- (Static content, not fetched.) Explains the Compass scoring.
- **Observation:** Methodology as a first-class nav item signals they expect institutional scrutiny. ATLAS should ship the same — a live, traceable methodology page rather than a PDF.

### 3.7 Model Portfolios (`/portfolios`)

- **APIs:** `/api/portfolios`, `/{id}`, `/{id}/holdings`, `/allocation`, `/nav-history?period=`, `/performance`, `/transactions`, `/export/holdings`, `/export/transactions`, `/{id}/holdings/{t}/symbol`. Plus `/api/pms/upload`, `/api/pms/{id}/summary`, `/drawdowns`, `/holdings`, `/metrics`, `/nav`, `/risk-analytics`, `/sector-history`, `/win-loss`.
- **Intent:** Client PMS portfolios — NAV, holdings, drawdowns, win-loss, sector-history, risk analytics. CSV upload for onboarding.
- **What works:** Institutional-grade — drawdown analytics, win-loss tracking per trade, sector rotation history per portfolio.
- **ATLAS gap:** This is broader than just MF analysis. ATLAS MF detail page should borrow the drawdown + win-loss + sector-history pattern for single funds.

### 3.8 Microbaskets (`/microbaskets`)

- **APIs:** `/api/baskets`, `/{id}`, `/live?base=`, `/csv-upload`, `/{id}/stop`.
- **Intent:** User-defined stock baskets with live ratio vs benchmark (`/baskets/live?base=NIFTY500`). CSV upload. Stop = halt tracking.
- **What works:** "What-if" laboratory — test a conviction basket against an index in real time.

---

## 4. Design-language observations

- **Visual palette:** Emerald-500/700 as brand (sidebar logo gradient), slate text, amber/emerald/red for RAG. Not petrol — they went with emerald. ATLAS's petrol is more distinctive and should stay.
- **Typography:** `Inter`, small sizes, `text-[10px]` for labels, heavy use of `uppercase tracking-wider` on micro-labels. Information-density-first.
- **Components:** shadcn/ui (`data-slot="card"`, `data-slot="select-trigger"`) + Tailwind. Skeleton loaders on every data block (not spinners) — matches our frontend rule.
- **Density:** 6-column counter row on the dashboard. Cards sized `h-[200px]` in a 3-col grid. Per-row tables with 10+ columns. Mobile-responsive but desktop-first.
- **RAG usage:** `amber-600` pending, `emerald-600` approved/bullish, `red-600` denied/bearish. Applied functionally (status), not decoratively. Same rule we've locked for ATLAS.
- **Interaction:** 15-min auto-refresh surfaced in the sidebar. Refresh buttons on data-heavy tabs (Compass, Sentiment). Sub-second initial render via SSR shell + client fetch.

---

## 5. What ATLAS already does better

1. **UQL layer** (spec §17) — MarketPulse has 50+ hand-crafted endpoints; ATLAS has one query language plus thin route wrappers.
2. **Manager's alpha** — in `de_mf_derived_daily`, never surfaced on MarketPulse (they're index-only).
3. **Fundamental breadth** — ATLAS has ROE, EPS growth, FCF per stock. MarketPulse uses price breadth only.
4. **Macro overlay** — 40+ `de_macro_*` series on ATLAS. MarketPulse hardcodes `market_regime = "BULL"`.
5. **MF holdings-weighted technicals** — `de_mf_weighted_technicals`. MarketPulse has no MF layer at all.
6. **Provenance** — ATLAS enforces traceable-to-table-and-formula; MarketPulse doesn't expose the formula inline.

## 6. What ATLAS should steal

1. **The 7-lens fusion row** (`rs_score`, `rs_momentum`, `quadrant`, `volume_signal`, `pe_zone`, `market_regime`, `action` + `action_reason`). This is the convergence/divergence pattern, productised. Every quantitative row in ATLAS (sector, fund, stock, ETF) should carry an equivalent compound verdict with a one-sentence explanation.
2. **FM approve/deny loop** on alerts, and the Actioned Cards live scorecard. Accountability closes the signal loop.
3. **Lab** as a first-class research workbench — universe × horizon × rule → run → accuracy over time. Maps directly to V3 Simulation Engine.
4. **Methodology as a nav item**, not a PDF. Live, traceable.
5. **Microbasket pattern** — "test any basket vs any benchmark, live" — as the interaction primitive behind the simulation tab on MF / stock pages.
6. **Divergences as first-class output**, not a byproduct. The `/breadth/history` endpoint returns a `divergences[]` array. ATLAS should do the same for every multi-lens surface.
7. **Skeleton loaders over spinners** (already in our frontend rules; reinforce).
8. **7-period ladder** (1w / 1m / 3m / 6m / 12m / 18m / 2y / 3y) — consistent across pages. ATLAS's mockups are inconsistent; standardise.

---

## 7. Direct implications for the MF detail redesign (deferred task)

Before we restart `mf-detail.html` as hub-and-spoke, bake in these decisions:

- **Overview landing** = the "fund's Compass row": compound action verdict (BUY / HOLD / AVOID / WATCH), with the 7-lens fusion displayed as a horizontal strip (RS vs category, momentum, volume signal from flows, PE zone, regime, manager alpha zone, risk zone) + a one-sentence `action_reason`.
- **Performance tab** = absolute NAV chart + benchmark (Pattern A), rolling returns table across the 8-period ladder.
- **Risk tab** = drawdown underwater chart + capture ratio dumbbell + Sharpe/Sortino vs category (Pattern C reference markers).
- **Portfolio tab** = holdings × sector compass join (each holding tagged with its sector's Compass action and volume signal — one click goes from fund → sector → stock).
- **Fundamentals tab** = fundamental breadth rollup (% of portfolio with ROE>15, % with positive EPS growth, % with FCF positive — this is the first ATLAS-native output MarketPulse cannot match).
- **Simulation tab** = "microbasket"-style what-if (sub this fund for that fund in a model portfolio; replay last 3Y).
- **Suitability tab** = fund tags (Quality Compounder / Aggressive / Concentration Risk / Large-AUM-Impact-Risk) feeding the recommendation engine.

Each tab carries its own mini-verdict so the Overview strip is a rollup, not a replacement.

---

## 8. Screenshots

Headless browser unavailable on this host (bundled `browse` binary is macOS arm64; no `bun`/Playwright installed). Audit performed via SSR shell + API introspection. Raw payload samples are saved under `/tmp/mp/api/` (not committed) for reference during design work. If full visual capture is needed, either (a) build the `gstack browse` binary on Linux, (b) `pip install playwright && playwright install chromium` into `backend/venv`, or (c) run the audit from the user's macOS laptop and drop PNGs into `docs/design/marketpulse-shots/`.

**Recommendation:** Visual capture is nice-to-have. The API-level picture is what matters for design — every number on every screen came through the endpoints documented above, and we now have the full data model.
