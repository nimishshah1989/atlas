---
title: ATLAS Frontend V1 — Mobile / Responsive Specification
status: draft (slated for §1.8 of frontend-v1-spec.md)
last-updated: 2026-04-18
owner: frontend-v1
---

# §1.8 · Mobile / responsive

ATLAS is a desktop-first wealth-management console. The primary user is
an FM / advisor on a 1440px or larger display. But the FM **will** pull
it up on an iPad during client meetings, and will occasionally hand
their phone to a prospect to show a chart. The product must not collapse
into an unreadable mess on those form factors.

This section locks breakpoints, per-page collapse rules, touch-input
rules, and the explicit list of things we are NOT doing on mobile in V1.

Alignment with global rules: desktop-first CSS (min-width media
queries), progressive enhancement for narrower frames. See
`frontend-viz.md` rule "Mobile responsive but desktop-first (advisors
use large screens)".

---

## 1.8.1 Breakpoints (locked)

All breakpoints measured on the **viewport width** of the rendering
window, not the device. The grid base is 12 columns at XL / L,
collapsing progressively.

| Token | Name | Range | Typical device | Base grid | Default gutter |
|---|---|---|---|---|---|
| `--bp-xl` | XL | ≥ 1440px | 15"+ laptop, external monitor | 12-col, 80px side margin | 24px |
| `--bp-l` | L | 1024–1439px | 13"–14" laptop | 12-col, 40px side margin | 20px |
| `--bp-m` | M | 768–1023px | iPad landscape, small laptop | 8-col, 24px side margin | 16px |
| `--bp-s` | S | 640–767px | iPad portrait, large phone landscape | 4-col, 20px side margin | 16px |
| `--bp-xs` | XS | < 640px | Phone portrait | 4-col, 16px side margin | 12px |

### Token definitions (add to `tokens.css`)

```css
:root {
  --bp-xl: 1440px;
  --bp-l:  1024px;
  --bp-m:  768px;
  --bp-s:  640px;
  /* XS is the implicit default */

  --gutter-xl: 24px;
  --gutter-l:  20px;
  --gutter-m:  16px;
  --gutter-s:  16px;
  --gutter-xs: 12px;

  --side-xl: 80px;
  --side-l:  40px;
  --side-m:  24px;
  --side-s:  20px;
  --side-xs: 16px;
}
```

### Media-query order (desktop-first)

Author styles at XL as the base. Override downward using `max-width`
queries. This matches the existing mockup code and avoids rewriting
settled layouts.

```css
/* Base (XL): 12-col grid, 80px side margin */
.page { padding: 0 var(--side-xl); }

@media (max-width: 1439.98px) { .page { padding: 0 var(--side-l);  } }
@media (max-width: 1023.98px) { .page { padding: 0 var(--side-m);  } }
@media (max-width: 767.98px)  { .page { padding: 0 var(--side-s);  } }
@media (max-width: 639.98px)  { .page { padding: 0 var(--side-xs); } }
```

### Container queries (preferred for shared components)

Shared components (`kpi-strip`, `data-table`, `chart-with-events`,
`sector-tile`, `signal-playback`) live inside parents of varying widths
(full-page on Breadth Terminal, right-rail on Stock detail). Use
**container queries** rather than viewport queries for these, so a
right-rail component collapses the same way a narrow-viewport component
does.

```css
.kpi-strip            { container-type: inline-size; container-name: kpi; }
@container kpi (max-width: 720px) { .kpi-strip .kpi-item + .kpi-item { flex-basis: 50%; } }
@container kpi (max-width: 480px) { .kpi-strip .kpi-item              { flex-basis: 100%; } }
```

Viewport queries handle **page-level** structure (sidebar stack, nav
collapse). Container queries handle **component-level** rearrangement.
No component hard-codes viewport widths.

### Element-by-element rules

