# ATLAS Frontend V1 — Specification

**Target:** Stage 1 (mockup sweep, all pages) landed by EOD Mon 20 Apr 2026.
**Stage 2** (wire to live APIs + Next.js mount) follows post-Monday.
**Scope:** pure mockup layer, zero API wiring in this stage. HTML only,
served via existing `/mockups/*` symlink. Uses the locked light design
system (`docs/design/design-principles.md`).

---

## §0 · Context + non-goals

### What V1 is
- Data-representation layer. Factors, chips, charts, tables, KPIs.
- Deterministic readouts ("at 178, below midline of 250") are OK.
- Pedagogical commentary everywhere — formulas shown, tooltips on every
  column, short explainers below every chart.
- Staged. V1 ships the canonical skeleton. V1.1+ enriches.

### What V1 is NOT
- NO LLM commentary. NO AI-driven narrative. NO GPT verdicts.
- NO actionable recommendations ("BUY", "HOLD / ADD ON DIPS", "reduce
  sizing", "trim FMCG"). Those are gated to V1.1 rule engine.
- NO portfolio accountability banner, shadow-NAV delta, rec ledger.
- NO dark mode. Locked light design language stays.

### Non-goals for Stage 1
- API wiring. Everything is static HTML.
- Reports (out of scope entirely for Monday).
- Watchlist (out of scope entirely for Monday).
- V1.1 rule engine (memory file:
  `~/.claude/projects/-home-ubuntu-atlas/memory/project_rule_engine_v1_1.md`).

---

## §1 · Global vocabulary

### 1.1 Commentary framework — three tiers

Every piece of prose on every page falls into exactly one tier.

| Tier | Purpose | Status | Example |
|---|---|---|---|
| **EXPLAIN** | Static pedagogical. What is this metric? What is the formula? | Always on, V1 | "Sharpe = (R − Rf) / σ. Higher = better risk-adjusted return." |
| **DESCRIBE** | Deterministic rule-free readout of the current data point. | Always on, V1 | "At 178, breadth is below the 250 midline. 5-day Δ −31." |
| **RECOMMEND** | Actionable call requiring judgment. | **Gated V1.1**, placeholder slot in V1 | "Reduce position sizing. Wait for recovery above 250." |

**EXPLAIN** is how the FM onboards a new analyst. Every chart gets a
2–3 sentence explainer printed BELOW the title, formula first, then
interpretation guidance. No jargon without a tooltip.

**DESCRIBE** is pure data paraphrase. If a human can read the chart
and say the same sentence, it's DESCRIBE. Numbers only.

**RECOMMEND** is what the rule engine will emit in V1.1. In V1, every
page reserves placeholder slots where RECOMMEND blocks will bind, but
the slot renders as empty / "V1.1 · coming".

### 1.2 Chip vocabulary (RRG · locked)

Four chip families. Rendered as pill badges. Colors from the RAG system.

- **RS** — LEADING (green) · IMPROVING (teal) · WEAKENING (amber) · LAGGING (red)
- **Momentum** — ACCEL (green) · STALL (amber) · DECEL (red)
- **Volume** — ACCUM (green) · NEUT (grey) · DISTRIB (red)
- **Breadth** — EXPANDING (green) · NARROW (amber) · THIN (red)

Every instrument panel (stock, MF, sector, index) displays all four.
Fund managers read the quartet at a glance. V1.1 rules bind on top
of these same chips.

### 1.3 Info-tooltip standard (`ⓘ`)

Every table column header MUST have an `ⓘ` tooltip defining the metric
and (where applicable) the formula. Every KPI card MUST have one. Every
chart axis label MUST have one.

Hover style: small `ⓘ` icon in `var(--text-tertiary)` to the right of
the label. On hover, tooltip card with:
- **Name** (bold, one line)
- **Formula** (mono font, one line)
- **Reading** (one sentence, plain English)

Example for Sharpe:

```
Sharpe ratio
(Return − Risk-free) / Std.deviation
Higher = more return per unit of risk. Above 1 is good, above 2 is excellent.
```

### 1.4 Formula disclosure

Formulas are first-class, not hidden in a glossary. Anywhere a
computed number is displayed:
- Short formula inline (below the chart title, in EXPLAIN block)
- Full formula + methodology in the `ⓘ` tooltip
- Source attribution at the bottom of every chart ("Source: JIP / ATLAS compute · data as of 18-Apr-2026 09:12 IST")

### 1.5 Shared components (defined once, reused)

| Component | Purpose | Used on |
|---|---|---|
| `kpi-strip` | Horizontal row of 4–8 big numbers with labels + deltas | Every page hero |
| `data-table` | Sortable, filterable, CSV-exportable tabular data | MF rank, Stock detail peers, Lab outputs, Portfolios |
| `sparkline` | Tiny inline trend, 60 × 20 px | Inside table rows, inside chip cards |
| `rs-mini` | 80 × 40 px RS line vs benchmark | Instrument cards, table cells |
| `sector-tile` | Large tile with sector name + 4 RRG chips + RS sparkline | Explore · Country, Pulse |
| `chart-with-events` | Line chart + vertical rules for key events (election, rate cut, COVID) | Breadth terminal, Stock detail, MF detail |
| `search-box` | Top-nav fuzzy search, typo-tolerant | Every page |
| `explain-block` | Title + formula + reading (tier 1 commentary) | Below every chart |
| `describe-block` | Deterministic readout of current values (tier 2) | Next to every chart |
| `rec-slot` | V1.1 placeholder; renders empty in V1 | Every page footer |

### 1.6 Number format (from global rules)

- `₹1,23,45,678` — Indian comma grouping, never Western million/billion
- Crore / lakh suffix for AUM: `₹847.2 cr`, not `₹8.47 bn`
- Percentages always signed: `+4.1%`, `−2.3%`
- Green for positive, red for negative, amber for watch/mid-band
- Numbers right-aligned, tabular-nums, mono font in tables
- Dates: `DD-MMM-YYYY` (`18-Apr-2026`), IST timezone always

### 1.7 Key-event markers (for 5Y charts)

Every 5Y historical chart includes vertical event rules with hover labels:
- Election result dates (General, key state)
- Budget announcement days
- RBI policy rate changes (cuts/hikes marked in different colors)
- Major macro events (COVID lockdown Mar 2020, demonetisation Nov 2016, Russia-Ukraine Feb 2022)
- Earnings season boundaries (each quarter's first and last result-day)
- Sector-specific shocks (IT: Trump export-ban headlines; Banks: AQR; Pharma: USFDA actions)

Events come from a shared `/mockups/fixtures/events.json` file in V1
(hand-curated for top ~30 events). V1.1 externalises to backend.

---

## §2 · Page tree (locked)

| # | Page | Path | New/Existing | Monday ships as |
|---|---|---|---|---|
| 1 | Today / Pulse | `/mockups/today.html` | Existing (needs rework) | Mockup |
| 2 | Explore · Global | `/mockups/explore-global.html` | Existing (stripped) | Mockup |
| 3 | Explore · Country (+ breadth) | `/mockups/explore-country.html` | Existing (stripped) | Mockup |
| 4 | Explore · Sector (+ breadth) | `/mockups/explore-sector.html` | Existing (stripped) | Mockup |
| 5 | Stock detail | `/mockups/stock-detail.html` | Existing (stripped) | Mockup |
| 6 | MF detail | `/mockups/mf-detail.html` | Existing (partial strip) | Mockup |
| 7 | MF rank | `/mockups/mf-rank.html` | **NEW** | Mockup |
| 8 | Breadth Terminal | `/mockups/breadth.html` | **NEW** | Mockup |
| 9 | Portfolios | `/mockups/portfolios.html` | Existing (stripped) | Mockup |
| 10 | Lab / Simulations | `/mockups/lab.html` | **NEW** | Mockup |
| — | Global search | top-nav component | **NEW** (across all pages) | Component |

Out of scope for Monday: Reports, Watchlist.

---

## §3 · Today / Pulse

**Purpose:** The 30-second morning open. Macro regime, breadth health,
top factor moves, day's top movers. One screen, no scroll ideally.

### Block list

1. **Hero strip** — date, last refresh IST, universe selector (NSE /
   Global), 4 KPI chips: Nifty 50 level + Δ, USDINR, 10Y G-Sec yield,
   India VIX.
2. **Regime band** — left half: structural classifier tag (Expansion /
   Correction / Distress) + days-in-regime counter. Right half: 4-chip
   RRG readout for Nifty 500 (RS vs MSCI EM, Momentum, Volume,
   Breadth).
3. **Breadth mini** — 3 KPI cards (% above 21-EMA, % above 50-DMA, %
   above 200-DMA), each with sparkline. Clicks through to Breadth
   Terminal.
4. **Sector board** — 11 sector tiles in grid. Each: sector name, 4
   RRG chips, RS sparkline vs Nifty 500. Sorted by RS composite
   descending.
5. **Movers** — two tables side by side: Top 10 gainers, Top 10 losers
   of the day. Columns: symbol, sector, Δ%, volume ratio, RS state.
6. **Fund mover strip** — top 5 MFs by 1-day NAV Δ that are in the
   universe. Columns: name, category, 1D, 1M, rs_composite.
7. **EXPLAIN footer** — "What is this page" block. Two sentences.

### API bindings (Stage 2)
- Hero: `/api/v1/global/indices`, `/api/v1/global/fx`, `/api/v1/global/rates`
- Regime: `/api/v1/stocks/breadth` (regime classifier field)
- Sector board: `/api/v1/sectors/rrg`
- Movers: `/api/v1/stocks/movers`
- Fund strip: `/api/v1/mf/universe?sort=1d_return&limit=5`

### V1.1 rule-hook slot
- Below regime band: `rec-slot` for "today's regime shift" fires.

---

## §4 · Explore · Global

**Purpose:** Macro regime dashboard. Global risk factors that set the
tone for India. DXY, US rates, credit, commodities, FX, global breadth,
sectors RRG.

### Block list (keeps existing, post-strip)

Order locked from existing mockup (already stripped of commentary +
portfolio call):

1. Regime
2. Macros
3. Yields
4. FX
5. Commodities
6. Credit
7. Risk (VIX, MOVE)
8. RRG (global sector rotation)

### V1 additions
- Each section gains `explain-block` below title (formula + reading).
- `describe-block` on each KPI giving current z-score reading.
- Info tooltips on every table column.

### V1.1 rule-hook slot
- Top of page: `rec-slot` for "global regime shifts" (Faber 10M rule firing at global index level).

---

## §5 · Explore · Country (India) — with embedded breadth

**Purpose:** India-level deep dive. Breadth, derivatives, rates, FX,
flows, sectors RRG.

### Block list (order locked, existing + breadth deep extension)

1. **Regime** (India-specific classifier)
2. **Breadth panel** (EXPANDED — see §5.1 below)
3. **Derivatives** (PCR, India VIX, max pain)
4. **Rates · G-Sec** (yield curve, 2s10s, real yields)
5. **INR** (USDINR chart + event markers)
6. **FII / DII** (daily flows + cumulative)
7. **Sectors RRG** (12 India sector tiles, same chip vocab)

### 5.1 Breadth panel (embedded from §10 Breadth Terminal)

Not a card — a full section. Compact version of the canonical Breadth
Terminal. Contains:
- Three KPI cards: % above 21-EMA, % above 50-DMA, % above 200-DMA
  (current value + d/d + % of universe)
- **Breadth oscillator chart** — 5Y default range, with overlays:
  - Primary: % above selected MA (toggle: 21-EMA / 50-DMA / 200-DMA)
  - Overlay: Nifty 500 index on secondary Y-axis
  - Zone bands: OB ≥400, Midline 250, OS ≤100
  - Event markers (elections, RBI, COVID, etc.)
- **Zone-crossing history** table: date, indicator, event (entered OB, exited OS), value held for N days
- "Open full Breadth Terminal" link → `/mockups/breadth.html?universe=nifty500`

All text is EXPLAIN + DESCRIBE tier. No RECOMMEND.

### V1.1 rule-hook slot
- Breadth panel footer: `rec-slot` for Rule #1 (%>200DMA regime
  shift) and Rule #2 (Zweig Breadth Thrust) fires.

---

## §6 · Explore · Sector — with embedded breadth

**Purpose:** Per-sector deep dive. Member stocks, fundamentals, macro
sensitivities, PLUS sector-level breadth (new).

### Block list

1. **State** (sector-level 4 chips, hero stats vs N500)
2. **Breadth panel (sector universe)** — NEW section, same pattern as
   §5.1 but universe = members of this sector. E.g. for Nifty IT,
   "% of 10 IT stocks above 21-EMA". Same oscillator + zones + events.
3. **Member stocks** (existing data table, now with all 4 RRG chips
   per row + info tooltips on every column)
4. **Fundamentals** (aggregated sector P/E, EPS growth, margin —
   gains formula disclosure + 10Y z-scores)
5. **Macro sensitivities** (existing sens table, gains `ⓘ` on each
   macro variable)

### V1.1 rule-hook slot
- Below Breadth panel: `rec-slot` for sector-level rule fires.
- Below Members: `rec-slot` for ENTRY_CANDIDATE fires on individual
  member stocks.

---

## §7 · Stock detail

**Purpose:** Single-stock terminal. Chart, risk, technical, fundamental,
RS vs bench + peers, corporate actions, news.

### Block list (existing, post-strip)

1. Hero strip (symbol, price, sector, market cap, 4 RRG chips)
2. Detail tabs (existing)
3. Col 1: Chart + News
4. Col 2: Risk + Technical + Fundamental snapshots
5. Col 3: RS panel + Corporate Actions

### V1 additions
- Every KPI card gains `ⓘ` tooltip with formula.
- Chart gains `explain-block` below: "This is a 5Y daily candle chart
  with 50-DMA (blue) and 200-DMA (red) overlays. Key events marked."
- Peer comparison table gets info tooltips on every column (P/E,
  ROE, D/E, RS, etc.).
- Fundamental section gains formula disclosure inline.

### V1.1 rule-hook slot
- Hero right edge: `rec-slot` for Minervini Trend Template firing
  (Rule #4), IBD RS Rating ≥80 (Rule #5), relative-volume breakout
  (Rule #7).
- Below News: `rec-slot` for WARNING fires (RSI divergence Rule #6).

---

## §8 · MF detail

**Purpose:** Single-MF terminal. Returns, alpha quality, holdings,
sector breakdown, rolling metrics, peer comparison, suitability.

### Block list (existing, cleaned of verdict blocks)

1. Hero (fund name, category, AMC, AUM, 4 RRG chips, 3Y Sharpe, 3Y alpha)
2. Section A: Returns table + rolling returns chart
3. Section B: Alpha quality (Jensen's alpha, Treynor, info ratio, capture ratios)
4. Section C: Risk (3Y vol, max DD, downside dev, VaR)
5. Section D: Holdings (top 20 with weights + concentration)
6. Section E: Sector allocation (vs benchmark)
7. Section F: Rolling alpha + Rolling beta (3Y window)
8. Section G: **Suitability** (renamed from "Suitability & Verdict") —
   Suitability matrix + SIP outcomes + Peer comparison table. Final
   verdict block + Fund tags STRIPPED.

### V1 additions
- Every Section gets EXPLAIN block: formula for Sharpe, Jensen's
  alpha, Treynor, IR, upside/downside capture, etc.
- Every column in peer tables gets `ⓘ`.
- Holdings table gains "Why this weight" tooltip on the weight column
  linking to fund's mandate.

### V1.1 rule-hook slot
- Section G footer: `rec-slot` for "HOLD / ADD / EXIT" call (bound to
  future rule engine that scores MF conviction).

---

## §9 · MF rank (NEW — replaces "Mutual Fund Pulse")

**Purpose:** Rank the MF universe by a 4-factor composite, let the FM
sort / filter / drill in. Replaces the old Pulse page.

### Block list

1. **Hero** — "MF Rank · Nifty-categorised open-ended equity" +
   `data_as_of` date + universe size (e.g. "347 funds across 11 categories").
2. **Filter rail** (left sidebar):
   - Category (multi-select: Large / Mid / Small / Flexi / Multi /
     Focused / ELSS / Hybrid · agg / Hybrid · bal / Debt · short / Debt · long / Index / Sectoral)
   - AUM band (< ₹500 cr, ₹500 cr – ₹5 kcr, ₹5 kcr – ₹25 kcr, > ₹25 kcr)
   - Benchmark
   - Min fund age (1Y, 3Y, 5Y, 10Y)
   - SEBI risk level
3. **Scoring panel** (top of main area) — EXPLAIN of the 4-factor
   framework + formula for each factor. Always visible.
4. **Rank table** — the main artefact. Columns:
   - Rank (1, 2, 3…)
   - Fund name + AMC
   - Category
   - AUM (₹ cr)
   - **Returns score** (0–100) + sparkline of rank history
   - **Risk score** (0–100) + sparkline
   - **Resilience score** (0–100) + sparkline
   - **Consistency score** (0–100) + sparkline
   - **Composite** (avg of 4) + tie-break marker
   - 4 RRG chips (RS, Mom, Vol, Breadth on underlying holdings)
   - Quick-actions: Open MF detail · Add to compare
5. **Formula disclosure block** (bottom-of-page, always visible):

   ```
   Returns score (0–100):
       z = (excess_return_1Y + excess_return_3Y + excess_return_5Y) / 3
           where excess = fund_return − category_benchmark_TRI_return
       score = 100 × Φ(z)  where Φ is the standard normal CDF
   Risk score (0–100):
       z = −1 × (0.4·vol_3Y + 0.4·max_dd_3Y + 0.2·downside_dev_3Y)
       (negative so lower risk = higher score)
       score = 100 × Φ(z)
   Resilience score (0–100):
       z = −1 × (0.6·downside_capture_3Y + 0.4·worst_rolling_6M_return)
       score = 100 × Φ(z)
   Consistency score (0–100):
       z = (0.5·rolling_12M_alpha_median + 0.5·pct_rolling_periods_beating_bench)
       score = 100 × Φ(z)
   Composite = (Returns + Risk + Resilience + Consistency) / 4
   Tie-break order: Consistency → Risk → Returns → Resilience
   ```

6. **Methodology footer** — data_as_of, source attribution, universe
   definition, rebalance cadence (daily EOD).

### API bindings (Stage 2)
- `/api/v1/mf/universe` (universe + filters)
- `/api/v1/mf/{id}/weighted-technicals` (RRG chips)
- `/api/v1/mf/{id}/rs-history` (sparklines)
- New route needed: `/api/v1/mf/rank` (4-factor composite) —
  **backlog item for V1.1**, mockup computes on fixture data.

### V1.1 rule-hook slot
- Top of table: `rec-slot` for "screen: high-consistency + low-AUM" type
  rule fires.

---

## §10 · Breadth Terminal (NEW — canonical)

**Purpose:** The full breadth cockpit. One standalone page. Embedded
compact version lives on Explore · Country (§5.1) and Explore · Sector
(§6). Light design language (NOT dark, per locked system).

### URL params
- `?universe=nifty500` (default) — also: nifty50, nifty_midcap150, nifty_smallcap250, or sector= e.g. `sector=nifty_it`
- `?ma=21ema` — also: 50dma, 200dma, all

### Block list

1. **Hero strip** — "Breadth · {universe} · Terminal"
   - Three headline numbers: 21-EMA count, 50-DMA count, 200-DMA count
     (each /500 or /N depending on universe size)
   - Last updated IST + "N sessions / EOD"
   - Universe selector pill, MA selector pill
2. **Regime band** — Structural classifier (Expansion / Correction /
   Distress) + days-in-regime. Description text is DESCRIBE tier only
   (no recommendation). `rec-slot` reserved for V1.1.
3. **Three KPI cards** — Above 21-EMA / 50-DMA / 200-DMA:
   - Big count (178/500)
   - d/d delta
   - % of universe
   - BULLISH / BEARISH tag (deterministic: >midline = BULLISH,
     <midline = BEARISH, no opinion)
4. **Breadth oscillator chart** — THE centrepiece:
   - 5Y daily series by default, range buttons 1M / 3M / 6M / 1Y / 5Y / ALL
   - Primary Y-axis (left): breadth count 0–500
   - Secondary Y-axis (right): underlying index (Nifty 500, etc.)
   - Zone bands: OB ≥400 (red tint), Midline 250 (grey line), OS ≤100 (green tint)
   - Dot annotations where breadth entered OB / OS zones
   - Event markers (elections, RBI, COVID, Budget, sector shocks)
   - Toggles: index overlay on/off, events on/off
5. **Zone reference panel** (right rail):
   - OB threshold, Midline, OS threshold
   - Current reading: current, Δ1d, Δ5d, Δ20d, 60D high, 60D low, 60D avg
6. **DESCRIBE block** (right rail, always on):
   - Deterministic paraphrase of current state.
   - Example: "At 178, breadth is below midline (250) and 193 below
     its 20-day level. In the past 60 sessions the oscillator has
     ranged 118–404. 3 zone events in this window: OB entry 25-Mar,
     OB exit 02-Apr, current drift toward OS zone."
   - NO action language.
7. **Signal history table** — chronological log of zone events:
   - Date, Indicator (21EMA / 50DMA / 200DMA), Event (entered OB,
     exited OS, crossed midline), Value at event, Days in previous zone
   - Filter chips: All / 21 EMA / 50 DMA / 200 DMA / BULLISH / BEARISH
   - 5Y default range, CSV export
8. **EXPLAIN block** (below chart):
   - Formula: "% above 21-EMA = count(close > EMA21) / count(universe constituents) × 100"
   - Reading: "Readings below 100 mark oversold extremes where bounces are historically likely. Above 400 signal overbought conditions where consolidation/pullback typically follows."
   - Provenance: "Source: JIP de_stock_price_daily · computed by ATLAS breadth service · EOD."
9. **Methodology footer** — data as of, last rebuild, universe
   definition, MA calculation window.

### Data model (for mockup fixtures)
- `breadth_timeseries.json` — 5Y of daily `{date, ema21_count, dma50_count, dma200_count, index_close}`
- `zone_events.json` — list of `{date, indicator, event_type, value, prior_zone_duration_days}`
- `events.json` — shared with other 5Y charts

### API bindings (Stage 2)
- `/api/v1/stocks/breadth?universe=X&range=5y`
- `/api/v1/stocks/breadth/zone-events?universe=X&range=5y`
- `/api/v1/global/events` (new — shared events feed)

### V1.1 rule-hook slots
- Regime band: Rule #1 (%>200DMA) + Rule #10 (Faber 10M SMA) outputs
- Signal history header: Rule #2 (Zweig Breadth Thrust) fires
- Right rail bottom: conviction-chip strip (CONV / DIV)

---

## §10.5 · Signal Playback (reusable simulator block)

**Purpose:** A breadth-driven entry/exit simulator that can be dropped
onto any instrument page. The base pattern is
`frontend/mockups/breadth-simulator-v8.html` — it takes a breadth series
(count of stocks above a chosen MA, Nifty 500 default) + an instrument
NAV/price series and replays a threshold-based SIP + lumpsum + staged
sell + staged redeploy strategy historically. Output is an equity curve
vs benchmark B&H, full transaction log, cashflow ledger (XIRR-ready),
and FY-level tax analysis.

This block is embedded (compact version) on three pages and full on
two:

- **§10 Breadth Terminal** — full block, universe-level (default: Nifty
  500 breadth vs Nifty 500 TRI)
- **§8 MF detail** — compact block under performance (breadth vs fund NAV)
- **§7 Stock detail** — compact block (breadth vs stock close)
- **§6 Explore · Sector** — full block (sector breadth vs sector index)
- **§12 Lab / Simulations** — full block, part of the broader strategy
  bench

Light design language (NOT the dark base file — translate to tokens
from §1.5). No LLM narrative. Every parameter labeled, every threshold
named, every resulting trade logged.

### 10.5.1 Input panel (10 parameters, all editable, all defaultable)

| # | Parameter | Default | Units | Role |
|---|-----------|---------|-------|------|
| 1 | Initial Investment | 1,00,000 | ₹ | Lumpsum on day 1 |
| 2 | Monthly SIP | 10,000 | ₹ | Deployed first session of each calendar month while SIP is on |
| 3 | Lumpsum (Count<L_os) | 50,000 | ₹ | One-shot deposit when breadth drops below L_os (default 50); 30-day cooldown |
| 4 | Sell % at Count≥L_ob | 30 | % of units | First profit-take when breadth ≥ L_ob (default 400) |
| 5 | Further Sell Below Level | 250 | breadth count | Second sell trigger (downcross) |
| 6 | Further Sell % | 20 | % of units | Size of second sell |
| 7 | 1st Redeploy Below Level | 125 | breadth count | First redeployment trigger (downcross) |
| 8 | 1st Redeploy % | 50 | % of liquid | Size of first redeploy |
| 9 | 2nd Redeploy Below Level | 50 | breadth count | Second redeployment trigger (downcross) |
| 10 | 2nd Redeploy % | 100 | % of liquid | Size of second redeploy (typically 100%, clears cash) |

- **"Set % to 0 to disable any rule"** — baked-in escape hatch on every
  percentage.
- **"Run Simulation"** button recomputes in-browser (V1 mockup uses
  bundled fixture; Stage 2 calls `/api/v1/simulate/breadth-strategy`).
- Liquid cash accrues at 6% p.a. (compounded daily) — labelled
  "LIQUID @ 6% PA" in the tile row, editable in V1.1.

### 10.5.2 Rules (evaluated per session, in order)

1. **Liquid accrual** — `liq *= (1 + 0.06/365)^days` between sessions.
2. **SIP** — if `sipOn && !exitMode` and calendar-month changed vs
   previous session, deposit `sip` at that session's NAV.
3. **Opportunity lumpsum** — if `count < L_os` and ≥30 days since last
   lumpsum, deposit `lump`.
4. **Exit-mode trigger** — when `count` upcrosses 350: stop SIP, set
   `exitMode=true`.
5. **First profit-take** — when `count ≥ L_ob` in exitMode and not yet
   sold: sell `Sell%@L_ob` of units FIFO; **post-tax** proceeds go to
   liquid case.
6. **Second profit-take** — when `count` downcrosses `fLvl` (250
   default) AND first sell already done AND not yet sold-further: sell
   `fPct%` of units FIFO; post-tax to liquid.
7. **SIP resume** — when `count` downcrosses 200: `sipOn=true`,
   `exitMode=false`.
8. **First redeploy** — when `count` downcrosses `rdLvl` (125 default)
   AND there is liquid from prior sells AND not yet redeployed:
   deploy `rdPct%` of liquid at that session's NAV.
9. **Second redeploy** — when `count < rd2Lvl` (50 default) AND liquid
   > 0 AND not yet done: deploy `rd2Pct%` of liquid.
10. **Cycle reset** — when `count ≥ L_ob` again AND both redeploys are
    done: clear all flags so the next cycle can trigger.

All crossings are **edge-triggered** on `prevCount → count` transitions
(no re-firing on consecutive sessions while in-zone).

### 10.5.3 Tax engine (locked, FIFO, India regime-aware)

- **FIFO lot tracker** — every buy pushes `{date, nav, units,
  remaining}`; every sell drains oldest-first.
- **Holding period** — LTCG if `holdDays > 365`, else STCG.
- **Regime split** on sell date:
  - Sell before **2024-07-23**: STCG 15%, LTCG 10%, LTCG FY-exemption
    ₹1,00,000.
  - Sell on/after 2024-07-23: STCG 20%, LTCG 12.5%, LTCG FY-exemption
    ₹1,25,000.
- **Cess** 4% on (STCG tax + LTCG tax).
- **Exemption** applied at FY level in the Tax Analysis tab, not at
  each sell.
- **Unrealised-if-sold-today** panel computes what would be owed on
  remaining lots using the current (post-2024-07-23) regime.

### 10.5.4 Benchmark B&H (mandatory overlay)

For apples-to-apples: the simulator replays the **same cash
deployments** (initial + every SIP + every opportunity lumpsum — i.e.
the deposit schedule, NOT the sell/redeploy behaviour) on **Nifty 50
TRI** and **Nifty 500 TRI** pure buy-and-hold. That gives the FM a
three-way read:

- Strategy equity curve (active, with breadth-driven sells/redeploys)
- Nifty 50 B&H on the same cashflows
- Nifty 500 B&H on the same cashflows

Breadth count is overlaid as a secondary Y-axis line so you see rule
triggers visually against the curves.

### 10.5.5 Output blocks (top to bottom)

1. **Input panel** (as above) + Run button.
2. **KPI tile row:**
   - Total Invested, Final FV, Liquid Cash, Final Total
   - XIRR (pre-unrealised-tax), CAGR, Absolute Gain %
   - vs Nifty 50 B&H (Δ % vs strategy), vs Nifty 500 B&H
   - Total Tax Paid (realised), Unrealised STCG, Unrealised LTCG,
     Unrealised Tax
   - **Post-all-tax** Total / CAGR / XIRR (after notional exit)
3. **Equity Curve vs Benchmark Indices chart:**
   - Legend: Strategy | Nifty 50 B&H | Nifty 500 B&H | Breadth Count (right axis) | Invested Line
   - Event markers from §1.7 events.json overlaid
   - Zone bands (OB ≥ L_ob red tint, OS ≤ L_os green tint) on breadth axis
   - Hover tooltip: date, strategy value, N50, N500, breadth count, cumulative invested
4. **Tabs below chart:**
   - **Transaction Log** — date, action, amount, NAV, breadth count, units, liquid, FV, STCG tax, LTCG tax, total tax. One row per event: Initial, SIP, Lumpsum(Count<L_os), Sell@≥L_ob, Sell@<fLvl, SIP Stopped, SIP Resumed, Redeploy@<rdLvl, Redeploy@<rd2Lvl.
   - **Cashflow** — the XIRR input series: date, amount (-ve = deposit, +ve = final redemption).
   - **Tax Analysis** — grouped by FY (`FY2023-24`, `FY2024-25`, …): STCG realised, LTCG realised, LTCG exemption used, taxable LTCG, tax paid, cess, total.
5. **EXPLAIN block** (collapsible):
   - What each rule does, in one sentence, with the threshold name.
   - XIRR formula, CAGR formula, FIFO mechanics.
   - Source: `/api/v1/stocks/breadth` (breadth series) +
     `/api/v1/mf/{id}/nav-history` or `/api/v1/stocks/{symbol}/prices`
     (instrument) + `/api/v1/benchmarks/nifty50,nifty500`.
6. **Methodology footer** — data as of, universe used, tax regime
   cutoff, liquid-rate assumption, deterministic (same inputs ⇒ same
   output).

### 10.5.6 Component contract (for S1-0 shared components)

- `signal-playback.html` — single reusable partial, id-based params
  `i_initial, i_sip, i_lumpsum, i_sell400, i_furtherLvl, i_furtherPct,
  i_redeployLvl, i_redeployPct, i_redeploy2Lvl, i_redeploy2Pct`.
- Accepts a data prop indicating instrument type:
  - `instrument: "mf" | "stock" | "sector" | "index"` — determines
    which NAV/price series to read.
  - `breadth_universe: "nifty500" | "sector:nifty_it" | …`
- Compact embed mode: collapses KPI row to 4 tiles, hides tax tab by
  default (one toggle to expand).
- Full mode: all blocks shown.

### 10.5.7 Fixtures (for Stage 1 mockups)

- `fixtures/breadth_daily_5y.json` — date, 21EMA count, 50DMA count,
  200DMA count, Nifty 500 close, Nifty 500 TRI, Nifty 50 TRI
- `fixtures/ppfas_flexi_nav_5y.json` — date, NAV (sanity sample for
  MF detail embed)
- `fixtures/reliance_close_5y.json` — stock sample (sanity sample for
  Stock detail embed)
- The base simulator JS (from `breadth-simulator-v8.html`) gets
  refactored into `assets/signal-playback.js` and consumed by all five
  embed locations.

### API bindings (Stage 2)

- `/api/v1/stocks/breadth?universe=X&range=5y` (existing)
- `/api/v1/mf/{id}/nav-history?range=5y` (existing)
- `/api/v1/stocks/{symbol}/prices?range=5y` (existing)
- `/api/v1/benchmarks/tri?ids=nifty50,nifty500&range=5y` (Stage 2)
- `/api/v1/simulate/breadth-strategy` (Stage 2 POST — server-side
  reimpl of the JS for Lab / shareable runs)

### V1.1 rule-hook slots

- Replace the hard-coded threshold ladder with a rule-library-driven
  version: rule selector can swap in Rule #1 (%>200DMA), Rule #2
  (Zweig Breadth Thrust), Rule #10 (Faber 10M SMA) as the entry/exit
  signal generator.
- Conviction overlay: when a CONV chip is present at a trade date,
  mark the trade point with a halo.
- `rec-slot` below KPIs for "what the rule engine would recommend
  now at current breadth reading."

---

## §11 · Portfolios

**Purpose:** Four books with holdings, weights, performance. Stripped of
accountability banner + pending-rec ledger.

### Block list (existing, post-strip)

1. Hero (ph-title = "Books", KPI chips: Aggregate AUM, Last reconciled IST)
2. Book grid (4 book cards: Multi-Asset India, IBKR Global, Thematic IT, Conservative Debt+)
3. Per-book expand: holdings table + weight chart + performance vs benchmark

### V1 additions
- Every book card gains formula for its performance metric.
- Every holdings table gains `ⓘ` on Weight, Cost basis, Unrealised P&L columns.

### V1.1 rule-hook slot
- Below each book card: `rec-slot` for ATLAS pending recs on that
  book's instruments.

---

## §12 · Lab / Simulations (NEW)

**Purpose:** Backtest a rule or allocation strategy over historical
data, see equity curve + drawdown + metrics + trade log. Systematic,
reproducible, research-grade. **Includes the §10.5 Signal Playback block
as one of the two lab modes** — "Breadth playback (threshold ladder)"
alongside "Rule backtest (V1.1)".

### Block list

0. **Mode tabs** — `[ Breadth Playback ]` · `[ Rule Backtest (V1.1) ]`
   · `[ Compare ]`. Breadth Playback mode loads the §10.5 block
   verbatim with MF/stock/index picker at the top.
1. **Hero strip** — "Lab · Strategy Simulation" + quick-load chips
   ("Load: Breadth threshold ladder", "Load: Faber 10M", "Load: JT 12-1
   Momentum", "Load: %>200DMA regime overlay")
2. **Strategy config panel** (left, ~320px):
   - Universe selector (Nifty 50 / 500 / Midcap 150 / Smallcap 250 / Custom)
   - Rule selector (dropdown sourced from V1.1 rule library — in V1
     mockup, shows the 10 rules but marked "V1.1" with greyed
     toggle)
   - Parameters (e.g. for Faber: MA window = 10M, rebalance = monthly)
   - Date range (default 10Y, back to 2016)
   - Rebalance frequency (daily / weekly / monthly / quarterly)
   - Transaction costs (bps per side, default 10)
   - Benchmark selector (Nifty 500 TRI default)
3. **Run button** + status indicator
4. **Results section** (right, main area):
   - **Equity curve** — strategy vs benchmark, 10Y line chart with event markers
   - **Drawdown chart** — below equity curve, shared X-axis
   - **Performance KPIs**: CAGR, Vol, Sharpe, Sortino, Max DD, Calmar, Hit rate, avg win / avg loss, Best year, Worst year, YoY consistency
   - **Rolling metrics**: 3Y rolling Sharpe, 3Y rolling alpha, 3Y rolling beta
   - **Trade log** — every entry/exit with date, symbol, action, return contribution
   - **Monte Carlo overlay (toggleable)**: 1000 block-bootstrap resamples, 5/50/95 percentile bands
5. **Compare strategies** (toggle): overlay up to 3 saved runs on the
   same chart.
6. **Export** — CSV of trade log, PDF of results summary.
7. **EXPLAIN block** — formulas for every KPI (CAGR, Sharpe, Sortino,
   Max DD, Calmar), and a paragraph on the backtesting methodology:
   - Look-ahead bias prevention (signal lag)
   - Survivorship bias acknowledged
   - Transaction cost model
   - Rebalancing mechanics
8. **Methodology footer** — universe definition, data source, compute
   date, deterministic seed (for Monte Carlo).

### API bindings (Stage 2)
- `/api/v1/simulate/run` — POST strategy config, get results
- `/api/v1/simulate/results/{run_id}` — GET
- Existing `/api/v1/simulate/*` backbone is already live (V5 chunk)

### V1.1 rule-hook slot
- Rule selector goes live (bound to actual V1.1 rule engine).
- Mockup in V1 shows the 10 rules with "V1.1" tags, toggle disabled.

---

## §13 · Global search (top-nav component)

**Purpose:** One search box, everywhere, finds anything. Fuzzy,
typo-tolerant, partial-match, cross-entity.

### Location
Top-nav bar, right of ATLAS logo, left of user avatar. Fixed on every
page. Keyboard shortcut: `⌘K` / `Ctrl+K`.

### Behaviour
- Debounced input (150ms)
- Fuzzy match algorithm: Jaro-Winkler + token-subset match + n-gram
  (handles "HDFC flexi" → "HDFC Flexi Cap Fund Direct Growth")
- Results grouped by entity type:
  - **Stocks** (symbol + company name)
  - **Mutual funds** (name + AMC + category)
  - **Sectors** (Nifty sector indices)
  - **Indices** (Nifty, Sensex, global)
  - **Currencies** (USDINR, EURINR…)
  - **Macro tickers** (10Y G-Sec, India VIX, DXY)
- Top 3 results per group, up to 15 total
- Keyboard nav (↑ ↓ ↵) + recent searches + "See all results" link

### V1 mockup
- Static fixture of ~200 indexed entities
- Client-side Fuse.js for fuzzy matching (already a lib the project
  allows; zero new infra)

### V1 API binding (Stage 2)
- `/api/v1/search?q=X` — new endpoint, backed by a Postgres tsvector
  + trigram index on the concatenation of all entity names. Backlog.

---

## §14 · V1.1 rule-hook slot index

Master list so V1.1 chunk knows exactly where to bind. Every slot in
V1 renders as an empty placeholder `<div class="rec-slot"
data-rule-scope="X" data-page="Y">`.

| Page | Slot id | Binds to |
|---|---|---|
| Today | `pulse-regime` | Rule #1 (%>200DMA regime shift), Rule #10 (Faber) |
| Explore · Global | `global-regime` | Rule #10 at global index level |
| Explore · Country | `country-breadth` | Rules #1 + #2 (Zweig) |
| Explore · Sector | `sector-breadth` | Rules #1 + #2 at sector universe |
| Explore · Sector | `sector-members` | Rule #3 (JT 12-1), #4 (Minervini), #5 (IBD RS), per member |
| Stock detail | `stock-hero` | Rules #4, #5, #7 (rel vol breakout) |
| Stock detail | `stock-news` | Rule #6 (RSI divergence) |
| MF detail | `mf-suitability` | Composite MF-rule engine (V1.2+) |
| MF rank | `mfrank-screens` | Screen-rule fires (top-quintile + low-AUM etc.) |
| Breadth Terminal | `breadth-regime` | Rules #1, #10 |
| Breadth Terminal | `breadth-signal-header` | Rule #2 (Zweig) |
| Breadth Terminal | `breadth-playback-halo` | Conviction chips decorate trade points on §10.5 block |
| Stock detail | `stock-playback` | §10.5 embed swaps threshold ladder for rule-library signals |
| MF detail | `mf-playback` | §10.5 embed swaps threshold ladder for rule-library signals |
| Explore · Sector | `sector-playback` | §10.5 embed swaps threshold ladder for rule-library signals |
| Portfolios | `portfolio-book-{i}` | Pending-rec fires per book |
| Lab | `lab-rule-selector` | Goes live (rule library activated) |
| Lab | `lab-playback-overlay` | Conviction halos on Breadth Playback mode |

---

## §15 · API binding matrix

Every block on every page → which route it reads. Only Stage 2
concern; V1 mockups hard-code fixtures in `/mockups/fixtures/*.json`.

| Page | Block | Route |
|---|---|---|
| Today | Regime + breadth mini | `/api/v1/stocks/breadth` |
| Today | Sector board | `/api/v1/sectors/rrg` |
| Today | Movers | `/api/v1/stocks/movers` |
| Today | Fund strip | `/api/v1/mf/universe` |
| Explore · Global | Macros / Rates / FX / Commod / Credit | `/api/v1/global/*` |
| Explore · Country | Breadth | `/api/v1/stocks/breadth?universe=nifty500` |
| Explore · Country | Sectors RRG | `/api/v1/sectors/rrg` |
| Explore · Country | Flows | `/api/v1/global/flows` (new, backlog) |
| Explore · Sector | Breadth (sector universe) | `/api/v1/stocks/breadth?universe=sector:nifty_it` |
| Explore · Sector | Members | `/api/v1/stocks/universe?sector=X` |
| Stock detail | Chart + RS | `/api/v1/stocks/{sym}/chart-data`, `/api/v1/stocks/{sym}/rs-history` |
| Stock detail | Peers | `/api/v1/stocks/universe?sector=X&sort=rs_composite` |
| MF detail | Returns + alpha + holdings | `/api/v1/mf/{id}`, `/api/v1/mf/{id}/nav-history`, `/api/v1/mf/{id}/sectors`, `/api/v1/mf/{id}/weighted-technicals` |
| MF rank | Universe + scoring | `/api/v1/mf/rank` (**new, backlog**) |
| Breadth Terminal | Timeseries + zones | `/api/v1/stocks/breadth`, `/api/v1/stocks/breadth/zone-events` (**new**) |
| Portfolios | Books + holdings | `/api/v1/portfolio/*` |
| Lab | Simulate | `/api/v1/simulate/*` |
| Global search | Query | `/api/v1/search?q=X` (**new, backlog**) |

### New backend routes needed (V1.1 / Stage 2 backlog)
1. `/api/v1/mf/rank` — 4-factor composite
2. `/api/v1/stocks/breadth/zone-events` — zone crossing log
3. `/api/v1/global/events` — shared event markers feed
4. `/api/v1/search` — fuzzy cross-entity search

None blocks Monday (Stage 1 is mockup).

---

## §16 · Monday Stage 1 chunk plan

Everything below is one Stage. Each chunk is ~2–4 hours. Can run
serially or parallel (no cross-dependencies within Stage 1 except the
shared components).

| Chunk | Work | Files touched |
|---|---|---|
| **S1-0** | Shared component pass — extract chip, kpi-strip, data-table, sparkline, rs-mini, sector-tile, chart-with-events, search-box, explain-block, describe-block, rec-slot into shared `/mockups/components.css` + `/mockups/_shared.html` partial | `components.css`, `_shared.html` |
| **S1-1** | Kill-list sweep (complete the strip I started, apply EXPLAIN additions) across explore-global, explore-country, explore-sector, stock-detail, mf-detail, portfolios | 6 existing HTML files |
| **S1-2** | Build Breadth Terminal (`breadth.html`) — canonical. Use fixture data. | `breadth.html`, fixtures |
| **S1-2b** | Translate `breadth-simulator-v8.html` from dark→light tokens into reusable `signal-playback.html` + `signal-playback.js`, ported into Breadth Terminal as bottom block. Preserves all 10 inputs, rule logic, FIFO tax engine, Nifty 50/500 B&H overlay. See §10.5. | `signal-playback.html`, `signal-playback.js`, `breadth.html` |
| **S1-3** | Embed breadth panel + compact §10.5 playback into Explore · Country + Explore · Sector + Stock detail + MF detail | 4 existing files |
| **S1-4** | Rework Today / Pulse to new spec | `today.html` |
| **S1-5** | Build MF rank (`mf-rank.html`) — scoring panel + filter rail + rank table + formula disclosure | `mf-rank.html`, fixtures |
| **S1-6** | Build Lab (`lab.html`) — mode tabs (Breadth Playback / Rule Backtest / Compare) + config panel + results area + formula disclosure. Breadth Playback mode reuses §10.5 component | `lab.html`, fixtures |
| **S1-7** | Global search top-nav component — Fuse.js + fixture index + keyboard nav | `_nav-shell.html`, `search.js`, `search-index.json` |
| **S1-8** | V1.1 `rec-slot` placeholders injected per §14 | All 10 pages |
| **S1-9** | Event markers fixture (`events.json`) + render on chart-with-events | `events.json`, `components.css` |
| **S1-10** | Smoke test all 10 pages — every chart renders, every tooltip shows, search works, no console errors. Deploy to atlas.jslwealth.in | — |

Chunk ordering: S1-0 first (unblocks everything), then S1-1..S1-9 can
run in parallel as independent mockup jobs. S1-10 last.

---

## §17 · Out of scope (explicit)

- LLM commentary. Forever banned.
- AI-driven narrative. Forever banned.
- RECOMMEND-tier prose. V1.1 only.
- Reports page. Not in Monday.
- Watchlist page. Not in Monday.
- Configurability / rule-toggle UI. V1.1 with the rule engine.
- Dark mode. Never.
- Any page not listed in §2.

---

## §18 · Acceptance criteria for Stage 1 done

- [ ] All 10 mockup pages render without error in Chrome + Safari + Firefox
- [ ] Every page has hero, EXPLAIN blocks, info tooltips, formula disclosure, methodology footer
- [ ] Breadth Terminal renders 5Y chart with event markers + zone crossings + DESCRIBE block
- [ ] MF rank renders 4-factor composite scoring with tie-break indicator + formula disclosure
- [ ] Lab renders with rule selector (V1.1 disabled state), equity curve, drawdown, KPIs, trade log
- [ ] Global search works on fixture data across all entity types, `⌘K` opens, `↑↓↵` nav, fuzzy match on "HDFC flexi"
- [ ] Zero RECOMMEND-tier prose present (every "BUY / HOLD / reduce" string removed or gated)
- [ ] All V1.1 `rec-slot` placeholders present per §14
- [ ] Deployed to atlas.jslwealth.in/mockups/* and every page click-through works
- [ ] Smoke checklist signed off by FM

---

**End of spec. Monday target: Stage 1 complete, all 10 mockups live for review.**
