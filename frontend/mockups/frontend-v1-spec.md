# ATLAS Frontend V1 — Specification

**Version:** v1.1 (18 Apr 2026) — red-team-driven revision of v1.0.
**Target:** Stage 1 (mockup sweep, all pages) landed by EOD Mon 20 Apr 2026.
**Stage 2** (wire to live APIs + Next.js mount) follows post-Monday.
**Scope:** pure mockup layer, zero API wiring in this stage. HTML only,
served via existing `/mockups/*` symlink. Uses the locked light design
system (`docs/design/design-principles.md`).

**v1.1 change-log (vs v1.0):**
- Added §1.2.1 Gold RS amplifier chip (DP §10) — 5th chip across every instrument row
- Added §1.2.2 Divergences block (DP §10 divergence rule) as mandatory shared component
- Added §1.5 shared components with explicit DP-§ references for `regime-banner`, `signal-strip`, `conviction-chip`, `gold-rs-chip`, `dual-axis-overlay`, `interpretation-sidecar`, `divergences-block`, `signal-history-table`, `four-decision-card`, `simulate-this`
- Added §1.8 Responsive / mobile contract (authoritative: `frontend-v1-mobile.md`)
- Added §1.9 Data states — loading / empty / stale / error (authoritative: `frontend-v1-states.md`)
- Added §1.10 Design-principles cross-reference matrix (enforcement contract)
- Added §1.11 Breadth zone vocabulary reconciliation (terminal-band 100/400 vs simulator-threshold L_os/L_ob)
- Added §2.0 IA reconciliation (8-page memory vs 10-page V1)
- Added §2.1 Hub-and-spoke pre-wiring for §7 Stock detail + §8 MF detail
- §3 Pulse rewritten to DP §12/§13/§10/§15 pattern
- §4 Global rewritten with four-universal-benchmarks (MSCI World · S&P 500 · Nifty 50 TRI · Gold) per DP §3
- §5 Country + §6 Sector rewritten with explicit DP §12/§13/§14/§15/§16 mapping
- §7 Stock detail + §8 MF detail rewritten on shared hub-and-spoke skeleton
- §9 MF rank formula disclosure fixed (dimensional bug: z-score per factor → Φ → average, NOT raw → Φ → average)
- §10 Breadth Terminal blocks rewritten with explicit DP §12-§16 component bindings
- §10.5 Signal Playback — magic numbers 350 (exit trigger) and 200 (SIP resume) elevated to named parameters `L_exit` and `L_sip_resume`
- §14 expanded with slots for Rules #3/#8/#9 (previously unbound) + new §14.1 rule coverage matrix proving every V1.1 rule has ≥1 V1 slot
- §18 acceptance criteria expanded with DP §19 consistency checklist + quality-harness gates

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

### 1.2 Chip vocabulary (RRG + Gold amplifier · locked)

Four RRG chip families. Rendered as pill badges. Colors from the RAG system.

- **RS** — LEADING (green) · IMPROVING (teal) · WEAKENING (amber) · LAGGING (red)
- **Momentum** — ACCEL (green) · STALL (amber) · DECEL (red)
- **Volume** — ACCUM (green) · NEUT (grey) · DISTRIB (red)
- **Breadth** — EXPANDING (green) · NARROW (amber) · THIN (red)

Every instrument panel (stock, MF, sector, index) displays all four.
Fund managers read the quartet at a glance. V1.1 rules bind on top
of these same chips.

#### 1.2.1 Gold RS amplifier chip (mandatory second axis)

Per design-principles §10, every RS row carries a **second RS** computed
against Gold (LBMA PM fix USD for global, MCX Gold INR for India). This
is a **fifth chip** rendered immediately right of the RS chip with a `×`
connector so the visual relationship is obvious.

- **Gold RS** — AMPLIFY+ (petrol filled, Bench+ & Gold+) · NEUTRAL (grey, Bench+ & Gold−) · FRAGILE (amber outline, Bench− & Gold+) · AMPLIFY− (red filled, Bench− & Gold−)

The resulting pair drives the **conviction chip** per design-principles
§10: 4-of-4 aligned = High, 3-of-4 = Medium, 2-of-4 = Divergent, ≤1 = No
signal. Gold-positive combined with Bench-positive upgrades the chip to
`High+` (petrol outline, filled). The conviction chip is a single
derived badge that replaces "BUY" as the headline state on every
recommendation surface, but is informational in V1 (no action label).

**Placement:** RS · × · Gold-RS · ▸ · Momentum · Volume · Breadth · Conviction.
Seven slots total per instrument row. V1 shows all seven; the
Conviction slot renders grey ("no-signal") until V1.1 rules fire.

### 1.2.2 Divergences block (mandatory on multi-factor surfaces)

Per design-principles §10.divergence-rule, any screen that renders more
than one RS factor MUST also render a `divergences[]` block. Empty is
fine; absent is not. Two canonical patterns:

- **Price strong, breadth weak** → narrowing leadership caption
- **Price weak, volume accumulating** → smart money entering caption

In V1 the block renders as a `.card--sm` with a fixed title "Divergences"
and either a bulleted list of detected divergences (V1.1 rule engine
populates) or the literal string "None detected in this window". If the
data feed is incomplete, the block MUST say `insufficient data to
compute divergences` rather than appear empty.

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

| Component | Purpose | Used on | Design-principles §ref |
|---|---|---|---|
| `kpi-strip` | Horizontal row of 4–8 big numbers with labels + deltas | Every page hero | — |
| `data-table` | Sortable, filterable, CSV-exportable tabular data | MF rank, Stock detail peers, Lab outputs, Portfolios | — |
| `sparkline` | Tiny inline trend, 60 × 20 px | Inside table rows, inside chip cards | — |
| `rs-mini` | 80 × 40 px RS line vs benchmark | Instrument cards, table cells | §3 Pattern A |
| `sector-tile` | Large tile with sector name + 4 RRG chips + RS sparkline | Explore · Country, Pulse | §10 |
| `chart-with-events` | Line chart + vertical rules for key events (election, rate cut, COVID) | Breadth terminal, Stock detail, MF detail | §14 |
| `search-box` | Top-nav fuzzy search, typo-tolerant | Every page | — |
| `explain-block` | Title + formula + reading (tier 1 commentary) | Below every chart | §6 |
| `describe-block` | Deterministic readout of current values (tier 2) | Next to every chart | §6 |
| `rec-slot` | V1.1 placeholder; renders empty in V1 | Every page footer | §11 |
| `regime-banner` | `.card--lg` page anchor: regime name (serif) + one-paragraph read + days-in-regime counter. 3px left border in regime RAG token. | **Top of every analytical page** (Pulse, Country, Sector, Stock, MF, Breadth, Lab) | **§12** |
| `signal-strip` | Horizontal row of 3–4 key readings (`label · value · Δ1d`). Immediately below regime banner. | Same pages as `regime-banner` | **§13** |
| `conviction-chip` | 4-factor agreement badge: High / Medium / Divergent / No-signal. Gold-RS amplifier produces High+. | Every RS row, every instrument card, every rec surface | **§10** |
| `gold-rs-chip` | Second-axis RS vs Gold (LBMA PM USD global / MCX INR India). Rendered right of RS chip with `×` connector. | Every RS-bearing row | **§10 amplifier** |
| `dual-axis-overlay` | Indicator (left axis) + price (right axis) + threshold dashed lines + zone-crossing dots. | Breadth terminal, Country/Sector breadth panels, §10.5 sim chart, Stock detail RSI/MACD (when added) | **§14** |
| `interpretation-sidecar` | Right-rail `.card--sm`: auto-generated headline (2–4 words, serif italic, RAG-coded) + 2–4 sentence templated paragraph (bolded keywords in RAG tokens) + `AUTO`/`EDITORIAL` tag. | Right of every analytical chart | **§15** |
| `divergences-block` | `.card--sm` titled "Divergences" showing detected multi-factor disagreements, or `None detected` / `insufficient data` | Every multi-factor surface | **§10 divergence rule** |
| `signal-history-table` | Compact table of zone entry/exit events, filterable by indicator + signal type. Columns: Date · Indicator · Event · Value. | Below every oscillator chart | **§16** |
| `four-decision-card` | Rec-card template enforcing the four explicit fields: `nature` · `size` · `timing` · `instrument`. In V1 renders as empty slot bound to `rec-slot`; populated in V1.1. | Stock detail, MF detail, Portfolios, Lab | **§11** |
| `simulate-this` | Right-aligned button/link on every predictive output. In V1 opens §10.5 Signal Playback pre-filled with that instrument's context. | Every recommendation surface, every zone-crossing event, every portfolio change | **§18** |