| Element | XL / L | M | S | XS |
|---|---|---|---|---|
| Top nav | Fixed top bar, logo + search + avatar | Same | Same, search collapses to `⌘K` icon | Hamburger + logo + search icon; overlay menu |
| Page hero | Full 12-col | Full 8-col | Full 4-col, KPI chips wrap | Title on its own row, chips stack 2×N |
| Regime banner | `.card--lg` | `.card--lg`, days-in-regime drops below text | Same as M | Days-in-regime inline with name; paragraph 3 lines max then "more" |
| Signal strip | 3–4 readings horizontal | Same | Same | Wraps to 2×2 grid |
| Sector board (11 tiles) | 4 per row | 3 per row | 2 per row | 1 per row |
| Right rail | 320px fixed | Same | Collapses to bottom sheet below main content | Drawer from right edge, opens via "Details" button |
| Data tables with >6 cols | Full | Full | Horizontal scroll with sticky first column | Collapsed to 3-col summary; tap row to expand full |
| Charts | Full width of card | Same | Height ×0.75 | Height ×0.5, aspect flips to 1:1 |
| Tabs | Horizontal tab bar | Same | Same | Horizontal scroll if > 4, or accordion (per §1.8.2 component list) |
| Tooltips (`ⓘ`) | Hover card | Hover card | Tap card | Tap card, full-width bottom sheet |
| Form inputs | Inline | Inline | Stack 2 per row | Stack 1 per row |
| Modal / drawer | Centered 720px max | Centered 640px max | Full-width drawer from right, 85% height | Full-screen sheet |

---

## 1.8.2 Per-page responsive behaviour

Each of the 10 pages gets an explicit collapse rule at M / S / XS. If a
block is not listed it follows the default (stack top-to-bottom at S,
hide only at XS if marked *desktop-only*).

### 1. Today / Pulse (`today.html`)

| Block | M (tablet landscape) | S (tablet portrait) | XS (phone) |
|---|---|---|---|
| Hero KPI chips (Nifty, USDINR, G-Sec, VIX) | 4 across | 2×2 | 2×2, smaller type |
| Regime band | Full width, RRG chips wrap to second row | Same | Regime text + chips stack vertically |
| Breadth mini (3 cards) | 3 across | 3 across, reduced height | 1 per row, sparklines retained |
| Sector board | 3×4 grid | 2×6 grid | 1×11 list; tap tile for full RRG readout |
| Movers (2 side-by-side tables) | Stack vertically | Stack | Stack; table collapses to 3-col summary (Symbol, Δ%, RS chip) |
| Fund mover strip | 5 rows, full table | Same, horizontal scroll | 5 rows, 3-col summary (Name, 1M, RS chip) |

*Desktop-only on XS:* none — every Today block must render on phone.

### 2. Explore · Global (`explore-global.html`)

| Block | M | S | XS |
|---|---|---|---|
| 8 sections (Regime, Macros, Yields, FX, Commodities, Credit, Risk, RRG) | Each section full-width, internal 2-col charts become 1-col | Same | Same |
| RRG quadrant chart | Square aspect, 480px | 360px | 320px, pan/pinch enabled |
| Macro data tables | Horizontal scroll, sticky first col | Same | 3-col summary (Ticker, Level, Δ%); tap for full |

*Desktop-only on XS:* per-ticker 5Y sparkline column in macro table (collapsed into expanded row).

### 3. Explore · Country (`explore-country.html`)

| Block | M | S | XS |
|---|---|---|---|
| Regime + India-specific classifier | Full | Full | Full; days-in-regime inline |
| Breadth panel (§5.1) | Oscillator chart full-width, 3 KPI cards below in 3-across | 3 KPI cards stacked | 3 KPI cards stacked, chart at 1:1 aspect with horizontal date-range scroll |
| Derivatives (PCR, VIX, max pain) | 3-across | 3-across | 1 per row |
| Rates · G-Sec yield curve | Chart 640px wide | 480px | 320px, pan enabled |
| INR chart | Full-width | Full-width | 1:1 aspect |
| FII / DII flows | Stacked bar + cumulative line | Same | Stacked bar only, cumulative drops to secondary tab |
| Sectors RRG (12 tiles) | 3×4 | 2×6 | 1×12 list |

*Desktop-only on XS:* Zone-crossing history table (§5.1) — collapsed to "View history" drawer.

### 4. Explore · Sector (`explore-sector.html`)

| Block | M | S | XS |
|---|---|---|---|
| State card (4 chips + hero stats) | Full | Full; hero stats wrap 2×2 | Chips on one row, stats stacked |
| Breadth panel (sector universe) | Same pattern as §5.1 | Same | Same |
| Member stocks (data table, ~11 cols) | Horizontal scroll + sticky symbol col | Same | 3-col summary: Symbol · Δ% · RS chip; tap row expands full row as card |
| Fundamentals (sector P/E, EPS growth, margin) | 3-across stat cards | 3-across | 1 per row |
| Macro sensitivities | Heatmap retained | Heatmap with horizontal scroll | Collapsed to ranked list (top 5 sensitivities) |

