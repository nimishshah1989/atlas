---
title: ATLAS Design Principles
status: locked
last-updated: 2026-04-17
---

# ATLAS Design Principles

These are locked design decisions. Every mockup and every production screen must conform. Do not revisit without a recorded design review session.

---

## 1. Surface treatment — locked

**Grey-on-white. Default theme only.**

| Token | Value | Role |
|---|---|---|
| `--bg-app` | `#F7F8FA` | Page background |
| `--bg-surface` | `#FFFFFF` | Cards, panels, tables |
| `--bg-surface-alt` | `#FBFBFC` | Zebra stripes |
| `--bg-inset` | `#F2F4F7` | Code blocks, inset wells |

The Ivory, Paper, and Warm-white theme variants exist in tokens.css for experimentation but are **not in production scope**. Do not ship alternate themes without a product decision.

---

## 2. Color is functional, never decorative

**Two semantic layers. Nothing else.**

### Layer 1: RAG — signal vocabulary (data signals)

Red / Amber / Green is the primary classification system for every quantitative signal.

| Signal | Use | Tokens |
|---|---|---|
| Green | Outperforming, healthy, within limits | `--rag-green-*` |
| Amber | Watch, borderline, needs attention | `--rag-amber-*` |
| Red | Underperforming, breach, alert | `--rag-red-*` |

**Rules:**
- RAG is always icon + label + color together (never color alone)
- Amber is not "warning decoration" — amber means "this needs a decision"
- The absence of RAG on a data point is also a signal (grey = insufficient data)

### Layer 2: Petrol — chrome and identity (brand only)

`--accent-700: #134F5C` (petrol teal) is used **only** for:
- Navigation active states
- Primary action buttons
- Brand identity marker (the atlas. dot)
- "Your fund" / "your portfolio" identity lines in charts

Petrol **must not** be used as a category color in charts or as decorative fill. If you want "the fund" to be petrol in a chart, that's allowed — it means "this is the entity you're analyzing."

---

## 3. Benchmark comparison — mandatory on all quantitative visuals

**ATLAS is a relative strength intelligence platform. Every quantitative output must show performance relative to benchmark.**

This is the single most important design rule: context without a benchmark is incomplete.

### Three standard benchmark patterns

#### Pattern A: Dual line (line charts, area charts, performance charts)
```
Fund   → solid line, RAG-colored (green if outperforming, red if under)
Benchmark → dashed grey line, --text-tertiary (#8A909C), stroke-dasharray="3 2"
Legend → always rendered below chart: "▬ Fund name · +28.4%  - - Benchmark name · +19.1%"
```

#### Pattern B: Active weight bar (bar charts, sector charts)
```
Bars represent fund weight MINUS benchmark weight (signed delta)
Zero line = benchmark allocation
Green bar = overweight + right call (Brinson contribution positive)
Red bar = overweight + wrong call (or underweight + right call flipped)
Grey bar = negligible contribution
```

#### Pattern C: Reference marker (scatter plots, bubble charts)
```
Benchmark appears as a labelled anchor point (grey filled circle, no RAG color)
Label: "Nifty MC 150" or relevant index name
Positioned at its actual risk/return coordinates
All other dots are colored RAG relative to the benchmark dot's position
```

### Alpha display convention

Every visual that shows fund vs benchmark should also display the alpha (outperformance gap):
- Positive alpha: `+9.3pp α` in `--rag-green-700`
- Negative alpha: `−2.9pp α` in `--rag-red-700`
- Near-zero (< 1pp): `+0.7pp α` in `--rag-amber-700`

### Which benchmark?

**India universe (primary benchmark depends on category):**

| Category | Primary benchmark |
|---|---|
| Mid cap | Nifty Midcap 150 TRI |
| Small cap | Nifty Smallcap 250 TRI |
| Large cap | Nifty 50 TRI |
| Flexi / multi-cap | Nifty 500 TRI |
| Thematic | Category-specific (label explicitly) |

**Global / country universe (the four universal benchmarks):**

Every global or country-level instrument is benchmarked against **all four of these** simultaneously, shown as a 4-column RS strip:

| Benchmark | Role |
|---|---|
| **MSCI World** | Global developed-markets reference |
| **S&P 500** | US equity reference (world's deepest risk-asset pool) |
| **Nifty 50 TRI** | Home-market reference (for comparing global picks vs staying home) |
| **Gold (LBMA PM fix, USD)** | Real-asset reference — see §10 Gold RS amplifier |

So a China ETF on the global page shows: `RS vs MSCI World · RS vs S&P 500 · RS vs Nifty · RS vs Gold`. Four numbers, every row, every time.

TRI = Total Return Index (includes reinvested dividends). Never compare against price-only index.

---

## 4. Card sizing — S / M / L only

Three sizes. No exceptions.

| Size | Class | Column span | Use |
|---|---|---|---|
| Small | `.card--sm` | `span-3` or `span-4` | Single KPI, delta pill, narrow stat |
| Medium | `.card--md` | `span-6` | Standard chart, table panel |
| Large | `.card--lg` | `span-12` | Full-width chart, detail view |

Avoid `span-9`, `span-7`, or custom widths. The three-size constraint creates visual rhythm.

---

## 5. Typography constraint

- **Serif** (`--font-serif: Source Serif 4`) for page titles and card headlines only
- **Inter tabular** (`--font-sans` + `font-variant-numeric: tabular-nums`) for all numbers
- **No custom font weights beyond** 400 / 500 / 600 / 700
- **No text decoration, gradient text, or text shadows**

---

## 6. The reading primitive (explainability on every visual)

Every chart or analytical output must have a "reading" component with four zones:

1. **Verdict** — one sentence, plain English, no jargon, RAG-coded
2. **How to read** tab — explains what the chart shows and how to interpret it
3. **Formula** tab — the exact math, with actual values plugged in
4. **Actions** — 2–4 contextual next steps

This is non-negotiable for analytical outputs. Simple KPI metrics can use the compact `verdict-strip` instead.

---

## 7. Motion budget

150ms maximum. No bounces, no springs, no parallax. Transitions exist only to prevent disorientation (e.g., modal entrance), not to delight.

```css
--dur-fast:   100ms;
--dur-normal: 150ms;
--dur-slow:   220ms;  /* modals only */
```

---

## 8. Iconography rules

- Icons are functional (carry information or indicate action), never ornamental
- Every icon appears alongside text or a tooltip — never icon-only in data context
- Icon set: inline SVG, 20×20 viewport, 1.8px stroke, `currentColor`

---

---

## 9. Investment philosophy (the thing the frontend must make obvious)

Every screen in ATLAS is a rendering of one philosophy. The philosophy is not a marketing line, it is a hard design constraint — if a visual does not serve this, it does not ship.

### The philosophy, stated

> **Relative strength is primary. Fundamentals are affirmation, not a filter.** Entries and exits are decided by relative strength alone. Fundamentals explain why the strength is or is not durable. Timing is governed by market breadth, not by trying to pick absolute highs or absolute lows. Risk management and capital protection are non-negotiable, which is why every call carries a pre-defined stop.

### What this means for every screen

1. **RS is the headline, always.** The first number on any instrument / sector / market view is its relative strength score, not its absolute return, not its PE, not its star rating.
2. **Fundamentals sit on the right of the frame, not the top.** They appear as confirmation ("earnings growth is accelerating — affirms the RS breakout") or as a caveat ("earnings are falling — RS is suspect"). They never override an RS call.
3. **Breadth sits at the top as context.** Every page opens with the regime the market is in — `Expansion / Correction / Contraction / Recovery` — because the same RS signal means different things in different regimes.
4. **Alpha, not absolutes.** We do not celebrate "+28% return". We celebrate "+9.3pp α vs Nifty 500 TRI". Every number is shown with its relative counterpart (see §3).
5. **The FM does not chase tops or bottoms.** The UI must never frame a decision as "is this the top?" Instead, it asks "is breadth supporting continuation or rolling over?"

---

## 10. The four-factor relative strength model

RS in ATLAS is a **convergence of four factors**. No single factor is a signal. The strength of a call is the correlation (agreement) across factors.

| Factor | What it measures | Primary tables |
|---|---|---|
| **Returns RS** | Price performance vs benchmark over 1w / 1m / 3m / 6m / 12m | `de_stock_daily`, `de_mf_nav_daily`, `de_etf_daily`, `de_index_daily` |
| **Momentum RS** | Change in RS (Δ), rate of improvement or decay | Derived (rolling window on Returns RS) |
| **Breadth RS** | % of constituents above 21-EMA / 50-DMA / 200-DMA; RSI zones; MACD-bullish %; new-high vs new-low counts | `de_sector_breadth_daily`, per-universe breadth derived tables |
| **Volume RS** | Accumulation vs distribution (volume-weighted) — is smart money buying strength or selling strength? | `de_stock_daily` (volume), `de_mf_flows_*`, `de_fii_dii_flows_daily` |

### The convergence rule (how the UI expresses strength of call)

Every RS-driven call carries a **conviction level** determined by how many factors agree:

| Factors in agreement | Conviction | UI treatment |
|---|---|---|
| 4 of 4 aligned | **High conviction** | Green/red filled chip, bold action label, default bulk-trade size |
| 3 of 4 aligned | **Medium conviction** | Tinted chip, normal action label, standard size |
| 2 of 4 aligned | **Divergent** (watch) | Amber chip, "WATCH" action, small size or skip |
| ≤ 1 aligned | **No signal** | Grey, no action |

### The Gold RS amplifier (second-axis rule)

RS is computed twice at every level: once against the instrument's own benchmark (§3) and once against **Gold** (LBMA PM fix in USD for global, MCX Gold in INR for India). Gold RS does not replace the benchmark RS — it amplifies the conviction by signalling whether the call is also winning against the universal store of value.

| Benchmark RS | Gold RS | Meaning | Conviction effect |
|---|---|---|---|
| Positive | Positive | Winning on alpha **and** beating real assets — durable strength | Upgrade chip to **High+** (filled, petrol outline); this is the "sure-shot" state |
| Positive | Negative | Alpha without macro tailwind — classic sector rotation call | Hold conviction at base level |
| Negative | Positive | Only holding up because real assets are failing — suspect | Downgrade one level, add amber "fragile strength" caveat |
| Negative | Negative | Losing on both axes | Upgrade short/avoid conviction to **High+** |

**UI field:** every RS row renders both scores: `rs_bench · +4.2` and `rs_gold · +2.8`. Visually they sit side-by-side with a small `×` connector indicating the amplifier relationship. The final `conviction` chip carries the compound verdict.

### The divergence rule (where the alpha actually comes from)

When factors **disagree**, the UI must surface the disagreement loudly, not hide it. Divergences are the most information-rich state on any screen. Two canonical patterns:

- **Price strong, breadth weak** → narrowing leadership, reduce size, tighten stops (the breadth terminal's current read — "Correction regime, 17 days in")
- **Price weak, volume accumulating** → smart money entering, watch for RS inflection (Sector Compass `ACCUMULATION` signal)

Every multi-factor surface must render a `divergences[]` block when present. Empty is fine. Absent is not — if the system cannot compute divergences, the block must say so.

---

## 11. From signal to position — the four decisions

Every RS call translates into four concrete decisions. The frontend must make all four explicit on every recommendation surface, never just one.

| Decision | Driven by | UI field |
|---|---|---|
| **Nature** (long / short / skip / hedge) | RS direction (returns + momentum) | `action` chip: `BUY` / `ADD` / `TRIM` / `SELL` / `AVOID` / `HEDGE` / `WATCH` |
| **Size** (bulk / standard / small / probe) | Conviction (factor-agreement count) | `size` field + recommended rupee allocation |
| **Timing** (enter now / wait for breadth / scale in) | Breadth regime + breadth oscillator zone | `timing` field: `NOW` / `ON_BREADTH_CONFIRM` / `SCALE_IN` / `WAIT` |
| **Instrument** (stock / ETF / fund / basket) | Universe and liquidity context | `instrument` field + one-click link to the tradeable |

**UI rule:** A recommendation card is incomplete if any of these four is missing. Do not ship a "BUY HDFCBANK" card. Ship "BUY HDFCBANK · standard size · enter on breadth confirm above 50-DMA · via HDFCBANK direct or BANKBEES ETF".

---

## 12. Regime banner — page anchor pattern

Every instrument/sector/market analytical page opens with a regime banner. Copied from the breadth terminal convention (see `frontend/mockups/refs/breadth-terminal-*.png`):

```
┌─ MARKET REGIME ──────────────────────────────────────────┐
│ Correction    Structural breadth has weakened to        │
│               245/500 above 200-DMA — a correction       │
│               regime. Reduce position sizing, tighten    │
│               stops, wait for a recovery above 250 before│
│               getting aggressive.                  [17d] │
└──────────────────────────────────────────────────────────┘
```

**Required fields (rendered as a `.card--lg` on the white surface per §1):** regime name (`--font-serif`, large), one-paragraph plain-English read (`--font-sans`), days-in-regime counter on the right. Left border 3px in the regime's RAG token: `--rag-amber-500` for Correction, `--rag-green-500` for Expansion, `--rag-red-500` for Contraction, `--accent-500` (petrol) for Recovery. No dark fills — the card is white, the colour comes from the border and the regime-name text.

**Regime is global, universe, and sector-scoped.** The global regime appears at the top of the command-centre. A sector page shows both the global regime and the sector's own regime (they may disagree — that is a divergence, surface it).

---

## 13. Signal strip — top-of-page multi-reading pattern

Directly below the regime banner on every analytical page: a horizontal strip of 3-4 key readings with deltas. The breadth-terminal strip is the reference:

```
21-EMA  178  -7      50-DMA  257  +9     200-DMA  245  +21
```

Rules:
- 3 or 4 readings max. Each reading = `label · value · Δ1d`.
- Delta is RAG-coloured (red negative, green positive).
- Readings are the three most load-bearing numbers on the page, picked for **independent coverage** (short-term, medium-term, long-term on breadth pages; return / momentum / conviction on recommendation pages; etc).
- Values are large, labels small-caps tracking-wider, the whole strip reads left-to-right as a one-glance health check.

---

## 14. Dual-axis indicator + price overlay (the breadth oscillator chart)

Every indicator that can be overlaid against a price series must be shown with both lines on the same frame — indicator on the left axis, price on the right. This is the most information-dense visual in the platform and is mandatory wherever applicable.

Template (rendered in the ATLAS grey-on-white language, §1):

- **Indicator** as filled area — use `--rag-amber-300` at ~15% alpha for fill and `--rag-amber-700` for the line (or the regime-appropriate RAG colour)
- **Price** as a thin solid line on the right axis, in petrol `--accent-700` (Pattern A's "your fund / your series" colour convention from §3 carried in)
- **Threshold lines** dashed at the overbought / midline / oversold levels, each labelled at the right edge (`OB 400`, `MID 250`, `OS 100`). Overbought uses `--rag-red-500`, midline uses `--text-tertiary`, oversold uses `--rag-green-500`. `stroke-dasharray="3 2"` across all three to match Pattern A.
- **Zone entry/exit dots** on the indicator line — filled RAG-coloured circle at each zone crossing (red on overbought entry, green on oversold entry). Hover shows date + value in the tooltip.

Applies to: breadth oscillators (stocks above DMA), RSI, MACD histogram, fund flows, FII/DII net, advance-decline, each vs its relevant price index.

---

## 15. Interpretation sidecar — auto-generated narrative

Every analytical chart carries a right-rail interpretation block that is **generated, not hand-written**. The breadth terminal example:

```
INTERPRETATION · AUTO

Weakening participation

At 178, breadth is below midline and currently
deteriorating over the past week. Indices may hold
up on narrow leadership, but a widening divergence
between price and breadth is a warning to reduce
position sizing and tighten risk.
```

Required structure (rendered on a standard `.card--sm` on the right rail, white surface per §1):
1. **Headline** (2–4 words, `--font-serif` italic, RAG-coded token from §2): captures the state in one phrase
2. **Paragraph** (2–4 sentences, `--font-sans`): templated narrative that plugs current values into regime-aware conditionals. Keywords inside the paragraph (the regime name, the current reading, the direction word) are bolded with the matching RAG token so the paragraph is scannable.
3. **`AUTO` tag** (small-caps tracking-wider, top-right, `--text-tertiary`): signals the narrative is computed from the live data, not editorial. If a human has overridden it, the tag reads `EDITORIAL` instead.

**Rule:** If a chart cannot support a generated narrative, it is not an analytical chart — it's a raw data block, and should be labelled as such. No chart ships without a reading (see §6).

---

## 16. Signal history / zone events table

Below the oscillator chart: a compact table of every zone entry/exit event, filterable by indicator and by signal type (Bullish / Bearish). Columns: `Date · Indicator · Event · Value`.

This is the proof layer. Every narrative claim in §15 must be backed by events in this table. If the interpretation says "breadth rolled over 5 days ago", the row must be visible in the history.

---

## 17. TradingView alerts + stop-loss discipline (first-class UI)

The platform does not just display signals — it **routes them into execution**. Two integration points, both surfaced as UI primitives:

### 17.1 Buy alert → FM approve/deny queue
- TradingView fires a buy alert → appears in `/command-center` as a pending card
- Card carries the four-decision bundle (§11) pre-filled from ATLAS signals
- FM approves → flows to `/actioned` with a live P&L tracker
- FM denies → archived with reason

### 17.2 Stop-loss alert → position protection
- Every approved buy auto-generates a stop-loss alert at a computed level (based on ATR, swing low, or a fixed % — whichever is tighter per the fund's rule)
- Stop-loss alert fires → card moves to `/actioned → Triggered` with exit execution queued
- **Rule:** no buy ships without a stop. UI must refuse to accept a buy approval that does not carry a stop level.

### 17.3 Breadth-triggered bulk entry/exit (the macro layer)
- When the breadth oscillator crosses a zone boundary (enters overbought, exits oversold), a **regime alert** fires
- Regime alerts do not fire per-instrument — they fire as a **playbook trigger** that opens a simulation: "Breadth entered oversold, historical bulk-entry playbook simulation — here are the 18 candidates, here is the expected path, approve the basket"
- One click approves the basket, pushes all buys to the command centre queue with pre-computed stops

This is the simulation-as-decision pattern: the sim is not a back-test we admire in isolation, it is the **pre-flight** for a real bulk trade.

---

## 18. Simulation as a first-class verb

Simulation is not a tab. It is an action available on every screen that carries a prediction.

Every recommendation card, every sector verdict, every breadth zone crossing, every portfolio change offers a "Simulate this" affordance that opens a modal (or a `/simulation/<id>` page) showing:

1. **Historical base rate** — in past occurrences of this exact signal combination, what happened?
2. **Expected path** — median, P25, P75 forward returns over the relevant horizon
3. **Bulk-execution preview** — if this is applied across the universe, which names qualify and at what sizes?
4. **Stop-loss behaviour** — at what price/level does the sim stop out, and what does that cost?
5. **Accuracy ledger** — of the last N times we took this call, what was the hit rate and avg alpha?

This maps to the V3 Simulation Engine and the `/compass/lab/*` pattern audited in `marketpulse-audit.md §3.6.e`.

---

## 19. Consistency checklist (apply to every new screen)

Before any analytical screen can be marked done, it must pass all of:

- [ ] **Regime banner** at the top (§12)
- [ ] **Signal strip** immediately below (§13)
- [ ] **RS as the headline number**, not absolute return (§9)
- [ ] **Benchmark comparison** on every quantitative visual (§3)
- [ ] **Four-factor conviction chip** on every RS call (§10)
- [ ] **Four decisions explicit** on every recommendation (§11)
- [ ] **Dual-axis overlay** wherever an indicator can be paired with price (§14)
- [ ] **Interpretation sidecar** on every analytical chart, auto-generated (§15)
- [ ] **Signal history table** below every oscillator (§16)
- [ ] **Divergences block** on every multi-factor surface (§10)
- [ ] **Stop level** on every buy recommendation (§17.2)
- [ ] **Simulate-this affordance** on every predictive output (§18)
- [ ] **S / M / L card sizing only** (§4)
- [ ] **Motion under 150ms**, no decorative motion (§7)

A screen that fails any of these is not ATLAS. It is a screen that happens to live in the ATLAS repo.

---

## Reference implementations

All patterns are showcased in `frontend/mockups/styleguide.html`.
Live preview: `python3 -u frontend/mockups/_devserver.py` (port 8765).

**External references studied (for content patterns only, not aesthetic):**
- `docs/design/marketpulse-audit.md` — sitemap, signal-fusion API, lab pattern from Jhaveri Intelligence Platform (live production at marketpulse.jslwealth.in)
- Breadth Terminal screenshots (user-shared, 2026-04-17) — source of the content patterns in §12 (regime banner), §13 (signal strip), §14 (dual-axis overlay), §15 (interpretation sidecar), §16 (signal history). The reference's dark aesthetic is explicitly **not** adopted — all these patterns are rendered in the ATLAS grey-on-white language defined in §1–§8.