**All `regime-banner` and `signal-strip` placements are enforced via
the §1.10 cross-reference table and the `dom_required` checks in
`docs/specs/frontend-v1-criteria.yaml`. A page without both fails the
Stage-1 gate.**

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

### 1.8 Responsive / mobile contract

ATLAS is desktop-first (advisors use large screens) but every page
MUST render without horizontal scroll and without component collisions
down to 360 px. Full mobile+responsive specification lives in
[`docs/design/frontend-v1-mobile.md`](./frontend-v1-mobile.md) and is
authoritative for breakpoints, per-page folding, chart-touch
interactions, and simulator-mobile patterns.

**Breakpoint summary** (details in `frontend-v1-mobile.md`):

| Tier | Range | Treatment |
|---|---|---|
| XL | ≥ 1440 | Full 12-col grid, right-rail sidecars visible |
| L | 1200–1439 | Same grid, sidecars collapse to width-constrained tails |
| M | 960–1199 | 8-col grid, sidecars move below chart as accordion |
| S | 640–959 | 4-col stack, KPI strips wrap to 2 rows |
| XS | 360–639 | 2-col stack, tables gain horizontal scroll, simulator inputs stack |

**Invariants across breakpoints:**
- Regime banner always at top, always visible
- Signal strip always immediately below regime banner
- Chart → Interpretation sidecar coupling preserved (on M/S/XS the
  sidecar moves below, but it remains adjacent)
- Every `data-table` with > 5 columns gets horizontal scroll on M↓
  with the first column sticky
- `⌘K` / `Ctrl+K` search shortcut works on all tiers; touch tap opens
  search modal on XS

### 1.9 Data states (loading / empty / stale / error)

Every block on every page has a defined behaviour for the four
canonical states. Full spec in
[`docs/design/frontend-v1-states.md`](./frontend-v1-states.md) and is
authoritative.

**Four states × four page categories** (summary table):

| State | Meaning | Default UI pattern |
|---|---|---|
| **Loading** | Data fetch in flight | Skeleton screen matching final layout (rows, chart shapes) — never spinner |
| **Empty** | Fetch succeeded, no rows | `empty-state` card: icon + headline + 1-sentence explanation + primary CTA if applicable |
| **Stale** | Fetch succeeded, but `data_as_of` older than freshness threshold for this data type | Amber `data-staleness-banner` above the block: "Data as of 14-Apr-2026, 4 days old — most recent source refresh pending" |
| **Error** | Fetch failed | Red `error-card` with error code + retry button + "fall back to last known" option when available |

**Known-stale JIP sources (hardcoded into staleness thresholds for V1):**
- `de_adjustment_factors_daily` — 0 rows; always shows "not yet available" stub
- `de_global_price_daily` USDINR series — 3-row fallback; banner reads "3-session sample"
- `de_fo_bhavcopy` — 0 rows; derivative-dependent blocks show empty-state
- `INDIAVIX` — 4-day lag vs trading day; banner reads "VIX updates at EOD+1 typically"
- `de_bse_bhavcopy` on weekends / holidays — no banner, just empty-state

Every block that can be stale MUST render a `data_as_of` timestamp;
blocks without one fail the gate.

### 1.10 Design-principles cross-reference table (enforcement contract)

This is the bridge between the locked `docs/design/design-principles.md`
and this V1 spec. Every Stage-1 page MUST satisfy every row applicable
to its page category. The criteria YAML
(`docs/specs/frontend-v1-criteria.yaml`) encodes each row as a
`dom_required` check.

| DP §ref | Component / rule | Pulse | Gbl | Ctry | Sec | Stk | MF | MFrank | Brdth | Port | Lab |
|---|---|---|---|---|---|---|---|---|---|---|---|
| §3 | Benchmark comparison on every quantitative visual | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| §3 | Four universal benchmarks on global/country rows (MSCI World · S&P 500 · Nifty 50 TRI · Gold) | — | ● | ● | ○ | — | — | — | — | — | — |
| §9 | RS is the headline number (not absolute return) | ● | ● | ● | ● | ● | ● | ● | — | ● | ● |
| §10 | 4-factor RRG chip set on every instrument row | ● | ● | ● | ● | ● | ● | ● | — | ● | ● |
| §10 | Gold RS amplifier chip (second axis) | ● | ● | ● | ● | ● | ● | ● | — | ● | ● |
| §10 | Conviction chip (compound derived) | ● | ● | ● | ● | ● | ● | ● | — | ● | ● |
| §10 | `divergences-block` on multi-factor surfaces | ● | ● | ● | ● | ● | ● | — | ● | — | ● |
| §11 | Four-decision template (`nature`·`size`·`timing`·`instrument`) on every rec | ○ | ○ | ○ | ○ | ● | ● | ○ | ○ | ● | ● |
| §12 | Regime banner at top | ● | ● | ● | ● | ● | ● | — | ● | — | ● |
| §13 | Signal strip immediately below regime banner | ● | ● | ● | ● | ● | ● | — | ● | — | ● |
| §14 | Dual-axis indicator + price overlay for oscillators | — | — | ● | ● | ○ | — | — | ● | — | ● |
| §15 | Interpretation sidecar on every analytical chart | ● | ● | ● | ● | ● | ● | ○ | ● | ● | ● |
| §16 | Signal history table below every oscillator | — | — | ● | ● | — | — | — | ● | — | ● |
| §17.2 | Stop level on every buy rec | — | — | — | — | ○ | ○ | — | — | ● | ● |
| §18 | `simulate-this` affordance on every predictive output | ○ | ○ | ○ | ○ | ● | ● | ○ | ● | ● | ● |

Legend: `●` = mandatory render, `○` = mandatory slot (renders empty / V1.1-gated), `—` = not applicable.

### 1.11 Breadth zone vocabulary reconciliation

The Breadth Terminal (§10) uses **fixed** zone boundaries for the
Nifty 500 `% above MA` oscillator:

- `OB_THRESHOLD = 400` (overbought entry)
- `MIDLINE = 250`
- `OS_THRESHOLD = 100` (oversold entry)

The Signal Playback simulator (§10.5) uses **per-run configurable**
thresholds `L_ob` and `L_os` that default to different values
(`L_ob = 400`, `L_os = 50` by default) because the simulator is
explicitly a parameter-sweep tool: the FM wants to see what happens if
the oversold trigger is tightened below the terminal's informational
100 line. **This is intentional** and the spec treats the two as
separate concepts:

| Concept | Purpose | Value | Source |
|---|---|---|---|
| `OB_THRESHOLD` | Informational overbought zone band (tint on chart) | Fixed 400 | §10 Breadth Terminal |
| `OS_THRESHOLD` | Informational oversold zone band (tint on chart) | Fixed 100 | §10 Breadth Terminal |
| `L_ob` (sim param) | First-profit-take trigger in simulator | Default 400 (editable per run) | §10.5.1 input #4 |
| `L_os` (sim param) | Opportunity-lumpsum trigger in simulator | Default 50 (editable per run) | §10.5.1 input #3 |

The simulator renders BOTH sets of bands on its chart: the
informational `OB_THRESHOLD` / `OS_THRESHOLD` as faint persistent
tints, and the active `L_ob` / `L_os` as solid dashed lines labelled
`L_ob = 400` / `L_os = 50`. When the FM changes `L_os` to 100 (to
match the terminal) the dashed line and the tint converge and the
chart reads as one band. **No spec simulator default may silently
overwrite the Breadth Terminal informational bands.**

---

## §2 · Page tree (locked)

### 2.0 Information-architecture reconciliation

The canonical ATLAS IA (memory file `project_atlas_frontend_pages.md`)
describes **8 pages** with hub-and-spoke for instruments: Pulse,
Explorer, Builder, Monte Carlo, Market Sentiment, **Instrument Deep
Dive**, My Watchlist, Reports. V1 ships **10 pages** because it
flattens the hub-and-spoke into two concrete spokes (Stock detail + MF
detail) so they can be built in parallel. The mapping:

| Post-V1 canonical (8-page IA) | V1 (10-page) expression | Merge plan |
|---|---|---|
| Pulse | §3 Today / Pulse | Same |
| Explorer | §4 Global + §5 Country + §6 Sector + §10 Breadth Terminal | Tabs within one Explorer shell in V1.2 |
| Builder | §9 MF rank + §11 Portfolios + (screener, V1.2) | Merged under one "Builder" in V1.2 |
| Monte Carlo / Lab | §12 Lab + §10.5 Signal Playback | Same |
| Market Sentiment | §10 Breadth Terminal (subsumed) | Deferred standalone page to V1.2 |
| Instrument Deep Dive (hub) | §7 Stock detail + §8 MF detail | **Merged into one page in V1.2** — spokes stay, hub presentation unifies |
| My Watchlist | Out of scope for V1 | V1.2 |
| Reports | Out of scope for V1 | V2 |

V1 explicitly chooses 10 flat pages over the 8-page hub-and-spoke so
each mockup can be built as an independent chunk on the new quality
harness. V1.2 will consolidate into the canonical 8-page IA; the
shared components (§1.5) are designed so consolidation is a routing
change, not a rebuild.

### 2.1 Hub-and-spoke pre-wiring (for §7 Stock detail and §8 MF detail)

Even though V1 ships these as separate flat pages, both MUST implement
the shared "instrument deep dive" skeleton so the V1.2 merge is
trivial. Shared skeleton:

1. Hero strip (symbol/name, price/NAV, 4 RRG chips + Gold RS + conviction)
2. Regime banner (global + instrument-universe dual scope)
3. Signal strip
4. Tabs: Overview · Performance · Risk · Fundamentals / Holdings · RS & Peers · News · Simulate
5. Right-rail interpretation sidecar (auto-generated)
6. Right-rail divergences block
7. Bottom: §10.5 Signal Playback compact embed
8. Footer: methodology + data_as_of + provenance

Spoke-specific content lives in tabs; skeleton and chrome are
identical. See §7.0 and §8.0 for per-spoke tab contracts.

### 2.2 Page registry (Monday ships)

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

Out of scope for Monday: Reports, Watchlist, standalone Market
Sentiment, V1.2 hub-and-spoke merge.

---

## §3 · Today / Pulse

**Purpose:** The 30-second morning open. Macro regime, breadth health,
top factor moves, day's top movers. One screen, no scroll ideally.

### Block list (order locked)

1. **`regime-banner` (DP §12)** — top of page. `.card--lg` with
   structural classifier (Expansion / Correction / Distress / Recovery)
   + one-paragraph plain-English read + days-in-regime counter. Left
   3px border in regime RAG token. Global India regime here; V1
   renders Nifty 500 scope, V1.1 adds universe toggle.
2. **`signal-strip` (DP §13)** — immediately below regime banner. 4
   readings: `Nifty 50 level · Δ1d`, `India VIX · Δ1d`, `USDINR · Δ1d`,
   `10Y G-Sec · Δ1d`. Each `label · value · Δ1d`.
3. **Hero strip** — date, last refresh IST (tz-aware), universe
   selector (NSE / Global), `data_as_of` timestamp (required; see §1.9).
4. **RRG quartet + Gold amplifier (DP §10)** — Nifty 500 4-chip RRG
   row (RS vs Nifty 500 own benchmark: MSCI EM, Momentum, Volume,
   Breadth) PLUS Gold RS chip PLUS conviction chip. Seven chip slots
   per §1.2.1.
5. **Breadth mini (DP §14 compact)** — 3 KPI cards (% above 21-EMA,
   % above 50-DMA, % above 200-DMA) each with sparkline. Clicks
   through to Breadth Terminal. Every card bears `data_as_of`.
6. **Sector board (DP §10)** — 11 sector tiles in grid. Each: sector
   name, 4 RRG chips, Gold RS chip, conviction chip, RS sparkline vs
   Nifty 500. Sorted by RS composite descending.
7. **Movers** — two tables side by side: Top 10 gainers, Top 10
   losers. Columns: symbol, sector, Δ%, volume ratio, RS state, Gold RS
   state, conviction chip.
8. **Fund mover strip** — top 5 MFs by 1-day NAV Δ in universe.
   Columns: name, category, 1D, 1M, rs_composite, Gold RS.
9. **`divergences-block` (DP §10 divergence rule)** — right rail.
   Lists detected divergences (price-strong-breadth-weak etc.) across
   the Nifty 500 multi-factor view. V1 renders empty state as "None
   detected in this window" or "insufficient data".
10. **`interpretation-sidecar` (DP §15)** — right rail, auto-generated
    narrative keyed off regime name + current breadth values. Bold keywords
    in RAG tokens. `AUTO` tag top-right.
11. **EXPLAIN footer** — "What is this page" block. Two sentences.

### API bindings (Stage 2)
- Hero: `/api/v1/global/indices`, `/api/v1/global/fx`, `/api/v1/global/rates`
- Regime: `/api/v1/stocks/breadth` (regime classifier field)
- Sector board: `/api/v1/sectors/rrg` (must include Gold RS field —
  new Stage-2 backlog: extend `sectors/rrg` response with `rs_gold`)
- Movers: `/api/v1/stocks/movers`
- Fund strip: `/api/v1/mf/universe?sort=1d_return&limit=5`

### V1.1 rule-hook slots
- Below regime banner: `rec-slot` id `pulse-regime` for Rule #1
  (%>200DMA) + Rule #10 (Faber) fires.
- Below sector board: `rec-slot` id `pulse-sector-screen` for Rule #8
  (sector-rotation screen: top-quintile RS composite).
- Below movers: `rec-slot` id `pulse-movers-screen` for Rule #9
  (breadth-thrust follow-through screener).

---

## §4 · Explore · Global

**Purpose:** Macro regime dashboard. Global risk factors that set the
tone for India. DXY, US rates, credit, commodities, FX, global breadth,
sectors RRG.

### Block list (order locked, post-strip)