### 5. Stock detail (`stock-detail.html`)

| Block | M | S | XS |
|---|---|---|---|
| Hero (symbol + price + 4 chips) | Single row | Price on its own row, chips row below | Two rows: (symbol + price), (4 chips wrapping) |
| Detail tabs | Horizontal, scroll if > 4 | Same | Accordion (vertical) — see §1.8.3 tabs decision |
| Chart (col 1) | Full col 1 (~600px) | Full-width, 16:9 | 1:1, horizontal date-range scroll |
| News (col 1 below chart) | 5 items visible | 5 items | 3 items with "more" link |
| Risk + Technical + Fundamental (col 2) | 3-card column | Stacked cards | Stacked cards, each collapsible |
| RS panel (col 3) | 4-bench RS strip, 80×40 sparkline each | Full-width, strip becomes 2×2 grid | 4 rows, one bench each |
| Corporate Actions (col 3) | Table visible | Compressed | Collapsed to drawer; "View actions" button |
| Peer comparison table (~12 cols) | Horizontal scroll | Same | 3-col summary: Symbol · P/E · RS; tap to expand |

*Desktop-only on XS:* rolling beta chart, RS vs all 4 benchmarks side-by-side (phones show one at a time with swipe).

### 6. MF detail (`mf-detail.html`)

| Block | M | S | XS |
|---|---|---|---|
| Hero (fund + AUM + 4 chips + 3Y Sharpe/alpha) | Single row, stats wrap 2×2 | Name + AUM on row 1, stats in 2×2 grid | Name on row 1, AUM on row 2, stats 2×2 |
| Section A: returns table + rolling chart | Table full-width, chart below | Same | Table horizontal scroll, chart 1:1 |
| Section B: alpha quality (Jensen, Treynor, IR, capture) | 2×2 grid of stat cards | 2×2 | 1 per row |
| Section C: risk (vol, DD, downside dev, VaR) | 2×2 | 2×2 | 1 per row |
| Section D: holdings (top 20) | Table full-width | Table horizontal scroll | 3-col: Name · Weight · Sector; tap to expand |
| Section E: sector allocation vs benchmark | Active-weight bar chart full-width | Same | Same, shorter bars |
| Section F: rolling alpha/beta | 2 charts side by side | Stack | Stack, 1:1 each |
| Section G: suitability | SIP outcomes table + peer comparison table | Stack | Peer table collapses to 3-col summary |

### 7. MF rank (`mf-rank.html`)

| Block | M | S | XS |
|---|---|---|---|
| Hero + filter rail (left, 280px) | Rail collapses to top filter bar | Top filter bar, "Show filters" button expands drawer | Same as S |
| Scoring panel (EXPLAIN) | Full width | Full width, accordion collapsed by default | Same |
| Rank table (~14 cols) | Horizontal scroll + sticky Rank + Fund name | Same | **3-col summary**: Rank · Fund name + AMC · Composite score. Tap row expands to full card showing all 4 scores + chips + AUM |
| Formula disclosure block | Bottom of page, full width | Accordion collapsed by default | Same |

*Desktop-only on XS:* per-score sparkline column. Phones show score number only.

### 8. Breadth Terminal (`breadth.html`)

| Block | M | S | XS |
|---|---|---|---|
| Hero + universe/MA selector pills | Inline | Stacked rows | Stacked |
| Regime band | Full width | Same | Same |
| 3 KPI cards (21-EMA, 50-DMA, 200-DMA) | 3-across | 3-across smaller | 1 per row |
| Breadth oscillator chart | Full-width 16:9 | 4:3 | 1:1 with horizontal date-range scroll |
| Zone reference panel (right rail) | Right rail retained | Drops below chart as card | Drawer opens from right via "Zone details" button |
| DESCRIBE block (right rail) | Right rail | Below chart | Collapsible card above Signal history |
| Signal history table (~5 cols) | Full table | Horizontal scroll | 3-col: Date · Event · Value; tap for full row |
| EXPLAIN block | Full width | Accordion collapsed | Same |
| Signal Playback embed (§10.5) | Full version | Compact — see §1.8.3 | Compact — see §1.8.3 |

### 9. Portfolios (`portfolios.html`)

| Block | M | S | XS |
|---|---|---|---|
| Hero (Books title, aggregate AUM, last reconciled) | Inline | Stacked | Stacked |
| Book grid (4 book cards) | 2×2 | 2×2 | 1 per row |
| Per-book expanded holdings | Table full-width | Horizontal scroll | 3-col: Symbol · Weight · Δ% |
| Weight chart | Donut + list side by side | Stacked | Stacked |
| Performance vs benchmark chart | Pattern A dual-line | Same | 1:1 aspect |

### 10. Lab / Simulations (`lab.html`)

| Block | M | S | XS |
|---|---|---|---|
| Mode tabs (Breadth Playback · Rule Backtest · Compare) | Horizontal | Horizontal, scrollable | **Vertical tab list** — see §1.8.3 |
| Strategy config panel (left, 320px) | Drops below Mode tabs as collapsible card | Same | Same |
| Equity curve + drawdown (shared X) | Stacked (equity on top, DD below) | Stacked | Stacked; each 1:1 aspect |
| Performance KPIs (~12 metrics) | 4×3 grid | 3×4 grid | 2×N grid |
| Rolling metrics (3 charts) | 3 across | Stack | Stack |
| Trade log table | Full table | Horizontal scroll | 3-col: Date · Symbol · Return contrib |
| Monte Carlo overlay | Toggle on top chart | Same | Same, tap to toggle |
| Compare strategies | 3-run overlay | Same | Same, legend wraps |

### Global search (top-nav component, §13)

| Mode | XL / L | M | S | XS |
|---|---|---|---|---|
| Invocation | `⌘K` or click top-bar input | Same | Input collapses to icon button | Icon in hamburger menu |
| Overlay | 640px centered modal | 640px centered | 90vw centered modal | **Full-screen overlay** with back button |
| Result groups | 6 groups visible | 6 groups | 3 groups, "More" tab | Scrollable, one group at a time with section dividers |

---

## 1.8.3 Signal Playback simulator on mobile (§10.5 ⇒ XS)

The Signal Playback block is the most input-heavy component in the
spec: 10 numeric inputs + Run button + KPI tile row + equity curve + 3
tabs (Transaction Log, Cashflow, Tax Analysis). Non-trivial on phone.

### Input panel: three-accordion grouping

At M / S / XS the 10 inputs are grouped into **three collapsible
accordion sections**, opened one at a time. Defaults pre-filled. Run
button always visible at the top of the panel.

| Accordion section | Inputs (from §10.5.1) |
|---|---|
| **1. Deposits** (default open) | Initial Investment, Monthly SIP, Lumpsum (Count<L_os) |
| **2. Sell rules** (closed) | Sell % at Count≥L_ob, Further Sell Below Level, Further Sell % |
| **3. Redeploy rules** (closed) | 1st Redeploy Below Level, 1st Redeploy %, 2nd Redeploy Below Level, 2nd Redeploy % |

Each accordion header shows a one-line current-value summary so the FM
can see what's set without opening it:

```
1. Deposits                                         ₹1L + ₹10K/mo + ₹50K opp ▾
2. Sell rules                                       30% @ 400 · 20% @ <250  ▾
3. Redeploy rules                                   50% @ <125 · 100% @ <50 ▾
```

Inputs inside each section stack one-per-row on XS, two-per-row on S/M.
Every input has `inputmode="numeric"` so the numeric keyboard opens.

### Chart aspect ratios

| Breakpoint | Equity curve aspect |
|---|---|
| XL / L | 16:9 (fills `.card--lg`) |
| M | 16:9 |
| S | 4:3 |
| XS | 1:1 with horizontal date-range scroll (pan) |

The 1:1 aspect on XS is justified: pinch-zoom should show detail on a
single visible date range while the user pans horizontally to navigate
the 5Y window. Vertical zoom is disabled (Y-axis is derived — locked).

### Tabs: swipeable segmented control (not vertical tabs)

**Decision: use a swipeable horizontal segmented control on XS**, not
a vertical tab list.

Rationale:
- The three tabs (Transaction Log, Cashflow, Tax Analysis) are peer
  views, not hierarchical — segmented control is the native iOS/Android
  pattern.
- Vertical tab lists on phone double the scroll distance and hide the
  content until the user picks one — the FM is mid-conversation and
  wants content-first.
- Swipe-to-switch matches FM mental model (tabs as slides).
- Segmented control occupies a single row (~48px tall) vs a vertical
  list that takes ~200px before content starts.