1. **`regime-banner` (DP §12)** — global regime. `.card--lg` with
   regime classifier + paragraph + days-in-regime.
2. **`signal-strip` (DP §13)** — 4 readings: `DXY · value · Δ1d`,
   `US 10Y · value · Δ1d`, `VIX · value · Δ1d`, `Gold · value · Δ1d`.
3. **Four-universal-benchmarks row (DP §3)** — for every entity
   rendered on the page the spec MANDATES the 4-column RS strip:
   `RS vs MSCI World · RS vs S&P 500 · RS vs Nifty 50 TRI · RS vs Gold`.
   This replaces the ad-hoc "RRG vs MSCI EM" single-benchmark pattern.
4. Macros (DXY, EM currency index, DM/EM equity indices — all four benchmarks)
5. Yields (US 2Y / 10Y / 30Y, DE Bund, JGB — all four benchmarks)
6. FX (EURUSD, USDJPY, USDCNY, USDINR — four benchmarks)
7. Commodities (Brent, WTI, Copper, Gold, Silver — four benchmarks)
8. Credit (IG spread, HY spread, EMBI — four benchmarks)
9. Risk (VIX, MOVE — four benchmarks)
10. RRG (global sector rotation — each sector gets 4-benchmark strip +
    Gold RS chip + conviction chip per DP §10)
11. **`divergences-block` (DP §10)** — right rail
12. **`interpretation-sidecar` (DP §15)** — right rail, auto-generated

### V1 additions
- Each section gains `explain-block` below title (formula + reading).
- `describe-block` on each KPI giving current z-score reading.
- Info tooltips on every table column.
- Every RS number rendered with its Gold RS counterpart per §1.2.1.

### V1.1 rule-hook slots
- Top of page (below regime banner): `rec-slot` id `global-regime`
  for Rule #10 (Faber 10M) at global index level, Rule #1 (%>200DMA)
  at MSCI World.
- RRG section: `rec-slot` id `global-sector-rotation` for Rule #8
  (sector-rotation screen, global-scope).

---

## §5 · Explore · Country (India) — with embedded breadth

**Purpose:** India-level deep dive. Breadth, derivatives, rates, FX,
flows, sectors RRG.

### Block list (order locked, existing + breadth deep extension)

1. **`regime-banner` (DP §12)** — India-specific classifier. `.card--lg`
   with regime + paragraph + days-in-regime, 3px left border in regime
   RAG token. Dual-scope: if global regime disagrees, surface the
   disagreement in the paragraph (this IS a divergence per DP §12).
2. **`signal-strip` (DP §13)** — 4 readings: `Nifty 500 level · Δ1d`,
   `%>200DMA · value · Δ1d`, `India VIX · value · Δ1d`,
   `USDINR · value · Δ1d`.
3. **Four-universal-benchmarks row (DP §3)** — Nifty 500 benchmarked
   against MSCI World · S&P 500 · Nifty 50 TRI · Gold. Required.
4. **Breadth panel** (EXPANDED — see §5.1 below). MUST use
   `dual-axis-overlay` component per DP §14.
5. **Derivatives** (PCR, India VIX, max pain)
6. **Rates · G-Sec** (yield curve, 2s10s, real yields)
7. **INR** (USDINR chart + event markers)
8. **FII / DII** (daily flows + cumulative)
9. **Sectors RRG** (12 India sector tiles, each with 4 RRG chips + Gold
   RS chip + conviction chip; see DP §10)
10. **`divergences-block` (DP §10)** — right rail
11. **`interpretation-sidecar` (DP §15)** — right rail, auto-generated

### 5.1 Breadth panel (embedded from §10 Breadth Terminal)

Not a card — a full section. Compact version of the canonical Breadth
Terminal rendered in the DP §14 dual-axis-overlay pattern. Contains:

- **Three KPI cards:** % above 21-EMA, % above 50-DMA, % above 200-DMA
  (current value + d/d + % of universe). `data_as_of` on each.
- **`dual-axis-overlay` chart (DP §14)** — THE centrepiece:
  - Primary axis (left): % above selected MA as filled area
    (`--rag-amber-300` 15% alpha fill, `--rag-amber-700` line)
  - Secondary axis (right): Nifty 500 close as thin solid petrol line
    (`--accent-700`)
  - Threshold dashed lines labeled right-edge: `OB 400`
    (`--rag-red-500`), `MID 250` (`--text-tertiary`), `OS 100`
    (`--rag-green-500`), all `stroke-dasharray="3 2"`
  - Zone-entry/exit filled dots on indicator line (red on OB entry,
    green on OS entry); hover tooltip with date + value
  - Event markers (elections, RBI, COVID) from `events.json`
  - Toggle: 21-EMA / 50-DMA / 200-DMA / all-three-overlaid
- **`interpretation-sidecar` (DP §15)** — right rail. Headline
  (2–4 words, serif italic, RAG-coded) + 2–4 sentence auto-generated
  paragraph with bolded RAG-token keywords. `AUTO` tag top-right.
- **`signal-history-table` (DP §16)** — below chart. Columns:
  `Date · Indicator · Event · Value`. Filter chips: All / 21 EMA /
  50 DMA / 200 DMA / Bullish / Bearish. 5Y default range, CSV export.
  Every row traceable to chart annotations.
- "Open full Breadth Terminal" link → `/mockups/breadth.html?universe=nifty500`

All text is EXPLAIN + DESCRIBE tier. No RECOMMEND. The sidecar is
auto-generated narrative derived from current data, not editorial
opinion (`AUTO` tag required; if overridden, `EDITORIAL` tag).

### V1.1 rule-hook slots
- Breadth panel footer: `rec-slot` id `country-breadth` for Rule #1
  (%>200DMA regime shift) + Rule #2 (Zweig Breadth Thrust) fires.
- Signal-history header: `rec-slot` id `country-breadth-thrust` for
  Rule #9 (breadth-thrust follow-through) fires.

---

## §6 · Explore · Sector — with embedded breadth

**Purpose:** Per-sector deep dive. Member stocks, fundamentals, macro
sensitivities, PLUS sector-level breadth (new).

### Block list (order locked)

1. **`regime-banner` dual-scope (DP §12)** — TWO `.card--lg` bands
   stacked: global regime + sector-specific regime. When they disagree
   the paragraph MUST surface the disagreement as a divergence. Left
   3px border in each regime's RAG token.
2. **`signal-strip` (DP §13)** — 4 sector-level readings:
   `Sector RS vs Nifty 500 · value · Δ1d`, `%>200DMA (sector
   universe) · value · Δ1d`, `Sector 12M return · value · Δ1d`,
   `Gold RS · value · Δ1d`.
3. **State** — sector-level 7-chip row per §1.2.1: 4 RRG chips + Gold
   RS chip + conviction chip, plus hero stats vs Nifty 500.
4. **Four-universal-benchmarks row (DP §3)** — sector index vs MSCI
   World · S&P 500 · Nifty 50 TRI · Gold.
5. **Breadth panel (sector universe)** — NEW section, same
   `dual-axis-overlay` + `interpretation-sidecar` + `signal-history-table`
   pattern as §5.1 but universe = members of this sector. E.g. for
   Nifty IT, "% of 10 IT stocks above 21-EMA". Same oscillator +
   zones (note: OB/OS thresholds scale with universe size — for a 10-
   member universe the zone bands are `OB ≥ 8`, `OS ≤ 2`, `MID = 5`).
6. **Member stocks** — existing data table, now with 7-chip row per
   member (4 RRG + Gold RS + conviction) + info tooltips on every
   column. Sort by conviction descending default.
7. **Fundamentals** — aggregated sector P/E, EPS growth, margin with
   formula disclosure + 10Y z-scores
8. **Macro sensitivities** — existing sens table, `ⓘ` on each macro
   variable with beta coefficient + lookback window
9. **§10.5 Signal Playback compact embed** — breadth-of-sector vs
   sector-index playback
10. **`divergences-block` (DP §10)** — right rail
11. **`interpretation-sidecar` (DP §15)** — right rail per block

### V1.1 rule-hook slots
- Below Breadth panel: `rec-slot` id `sector-breadth` for Rule #1
  (%>200DMA, sector-scope) + Rule #2 (Zweig, sector-scope).
- Below Members: `rec-slot` id `sector-members` for Rule #3 (JT 12-1
  momentum screen on members), Rule #4 (Minervini trend-template
  across members), Rule #5 (IBD RS ≥80).
- Below state chip row: `rec-slot` id `sector-rotation` for Rule #8
  (sector-rotation screen — this sector's position in the rotation).
- §10.5 embed: `rec-slot` id `sector-playback` swaps threshold ladder
  for rule-library signal generator.

---

## §7 · Stock detail

**Purpose:** Single-stock terminal. Chart, risk, technical, fundamental,
RS vs bench + peers, corporate actions, news.

### 7.0 Hub-and-spoke skeleton (shared with §8 MF detail)

V1 implements the shared deep-dive skeleton from §2.1. Stock-specific
tab content differs from §8 MF detail in the **Fundamentals** tab
(Stock: EPS / P/E / ROE / D/E / FCF; MF: Holdings / Sector alloc /
Concentration) but the other six tabs (Overview · Performance ·
Risk · RS & Peers · News · Simulate) use the same components with
instrument-typed data.

### Block list (order locked, post-strip)

1. **Hero strip** — symbol, company name, price, Δ1d, sector, market
   cap, `data_as_of`. 7-chip row per §1.2.1: 4 RRG chips + Gold RS
   chip + conviction chip.
2. **`regime-banner` dual-scope (DP §12)** — global India regime +
   sector regime. Disagreement surfaced in paragraph.
3. **`signal-strip` (DP §13)** — 4 readings: `RS vs Nifty 500 · value
   · Δ1d`, `RS vs sector · value · Δ1d`, `Gold RS · value · Δ1d`,
   `Rel vol (21d) · value · Δ1d`.
4. **Four-universal-benchmarks row (DP §3)** — stock vs MSCI World ·
   S&P 500 · Nifty 50 TRI · Gold. Required.
5. **Tabs (hub-and-spoke):**
   - Overview (hero + chart + news)
   - Performance (5Y daily candle + MAs + events)
   - Risk (vol, DD, beta, downside capture, VaR)
   - Fundamentals (EPS / P/E / ROE / D/E / FCF / margins)
   - RS & Peers (peer table with 7-chip row per peer, RS panel, RS-vs-sector chart)
   - News (latest feed + event markers)
   - Simulate (§10.5 full embed)
6. **Chart** — 5Y daily candle + 50-DMA (blue) + 200-DMA (red) +
   event markers. `explain-block` below: "This is a 5Y daily candle
   chart with 50-DMA (blue) and 200-DMA (red) overlays. Key events
   marked." Paired with `interpretation-sidecar` (DP §15).
7. **Right col:** RS panel + Corporate Actions + `divergences-block` +
   `interpretation-sidecar`.
8. **§10.5 Signal Playback compact embed** — breadth vs stock close.
9. **`four-decision-card` (DP §11) rec slot** — `rec-slot` id
   `stock-four-decision`. V1 renders empty placeholder with all four
   fields visible: `nature` · `size` · `timing` · `instrument` · stop
   level. V1.1 populates. Required per DP §11.
10. **`simulate-this` affordance (DP §18)** — right-aligned link on
    every predictive output opening §10.5 pre-filled with this stock.

### V1 additions
- Every KPI card gains `ⓘ` tooltip with formula.
- Every peer table row gets 7-chip row per §1.2.1.
- Fundamental section gains formula disclosure inline.

### V1.1 rule-hook slots
- Hero right edge: `rec-slot` id `stock-hero` for Rule #4 (Minervini
  Trend Template), Rule #5 (IBD RS Rating ≥80), Rule #7 (relative-vol
  breakout).
- RS & Peers tab: `rec-slot` id `stock-momentum` for Rule #3 (JT 12-1
  momentum) — stock's rank in cross-sectional 12-1 momentum screen.
- Below News: `rec-slot` id `stock-news` for Rule #6 (RSI divergence
  WARN).
- Simulate tab: `rec-slot` id `stock-playback` swaps threshold ladder
  for rule-library signal generator.

---

## §8 · MF detail

**Purpose:** Single-MF terminal. Returns, alpha quality, holdings,
sector breakdown, rolling metrics, peer comparison, suitability.

### 8.0 Hub-and-spoke skeleton (shared with §7 Stock detail)

V1 implements the shared deep-dive skeleton from §2.1. Same seven-tab
chrome; Fundamentals tab differs (MF: Holdings / Sector alloc /
Concentration / Top-20 turnover).

### Block list (order locked, cleaned of verdict blocks)

1. **Hero** — fund name, category, AMC, AUM (₹ cr, lakh/crore style),
   3Y Sharpe, 3Y alpha, `data_as_of`. 7-chip row per §1.2.1: 4 RRG
   chips (on underlying weighted holdings) + Gold RS chip + conviction
   chip.
2. **`regime-banner` dual-scope (DP §12)** — global India regime +
   category regime (e.g. "Mid-cap regime: Correction — 12 days").
3. **`signal-strip` (DP §13)** — 4 readings: `RS vs category-bench ·
   value · Δ1d`, `3Y rolling alpha · value · Δ1d`, `Gold RS · value ·
   Δ1d`, `Downside-capture (3Y) · value · Δ1d`.
4. **Four-universal-benchmarks row (DP §3)** — fund vs MSCI World ·
   S&P 500 · Nifty 50 TRI · Gold. Plus category-specific benchmark
   (from DP §3 category table — Mid = Nifty Midcap 150 TRI, etc.).
5. **Tabs (hub-and-spoke):**
   - Overview (hero + NAV chart + key metrics)
   - Performance — Section A: Returns table + rolling returns chart
   - Risk — Section C: 3Y vol, max DD, downside dev, VaR
   - Fundamentals — Section D: Holdings (top 20 with weights +
     concentration) + Section E: Sector allocation vs benchmark
   - RS & Peers — Section B: Alpha quality (Jensen's alpha, Treynor,
     IR, capture ratios) + Section F: Rolling alpha/beta (3Y) + peer
     table with 7-chip row per peer
   - News (feed)
   - Simulate (§10.5 full embed)
6. **Suitability block** (renamed from "Suitability & Verdict") —
   suitability matrix + SIP outcomes + peer comparison table. Final
   verdict block + fund tags STRIPPED (moved to V1.1 rule engine).
7. **NAV chart** — 5Y NAV vs category-bench TRI (DP §3 Pattern A: fund
   solid RAG-coloured line, benchmark dashed grey line). Event markers.
   `explain-block` below. Paired `interpretation-sidecar` right rail.
8. **`divergences-block` (DP §10)** — right rail
9. **§10.5 Signal Playback compact embed** — breadth vs fund NAV.
10. **`four-decision-card` (DP §11) rec slot** — `rec-slot` id
    `mf-four-decision`. V1 renders empty placeholder.