Implementation: CSS-only scroll-snap with snap points at each tab
panel; segmented control updates via `IntersectionObserver` on the
panels. No JS framework required. Keyboard arrow-left/right cycles for
accessibility.

### KPI tile row

| Breakpoint | Layout |
|---|---|
| XL | 4×3 grid (12 tiles) |
| L | 4×3 |
| M | 3×4 |
| S | 2×6 |
| XS | 2×6 with horizontal scroll if needed; FIRST 4 always visible (Total Invested, Final FV, XIRR, vs Nifty 500) |

### Tap-target sizing

All interactive elements MUST meet both Apple HIG and Material
thresholds:

- **Minimum 44×44 pt** (Apple HIG)
- **Minimum 48×48 dp** (Material 3)
- ATLAS standard: **48×48 CSS px on every tap target at XS**, minimum
  40×40 at S/M (scales with system font)

Applied to: Run button, accordion chevrons, tab segmented control, chart
range buttons (1M/3M/6M/1Y/5Y/ALL), Reset/Load-fixture buttons, table
row expanders, drawer open/close handles.

Verified in tokens:

```css
.btn,
.tap-target,
.accordion-chevron,
.tab-control > button,
.range-button {
  min-width: 48px;
  min-height: 48px;
  padding: 12px 16px;
}
```

---

## 1.8.4 Chart touch interactions (shared-component)

Applies to every `chart-with-events` instance (Breadth Terminal, Stock
detail, MF detail, Signal Playback, Lab). Hover tooltips do not work
on touch — this section defines the touch equivalents.

| Interaction | Desktop (mouse) | Touch (M / S / XS) |
|---|---|---|
| Reveal tooltip at data point | Hover over point | **Single tap** on or near line → vertical crosshair line + tooltip sticky until dismissed |
| Dismiss tooltip | Move mouse away | Tap outside chart area, or tap chart with no near-point, or tap explicit ✕ in tooltip header |
| Zoom in | Scroll-wheel | **Pinch** to zoom X-axis (Y stays locked) |
| Zoom out | Scroll-wheel up | Pinch out, or tap "Reset zoom" button |
| Pan | Click+drag | **Single-finger drag** horizontally |
| Range brush (select date window) | Drag on range-brush strip below chart | Same brush strip; drag handles on each end are 48px wide |
| Context menu / export | Right-click | **Long-press** (500ms) → action sheet: Copy values · Export CSV · Share PNG |
| Event marker hover | Hover vertical event rule | Tap event rule → event details card slides up from bottom |

Rules:
- Tap-to-reveal tooltip MUST NOT also trigger a drag (debounce: if
  pointer moves > 8px during initial touch, treat as pan, not tap).
- Pinch zoom preserves aspect; X-axis range updates, Y-axis auto-fits.
- Long-press visual feedback: subtle 150ms scale-up on the target.
- All interactions respect `prefers-reduced-motion` — no momentum
  scroll, no bounce.

Accessibility: keyboard alternative on every chart (arrow keys to step
through data points, Enter to lock tooltip, Escape to dismiss).
`aria-describedby` on the chart container points to the auto-generated
interpretation sidecar (§15 of design-principles.md).

---

## 1.8.5 Top-nav on mobile

**Decision: persistent top bar at M, hamburger + collapsing top bar at
S / XS. No bottom-tab bar.**

Rationale for rejecting bottom-tab bar: ATLAS has 10 pages and an MF
rank / Lab / Breadth Terminal that are not peers — they're
destinations. A 3–5-slot bottom tab bar would force arbitrary
grouping. Hamburger menu scales to 10 items and matches the
wealth-management competitor set (MorningStar, FE fundinfo, Factset).

### Layout per breakpoint

| Breakpoint | Top bar contents |
|---|---|
| XL / L | `[atlas.]` logo · Primary nav (Today, Explore, Portfolios, MF rank, Breadth, Lab) · Search input · User avatar |
| M | `[atlas.]` logo · Primary nav (compressed, icon-only with tooltip) · Search input · Avatar |
| S | `[☰]` hamburger · `[atlas.]` logo · `[🔍]` search icon · `[avatar]` |
| XS | Same as S |

### Hamburger menu (S / XS)

Full-height drawer from the left, 280px wide, overlay dim backdrop.
Contents:
- Primary nav (10 pages), each as a full 48px-tall row
- Divider
- `⌘K` search shortcut hint
- User section (avatar, "Sign out")
- Version + data-as-of footer