11. **`simulate-this` affordance (DP §18)** — right-aligned link on
    every predictive output.

### V1 additions
- Every Section gets EXPLAIN block with full formula: Sharpe,
  Jensen's α, Treynor, IR, upside/downside capture, etc.
- Every column in peer tables gets `ⓘ`.
- Holdings table gains "Why this weight" tooltip on the weight column
  linking to fund's mandate.

### V1.1 rule-hook slots
- Suitability footer: `rec-slot` id `mf-suitability` for composite MF-
  rule engine (V1.2+) producing HOLD / ADD / EXIT.
- RS & Peers tab: `rec-slot` id `mf-ibd-rs` for Rule #5 (IBD RS on
  fund NAV vs category bench).
- Performance tab: `rec-slot` id `mf-faber` for Rule #10 (Faber 10M
  SMA on fund NAV).
- Simulate tab: `rec-slot` id `mf-playback` swaps threshold ladder for
  rule-library signal generator.

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
   - 7-chip row per §1.2.1: 4 RRG chips (RS, Mom, Vol, Breadth on
     underlying holdings) + Gold RS chip + conviction chip
   - Quick-actions: Open MF detail · Add to compare · `simulate-this`
5. **Formula disclosure block** (bottom-of-page, always visible):

   Every factor is computed as a **cross-sectional z-score within the
   fund's category**, then passed through the standard-normal CDF to
   produce a percentile-equivalent 0–100 score. This makes the four
   factors dimensionally commensurable (all unitless percentiles)
   before averaging — fixing the previous draft where raw returns
   were passed into Φ without normalisation, mixing raw magnitude
   with probability space.

   Notation: for each raw input `x`, define
   `z_cat(x) = (x − mean_category(x)) / stddev_category(x)`
   computed across all funds in the same category (SEBI scheme
   classification).

   ```
   Returns score (0–100):
       raw = (excess_1y + excess_3y + excess_5y) / 3
             where excess_ny = fund_TRI_return_ny − category_bench_TRI_return_ny
       z = z_cat(raw)
       score = round(100 × Φ(z))             where Φ is the standard normal CDF

   Risk score (0–100):
       raw = −1 × ( 0.4·vol_3y + 0.4·max_dd_3y + 0.2·downside_dev_3y )
             (sign flipped so lower risk → higher raw)
             vol_3y and downside_dev_3y expressed as annualised decimals
             max_dd_3y expressed as absolute decimal (e.g. 0.23 for 23% DD)
       z = z_cat(raw)
       score = round(100 × Φ(z))

   Resilience score (0–100):
       raw = −1 × ( 0.6·downside_capture_3y + 0.4·worst_rolling_6m_return )
             downside_capture_3y as a ratio (e.g. 0.85 = captures 85% of
             benchmark's down moves; lower = more resilient)
             worst_rolling_6m_return as decimal (e.g. −0.18)
       z = z_cat(raw)
       score = round(100 × Φ(z))

   Consistency score (0–100):
       raw = 0.5·rolling_12m_alpha_median + 0.5·pct_rolling_periods_beating_bench
             rolling_12m_alpha_median in decimal (e.g. 0.024 = 2.4pp/yr)
             pct_rolling_periods_beating_bench in [0,1]
       z = z_cat(raw)
       score = round(100 × Φ(z))

   Composite = (Returns + Risk + Resilience + Consistency) / 4
             → rounded to 1 decimal

   Tie-break order (applied when composites equal to 1 decimal):
       1. Consistency score (higher wins)
       2. Risk score (higher = lower risk, wins)
       3. Returns score (higher wins)
       4. Resilience score (higher wins)
   ```

   **Why z-score first, then Φ:** raw factor values have incompatible
   units (returns in %, vol in %, max_dd in %, downside capture as
   ratio). Z-scoring within the category puts every fund on the same
   relative scale; Φ converts that scale to a percentile so the four
   scores can be averaged as commensurable percentile-ranks.

   **Minimum universe size per category** for scoring to apply: 5
   funds. Categories with <5 funds display raw factors but composite
   reads `n/a — universe too small`.

   **Data_as_of:** score computed daily EOD against JIP
   `de_mf_nav_daily` + category benchmark from `de_index_daily_tri`.
   Timestamp rendered at top of page and on every row (tooltip).

6. **Methodology footer** — data_as_of, source attribution, universe
   definition, rebalance cadence (daily EOD), minimum universe size
   caveat.

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

### Block list (order locked, DP §12–§16 mapping explicit)

1. **Hero strip** — "Breadth · {universe} · Terminal"
   - Three headline numbers: 21-EMA count, 50-DMA count, 200-DMA count
     (each /500 or /N depending on universe size)
   - Last updated IST + "N sessions / EOD"
   - Universe selector pill, MA selector pill
   - `data_as_of` timestamp (required per §1.9)
2. **`regime-banner` (DP §12)** — `.card--lg` with structural
   classifier (Expansion / Correction / Distress / Recovery) +
   one-paragraph DESCRIBE-tier plain-English read + days-in-regime
   counter. 3px left border in regime RAG token. **Description text is
   DESCRIBE tier only (no recommendation).** `rec-slot` id
   `breadth-regime` reserved for V1.1 Rule #1 + Rule #10.
3. **`signal-strip` (DP §13)** — 4 readings:
   `21-EMA · count · Δ1d`, `50-DMA · count · Δ1d`,
   `200-DMA · count · Δ1d`, `Nifty 500 close · value · Δ1d`.
4. **Three KPI cards** — Above 21-EMA / 50-DMA / 200-DMA:
   - Big count (178/500)
   - d/d delta
   - % of universe
   - BULLISH / BEARISH tag (deterministic: >midline = BULLISH,
     <midline = BEARISH, no opinion — DESCRIBE tier only)
5. **`dual-axis-overlay` breadth oscillator chart (DP §14)** — THE
   centrepiece:
   - 5Y daily series by default, range buttons 1M / 3M / 6M / 1Y / 5Y / ALL
   - Primary axis (left): % above selected MA as filled area
     (`--rag-amber-300` 15% alpha fill, `--rag-amber-700` line)
   - Secondary axis (right): underlying index close as thin solid
     petrol line (`--accent-700`)
   - Threshold dashed lines labeled right-edge: `OB 400`
     (`--rag-red-500`), `MID 250` (`--text-tertiary`), `OS 100`
     (`--rag-green-500`), all `stroke-dasharray="3 2"`. These are
     the informational Breadth Terminal zone bands per §1.11.
   - Zone-entry/exit dots on indicator line — filled RAG-coloured
     circle at each crossing (red on OB entry, green on OS entry).
     Hover tooltip with date + value.
   - Event markers (elections, RBI, COVID, Budget, sector shocks) from
     shared `events.json` fixture
   - Toggles: index overlay on/off, events on/off
6. **Zone reference panel** (right rail):
   - OB threshold, Midline, OS threshold (per §1.11)
   - Current reading: current, Δ1d, Δ5d, Δ20d, 60D high, 60D low,
     60D avg
7. **`interpretation-sidecar` (DP §15)** (right rail, always on):
   - Auto-generated headline (2–4 words, serif italic, RAG-coded)
   - 2–4 sentence paragraph with bolded keywords in RAG tokens
   - `AUTO` tag top-right (or `EDITORIAL` if overridden)
   - Example: "At 178, breadth is **below midline (250)** and
     193 below its 20-day level. In the past 60 sessions the
     oscillator has ranged 118–404. 3 zone events in this window:
     OB entry 25-Mar, OB exit 02-Apr, current drift toward **OS
     zone**."
   - NO action language in V1. V1.1 rule engine may bind an
     action-rider below the sidecar as a `rec-slot`.
8. **`divergences-block` (DP §10 divergence rule)** (right rail) —
   lists detected divergences (price-strong-breadth-weak, etc.) or
   "None detected in this window" / "insufficient data".
9. **`signal-history-table` (DP §16)** — chronological log of zone
   events:
   - Columns: Date · Indicator (21EMA / 50DMA / 200DMA) · Event
     (entered OB, exited OS, crossed midline) · Value at event ·
     Days in previous zone
   - Filter chips: All / 21 EMA / 50 DMA / 200 DMA / BULLISH / BEARISH
   - 5Y default range, CSV export
   - Every row in the table must be traceable to a dot annotation on
     the chart above (proof-layer invariant per DP §16)
10. **EXPLAIN block** (below chart):
    - Formula: "% above 21-EMA = count(close > EMA21) / count(universe constituents) × 100"
    - Reading: "Readings below 100 mark oversold extremes where
      bounces are historically likely. Above 400 signal overbought
      conditions where consolidation/pullback typically follows."
    - Provenance: "Source: JIP de_stock_price_daily · computed by
      ATLAS breadth service · EOD."
11. **§10.5 Signal Playback full embed** — bottom of page. Default:
    Nifty 500 breadth vs Nifty 500 TRI buy-and-hold baseline.
12. **Methodology footer** — data as of, last rebuild, universe
    definition, MA calculation window.

### Data model (for mockup fixtures)
- `breadth_daily_5y.json` (per schema
  `fixtures/schemas/breadth_daily_5y.schema.json`) — 5Y of daily
  `{date, ema21_count, dma50_count, dma200_count, index_close, index_tri}`
- `zone_events.json` (per schema
  `fixtures/schemas/zone_events.schema.json`) — list of
  `{date, indicator, event_type, value, prior_zone_duration_days}`
- `events.json` (per schema `fixtures/schemas/events.schema.json`)
  — shared with other 5Y charts

### API bindings (Stage 2)
- `/api/v1/stocks/breadth?universe=X&range=5y`
- `/api/v1/stocks/breadth/zone-events?universe=X&range=5y`
- `/api/v1/global/events` (new — shared events feed)

### V1.1 rule-hook slots
- `regime-banner`: `rec-slot` id `breadth-regime` for Rule #1 (%>200DMA)
  + Rule #10 (Faber 10M SMA)
- `signal-history-table` header: `rec-slot` id `breadth-signal-header`
  for Rule #2 (Zweig Breadth Thrust) fires
- Right rail bottom: conviction-chip strip (CONV / DIV) per DP §10
- `signal-history-table` footer: `rec-slot` id `breadth-thrust-follow`
  for Rule #9 (breadth-thrust follow-through screener)
- §10.5 embed: `rec-slot` id `breadth-playback-halo` — conviction
  chips decorate trade points on the Signal Playback chart

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

### 10.5.1 Input panel (12 parameters, all editable, all defaultable)

The simulator surfaces **12 parameters** — the original 10 plus two
previously-magic-numbered thresholds (350 exit trigger, 200 SIP
resume) that are now first-class editable inputs per the "no magic
numbers" invariant.

| # | Parameter | Default | Units | Role |
|---|-----------|---------|-------|------|
| 1 | Initial Investment | 1,00,000 | ₹ | Lumpsum on day 1 |
| 2 | Monthly SIP | 10,000 | ₹ | Deployed first session of each calendar month while SIP is on |
| 3 | Lumpsum (Count<L_os) | 50,000 | ₹ | One-shot deposit when breadth drops below `L_os`; 30-day cooldown |
| 4 | Sell % at Count≥L_ob | 30 | % of units | First profit-take when breadth ≥ `L_ob` |
| 5 | `L_os` — Oversold sim trigger | 50 | breadth count | Opportunity-lumpsum threshold (see §1.11 for zone reconciliation) |
| 6 | `L_ob` — Overbought sim trigger | 400 | breadth count | First profit-take threshold |
| 7 | `L_exit` — Exit-mode trigger (upcross) | 350 | breadth count | Stops SIP and arms profit-take ladder (previously magic 350) |
| 8 | `L_sip_resume` — SIP resume (downcross) | 200 | breadth count | Restarts SIP and clears exit mode (previously magic 200) |
| 9 | Further Sell Below Level (fLvl) | 250 | breadth count | Second sell trigger (downcross) |
| 10 | Further Sell % (fPct) | 20 | % of units | Size of second sell |
| 11 | 1st Redeploy Below Level (rdLvl) | 125 | breadth count | First redeployment trigger (downcross) |
| 12 | 1st Redeploy % (rdPct) | 50 | % of liquid | Size of first redeploy |
| 13 | 2nd Redeploy Below Level (rd2Lvl) | 50 | breadth count | Second redeployment trigger (downcross) |
| 14 | 2nd Redeploy % (rd2Pct) | 100 | % of liquid | Size of second redeploy (typically 100%, clears cash) |

*(The heading says "12 parameters" for the two new thresholds; the
table lists 14 total including the original deposit/percentage
inputs. The base simulator had 10 parameters + 2 magic constants =
12 behaviour-determining numbers. All 14 are now in the table.)*

**Zone-vocabulary note:** The defaults `L_os = 50` and `L_ob = 400`
deliberately differ from the Breadth Terminal informational bands
(`OS_THRESHOLD = 100`, `OB_THRESHOLD = 400`). See §1.11 for the
reconciliation: the chart renders BOTH sets of bands, faint
informational tints AND solid simulator-active dashed lines. The FM
is free to set `L_os = 100` to match the terminal.

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
4. **Exit-mode trigger** — when `count` upcrosses `L_exit` (default
   350): stop SIP, set `exitMode=true`.
5. **First profit-take** — when `count ≥ L_ob` in exitMode and not yet
   sold: sell `Sell%@L_ob` of units FIFO; **post-tax** proceeds go to
   liquid case.
6. **Second profit-take** — when `count` downcrosses `fLvl` (250
   default) AND first sell already done AND not yet sold-further: sell
   `fPct%` of units FIFO; post-tax to liquid.
7. **SIP resume** — when `count` downcrosses `L_sip_resume` (default
   200): `sipOn=true`, `exitMode=false`.
8. **First redeploy** — when `count` downcrosses `rdLvl` (125 default)
   AND there is liquid from prior sells AND not yet redeployed:
   deploy `rdPct%` of liquid at that session's NAV.
9. **Second redeploy** — when `count < rd2Lvl` (50 default) AND liquid
   > 0 AND not yet done: deploy `rd2Pct%` of liquid.
10. **Cycle reset** — when `count ≥ L_ob` again AND both redeploys are
    done: clear all flags so the next cycle can trigger.