### Search on mobile

Tapping the `[🔍]` icon opens a **full-screen overlay** (not a modal
— full height) with:
- Input field auto-focused
- Keyboard opens automatically
- Cancel button top-right (48×48)
- Results appear inline, grouped by entity type (§13)
- Keyboard-next cycles through results; Enter opens

Full-screen (vs modal) because the keyboard on phone consumes ~40% of
screen height, leaving a modal nearly unusable. Full-screen commits
to the search task.

### Keyboard-focus management

- Tab order: hamburger → logo → search → avatar → (inside overlay:
  input → result list → cancel)
- Closing the search overlay returns focus to the search icon
- Closing hamburger menu returns focus to hamburger button
- Escape key dismisses any overlay
- Focus ring: 2px `--accent-700` outline, 2px offset, visible on every
  tap target (not just keyboard focus)

---

## 1.8.6 Typography scaling

Fraunces (serif, titles) and Inter (sans, body + numbers) scale down at
narrower breakpoints. Table data stays at 13px minimum on all
breakpoints — never smaller, or the tabular-nums feature breaks
readability.

### Scale steps (exact)

| Token | XL / L | M | S | XS | Use |
|---|---|---|---|---|---|
| `--t-display` | 48px | 40px | 32px | 28px | Page-level hero titles (rare — Today page only) |
| `--t-h1` | 38px | 32px | 28px | 24px | Card headlines with serif (Fraunces / Source Serif 4) |
| `--t-h2` | 28px | 24px | 22px | 20px | Section titles |
| `--t-h3` | 22px | 20px | 18px | 17px | Sub-section, card subtitle |
| `--t-body` | 15px | 15px | 14px | 14px | Paragraphs, EXPLAIN blocks, DESCRIBE blocks |
| `--t-caption` | 13px | 13px | 13px | 13px | Labels under KPIs, footnotes, table column headers |
| `--t-table` | 13px | 13px | 13px | 13px | Table body numeric data — **floor, do not shrink** |
| `--t-small` | 12px | 12px | 12px | 12px | `ⓘ` tooltip body, tiny legends |

### Implementation

```css
:root {
  --t-display: 48px; --t-h1: 38px; --t-h2: 28px; --t-h3: 22px;
  --t-body: 15px;    --t-caption: 13px; --t-table: 13px; --t-small: 12px;
}

@media (max-width: 1023.98px) {
  :root { --t-display: 40px; --t-h1: 32px; --t-h2: 24px; --t-h3: 20px; }
}
@media (max-width: 767.98px) {
  :root { --t-display: 32px; --t-h1: 28px; --t-h2: 22px; --t-h3: 18px; --t-body: 14px; }
}
@media (max-width: 639.98px) {
  :root { --t-display: 28px; --t-h1: 24px; --t-h2: 20px; --t-h3: 17px; }
}
```

Line heights: fixed per token, not scaled. `--t-h1` always 1.2, `--t-body`
always 1.5, `--t-table` always 1.3.

---

## 1.8.7 Simulator FIFO tax tables on phone

The Tax Analysis tab (§10.5 output block 4) has 7–9 columns per FY row:
`FY · STCG realised · LTCG realised · LTCG exemption used · Taxable
LTCG · Tax paid · Cess · Total · Regime`. Does not fit on phone.

### Column priority (XS)

Visible columns on XS, in priority order:

1. **FY** (row header, sticky)
2. **Total tax** (the headline number)

That's it. Tap row to expand full-row card showing all 9 columns.

### At S breakpoint: 4 priority columns

1. FY
2. STCG realised
3. LTCG realised
4. Total tax

Tap row to expand remaining columns as inline detail rows.

### At M breakpoint: 6 priority columns

1. FY
2. STCG realised
3. LTCG realised
4. LTCG exemption used
5. Tax paid
6. Total tax

Regime, Cess, Taxable LTCG hidden — expand row for detail.

### At L / XL: all 9 columns

Full table, no expansion needed.

### Unrealised-if-sold-today panel (companion to Tax Analysis)

On XS: shown as a single-line summary card above the FY table:
`"If sold today: STCG ₹X · LTCG ₹Y · Tax ₹Z · Cess ₹C"`. Tap for
per-lot breakdown in a drawer.

---

## 1.8.8 Accessibility on touch

Touch accessibility is not optional. Every tap target, every chart, every
overlay must meet these rules.