All crossings are **edge-triggered** on `prevCount → count` transitions
(no re-firing on consecutive sessions while in-zone). Every `L_*`,
`fLvl`, `rdLvl`, `rd2Lvl` is user-editable — nothing hard-coded.

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
data-rule-scope="X" data-page="Y" data-slot-id="Z">`.

| Page | Slot id | Binds to |
|---|---|---|
| Today | `pulse-regime` | Rule #1 (%>200DMA regime shift), Rule #10 (Faber) |
| Today | `pulse-sector-screen` | Rule #8 (sector-rotation screen, top-quintile RS composite) |
| Today | `pulse-movers-screen` | Rule #9 (breadth-thrust follow-through screener on movers) |
| Explore · Global | `global-regime` | Rule #10 at global index level, Rule #1 at MSCI World |
| Explore · Global | `global-sector-rotation` | Rule #8 (global-scope sector rotation) |
| Explore · Country | `country-breadth` | Rules #1 + #2 (Zweig) |
| Explore · Country | `country-breadth-thrust` | Rule #9 (breadth-thrust follow-through) |
| Explore · Sector | `sector-breadth` | Rules #1 + #2 at sector universe |
| Explore · Sector | `sector-members` | Rule #3 (JT 12-1), #4 (Minervini), #5 (IBD RS), per member |
| Explore · Sector | `sector-rotation` | Rule #8 (this sector's position in cross-sector rotation) |
| Explore · Sector | `sector-playback` | §10.5 embed swaps threshold ladder for rule-library signals |
| Stock detail | `stock-hero` | Rules #4 (Minervini), #5 (IBD RS), #7 (rel-vol breakout) |
| Stock detail | `stock-momentum` | Rule #3 (JT 12-1 cross-sectional rank) |
| Stock detail | `stock-news` | Rule #6 (RSI divergence WARN) |
| Stock detail | `stock-four-decision` | DP §11 four-decision-card fires with full rec bundle |
| Stock detail | `stock-playback` | §10.5 embed swaps threshold ladder for rule-library signals |
| MF detail | `mf-suitability` | Composite MF-rule engine (V1.2+) |
| MF detail | `mf-ibd-rs` | Rule #5 (IBD RS ≥80 on fund NAV vs category bench) |
| MF detail | `mf-faber` | Rule #10 (Faber 10M SMA on fund NAV) |
| MF detail | `mf-four-decision` | DP §11 four-decision-card fires |
| MF detail | `mf-playback` | §10.5 embed swaps threshold ladder for rule-library signals |
| MF rank | `mfrank-screens` | Screen-rule fires (top-quintile + low-AUM etc.) |
| Breadth Terminal | `breadth-regime` | Rules #1, #10 |
| Breadth Terminal | `breadth-signal-header` | Rule #2 (Zweig) |
| Breadth Terminal | `breadth-thrust-follow` | Rule #9 (breadth-thrust follow-through) |
| Breadth Terminal | `breadth-playback-halo` | Conviction chips decorate trade points on §10.5 block |
| Portfolios | `portfolio-book-{i}` | Pending-rec fires per book |
| Lab | `lab-rule-selector` | Goes live (rule library activated) |
| Lab | `lab-playback-overlay` | Conviction halos on Breadth Playback mode |

### 14.1 Rule coverage matrix (which Rule fires where)

Cross-check: every one of the 10 V1.1 rules must have ≥1 rec-slot in
Stage-1 where it will bind. If a rule has zero slots, V1 ships
blind to that rule and V1.1 has no anchor point.

| # | Rule (memory `project_rule_engine_v1_1.md`) | Primary slot(s) | Secondary slot(s) | Signal type |
|---|---|---|---|---|
| 1 | %>200DMA regime shift | `pulse-regime`, `country-breadth`, `sector-breadth`, `breadth-regime` | — | REGIME |
| 2 | Zweig Breadth Thrust | `country-breadth`, `sector-breadth`, `breadth-signal-header` | — | ENTRY |
| 3 | JT 12-1 momentum | `sector-members`, `stock-momentum` | `mfrank-screens` (MF equivalent cross-sectional) | ENTRY |
| 4 | Minervini Trend Template | `stock-hero`, `sector-members` | — | ENTRY |
| 5 | IBD RS Rating ≥80 | `stock-hero`, `sector-members`, `mf-ibd-rs` | — | CONFIRM |
| 6 | RSI bearish divergence | `stock-news` | — | WARN |
| 7 | Relative-volume breakout | `stock-hero` | — | ENTRY |
| 8 | Sector rotation screen (top-quintile RS composite) | `pulse-sector-screen`, `global-sector-rotation`, `sector-rotation` | `mfrank-screens` | ENTRY |
| 9 | Breadth-thrust follow-through | `pulse-movers-screen`, `country-breadth-thrust`, `breadth-thrust-follow` | — | CONFIRM |
| 10 | Faber 10M SMA | `pulse-regime`, `global-regime`, `breadth-regime`, `mf-faber` | — | EXIT/REGIME |

**Coverage check result:** every rule has ≥2 slots. Rules #3/#8/#9
now have explicit primary slots (added in v1.1 revision — the
previous draft omitted these). V1.1 binding work has no blind spots.

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

### 18.1 Render + content
- [ ] All 10 mockup pages render without error in Chrome + Safari + Firefox
- [ ] Every page has hero, EXPLAIN blocks, info tooltips, formula disclosure, methodology footer
- [ ] Breadth Terminal renders 5Y chart with event markers + zone crossings + interpretation sidecar
- [ ] MF rank renders 4-factor composite scoring with tie-break indicator + formula disclosure
- [ ] Lab renders with rule selector (V1.1 disabled state), equity curve, drawdown, KPIs, trade log
- [ ] Global search works on fixture data across all entity types, `⌘K` opens, `↑↓↵` nav, fuzzy match on "HDFC flexi"

### 18.2 Design-principles §19 consistency checklist (enforced per page)
A screen that fails any of these is not ATLAS. Every page MUST pass:

- [ ] `regime-banner` at the top (DP §12)
- [ ] `signal-strip` immediately below (DP §13)
- [ ] RS is the headline number, not absolute return (DP §9)
- [ ] Benchmark comparison on every quantitative visual (DP §3)
- [ ] Four-factor conviction chip on every RS call (DP §10)
- [ ] Gold RS amplifier chip alongside every RS chip (DP §10, §1.2.1)
- [ ] Four decisions explicit on every recommendation slot (DP §11)
- [ ] Dual-axis overlay wherever an indicator pairs with price (DP §14)
- [ ] `interpretation-sidecar` on every analytical chart, `AUTO` tagged (DP §15)
- [ ] `signal-history-table` below every oscillator (DP §16)
- [ ] `divergences-block` on every multi-factor surface (DP §10)
- [ ] Stop level on every buy-rec slot (DP §17.2)
- [ ] `simulate-this` affordance on every predictive output (DP §18)
- [ ] S / M / L card sizing only (DP §4)
- [ ] Motion under 150ms, no decorative motion (DP §7)

### 18.3 Governance + quality harness
- [ ] Zero RECOMMEND-tier prose present (every "BUY / HOLD / reduce" string removed or gated)
- [ ] All V1.1 `rec-slot` placeholders present per §14 + every Rule #1–#10 has ≥1 slot per §14.1
- [ ] Every fixture validates against its schema in `/mockups/fixtures/schemas/` (ajv Draft-07)
- [ ] Every page passes `scripts/checks/` 12-check battery (html5_valid, design_tokens_only, kill_list, i18n_indian, chart_contract, methodology_footer, dom_required, fixture_schema, fixture_parity, playwright_a11y, playwright_screenshot, link_integrity)
- [ ] Every page passes `frontend-v1-criteria.yaml` `dom_required` + `dom_forbidden` for its page category in §1.10
- [ ] Mobile contract (§1.8 / `frontend-v1-mobile.md`): every page renders without horizontal scroll at 360 px
- [ ] States contract (§1.9 / `frontend-v1-states.md`): every block has defined loading / empty / stale / error behaviour; every stalable block carries `data_as_of`
- [ ] Deployed to atlas.jslwealth.in/mockups/* and every page click-through works
- [ ] Smoke checklist signed off by FM

---

**End of spec. Monday target: Stage 1 complete, all 10 mockups live for review.**