### Focus visibility

- Every tap target has a visible focus indicator:
  `outline: 2px solid var(--accent-700); outline-offset: 2px;`
- Focus indicator appears on **both** keyboard focus AND on touch
  start (to confirm the hit)
- Focus never removed by `outline: none` without a replacement

### Skip links

Every page ships a skip link as the first focusable element:

```html
<a href="#main-content" class="skip-link">Skip to main content</a>
```

Visible only when focused. Jumps past the top nav.

### Reduced motion

Honor `prefers-reduced-motion: reduce` on every animation:

- Breadth oscillator: no pulsing dots, no auto-scroll to current date
- Signal Playback: no auto-playing equity curve reveal; chart
  renders fully on mount
- Tab / accordion transitions: instant (0ms) instead of 150ms
- Hover/tap ripples: disabled

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0ms !important;
    transition-duration: 0ms !important;
  }
}
```

### Screen reader support

- Every chart has a `role="img"` wrapper with `aria-label` summarising
  the current state (e.g. "Breadth oscillator: 178, below midline of
  250, trending down over 5 days")
- Every interactive element has either visible text or `aria-label`
- Live regions for dynamic content (simulator results, search
  results) — see §1.9.6

### Colour contrast (WCAG AA minimum)

- Body text: 4.5:1 minimum against background
- Large text (≥18px bold, ≥24px regular): 3:1 minimum
- UI components / graphics: 3:1 minimum
- RAG chip text against chip background: verified ≥4.5:1 for all three
  colors against `--bg-surface` (see `tokens.css`)

---

## 1.8.9 Out of scope for V1

We are honest about what is NOT on the mobile roadmap in V1. Each item
below is deferred to V2+ with a tracking note.

| Capability | Status | Deferred to | Note |
|---|---|---|---|
| Offline caching (service worker) | Out of V1 | V2 | Requires full API stability + cache-invalidation strategy. Not designed for mockup stage. |
| Install-as-PWA (Add to Home Screen) | Out of V1 | V2 | Requires manifest.json, icon set, offline shell. Defer until V2 auth + shell routing. |
| Push notifications (alerts fire on phone) | Out of V1 | V2.1 | Requires push service + user consent flows + alert routing. Gated on V1.1 rule engine emitting alerts. |
| Biometric auth (Face ID, Touch ID) | Out of V1 | V2 | Requires auth redesign (V1 uses session cookie). |
| Native share sheet (share report PDF) | Out of V1 | V2 | Reports page out of V1 scope entirely (§17). |
| Native camera (upload portfolio screenshot) | Out of V1 | V2+ | Niche. Not in demand for Stage 1. |
| Gesture swipe between pages | Out of V1 | V2 | Conflicts with chart horizontal pan. Decide post-V1 usability testing. |
| Haptic feedback on tap | Out of V1 | V2 | Low value until push notifications land. |
| Landscape-specific layouts | Out of V1 | V1.1 | V1 honors viewport width only — if an iPhone rotates to landscape, it gets S-breakpoint layout. Dedicated landscape tuning deferred. |
| Responsive images / WebP hero art | Out of V1 | V2 | V1 mockups are text+chart only; no photographic hero art. |
| Device-specific CSS (iPhone notch, Android safe areas) | Basic only in V1 | V2 | V1 ships `env(safe-area-inset-*)` padding on top bar and bottom drawer. Deeper tuning (foldables, Dynamic Island) deferred. |

### V1 mobile acceptance criteria (add to §18)

- [ ] Every page renders without horizontal overflow at 375px viewport (iPhone SE)
- [ ] Every chart renders legibly at 320px container width
- [ ] Every tap target ≥ 44×44 CSS px
- [ ] Every form input opens the correct keyboard (`inputmode="numeric"` on numeric)
- [ ] Signal Playback simulator runs end-to-end on iPad (M) and iPhone (XS)
- [ ] Global search works via full-screen overlay on XS
- [ ] Hamburger menu opens/closes without flash; keyboard focus traps correctly
- [ ] No `hover:` state is the only way to access information
- [ ] Manual smoke test on: iPhone 15 (Safari), iPad Air (Safari), Pixel 8 (Chrome)

---

**End of §1.8.** Mobile behaviour is load-bearing for FM client-meeting
use, non-negotiable for V1 ship. Questions on a specific page's
collapse rule: check §1.8.2 table, not a new design session.
