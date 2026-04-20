# S2 — Drill-Spine v3 (PM-Decision Flow)

**Status:** READY FOR FORGE PRIME
**Owner:** n
**Drafted:** 2026-04-20  •  **Target:** complete in 9 chunks, one fresh session per chunk
**Starting HEAD:** `main` @ 7d1d330 + untracked S2-scaffold (revisited in §6)
**Budget:** ~$83 burn (~$68 chunks + $15 retry buffer), under $100 cap
**Source slice:** ATLAS-DEFINITIVE-SPEC.md §§ drill hierarchy, RS/Momentum/Breadth/Volume framework, RRG, §17 UQL, §18 include, §20 API principles
**Supersedes:** v1 (5-page-shell freelance, 2026-04-20) and v2 (drill-spine + 5-signal lock-in, 2026-04-20). Both retired.

---

## 1. One-line

Atlas is **MarketPulse++** organised around the **portfolio manager's three decisions** — *what to buy*, *how much to weight*, *when to act*. Four views replace MarketPulse's nine pages. The 4-lens RRG is the working surface for selection. Every sector → 3 instrument tables → instrument deep-dive flow shares one column schema. Five signal types fire transparently at every level.

---

## 2. Why this slice supersedes v2

v2 locked the drill spine + 5-signal types but framed atlas as a *richer index browser*. Conversation 2026-04-20 reframed it: a PM running an RS book opens the screen with three questions, not nine. v3 collapses scope around those three questions and makes every view answer at least one of them explicitly. v1's freelance shells (`/global`, `/india`, `/sector/*`, `/etf/*`) are abandoned; v3 replaces them with **4 routes + 3 upgraded routes + 1 drawer**.

---

## 3. The locked framework

### 3.1 Three PM decisions (non-negotiable)

| Decision | Driven by | Where it lives |
|---|---|---|
| **Selection** — what instrument | RS + Momentum + Absolute Returns | View 2 (Leaders Board) + View 3 (Sector Page) |
| **Weighting** — how much | Fundamentals (over/underpriced) | Conviction Sizer drawer + instrument page Weighting tab |
| **Timing** — when to act | Market breadth (ST 10d / MT 50d / LT 200d) | View 1 (Regime Cockpit) + instrument page Timing tab |

A view that does not serve at least one of these is out of scope. A signal that does not feed at least one of these is out of scope.

### 3.2 Four lenses (cross-cutting, every scope)

| Lens | Source | Used as |
|---|---|---|
| **RS** | atlas RS cache + multi-benchmark (N500 / Gold / MSCIW / SPX) | Selection + RRG x-axis |
| **Momentum** | computed from price + RS series | Selection + RRG y-axis |
| **Breadth** | sector breadth ST/MT/LT, advance/decline, % above DMA | Timing + RRG bubble color |
| **Volume** | rel volume, OBV, volume signal classifier | Conviction confirm + RRG bubble size |

### 3.3 Five signal types (rule-engine v1.1, ref `project_rule_engine_v1_1.md`)

Locked, with thresholds printed on every page footer (transparency rule).

| Signal | Definition | Actionable | Default per-lens thresholds |
|---|---|---|---|
| **ENTRY** | New positive crossing | Yes (initiate) | RS: cross above 70 sustained 3 days. Mom: cross above 0 with 5d slope > 0. Breadth: ST > 60 AND MT > 50. Volume: rel-vol > 1.5 on ENTRY day |
| **EXIT** | New negative crossing | Yes (close/reduce) | RS: cross below 40 sustained 3 days. Mom: cross below 0 with 5d slope < 0. Breadth: ST < 40 OR LT < 40. Volume: rel-vol > 1.5 on EXIT day |
| **REGIME** | Tier change (BULL/CAUT/CORR/BEAR) | Yes (rebalance posture) | Composite breadth + drawdown rule (MP-compass parity) |
| **WARN** | Approaching threshold | No (watch) | Within 5 points of any ENTRY/EXIT band |
| **CONFIRM** | Multi-lens agreement | Yes (size up) | ≥3 of 4 lenses ENTRY in same direction within 5 trading days |

Thresholds live in `backend/config/signal_thresholds.yaml`, hot-reloadable. Drawer in every view exposes them read-only.

### 3.4 The 4-lens RRG (locked mapping)

The RRG is no longer "x=RS, y=Mom, z=size=AbsReturn" (v2). All four lenses map to four visual dimensions:

| Visual dim | Lens | Read |
|---|---|---|
| x-axis | RS (vs selected benchmark) | Leader (right) vs laggard (left) |
| y-axis | Momentum | Accelerating (top) vs fading (bottom) |
| bubble size | Volume signal | Big = high participation |
| bubble color | Breadth | Green = broad, Amber = mixed, Red = narrow/divergent |

PM mental model: *big green top-right = highest-conviction leader. Big red top-right = leader on thin breadth → suspect. Small green bottom-left = early-stage candidate.*

Abs Return is a **table column** beside the RRG, not a visual dim. It sorts and confirms.

---

## 4. Page architecture (4 routes + 3 upgraded + 1 drawer)

### 4.1 Route map

| Route | View | Replaces in MP | New for atlas |
|---|---|---|---|
| `/` | View 1 — Regime Cockpit | Pulse + Sentiment | Global country layer, gold-RS, ST/MT/LT split |
| `/leaders` | View 2 — Leaders Board | Compass | 4-lens RRG, MFs as 3rd universe, multi-benchmark |
| `/sector/[key]` | View 3 — Sector Page | Compass drill | Stock-derived, universe filter, 3 tables |
| `/book` | View 4 — Book + Action Queue | Recommendations + Microbaskets + Portfolios + Actionables + Actioned + Approved + Trade + Performance (8 pages → 1) | Insider + corp-action overlay, 4-lens scoring on holdings |
| `/stocks/[symbol]` | Instrument detail (stock) | Existing, upgraded | 6-tab Selection/Weighting/Timing structure |
| `/etf/[ticker]` | Instrument detail (ETF) | Existing, upgraded | Same |
| `/funds/[id]` | Instrument detail (MF) | Existing, upgraded | Same |
| **Drawer** | Conviction Sizer | MP Microbaskets construction | Slides over Leaders / Book on "Size it" click |

### 4.2 View 1 — Regime Cockpit (`/`)

Three stacked bands, no tabs:

1. **Global band** — 4 region cards (US / EU / EM / India) with regime badge + composite score. Source: country breadth + gold-RS.
2. **India band** — composite gauge 0-100 + 5 layer mini-gauges (short-term / broad-trend / a/d / momentum / extremes, MP parity) + **explicit ST(10d) / MT(50d) / LT(200d)** breadth bars.
3. **Sector heatmap band** — rows = sectors, columns = ST/MT/LT, cell color = breadth state. Click cell → `/sector/[key]`.

**Single output at top:** "Deployment posture today: **SELECTIVE** — Global Risk-On, India CAUTIOUS, breadth divergent ST↔LT" with confidence %.

Drawer: "How regime is computed".

### 4.3 View 2 — Leaders Board (`/leaders`)

Single screen, 3 toggles at top:
- **Universe**: Sectors (default) / Stocks / ETFs / MFs
- **Benchmark**: N500 / Gold / MSCIW / SPX
- **Period**: 1M / 3M / 6M / 12M
- **Filter pill**: "Aligned leaders only" (RS+Mom+Abs all positive, default ON)

Below:
- 4-lens RRG (per §3.4)
- **Leaders table** with consistent columns (per §5):
  - Click row → instrument page
  - Click "Size it" → Conviction Sizer drawer prefilled
  - Click sector bubble in RRG → `/sector/[key]`

Default universe shown is **gated by regime** (View 1 → View 2 wiring): BULL → Stocks default; CAUTIOUS → Sectors default; CORRECTION/BEAR → ETFs default. PM can override.

### 4.4 View 3 — Sector Page (`/sector/[key]`)

**Header:** sector's own 4-lens summary card + signal flags + composite action + breadth ST/MT/LT.

**Universe filter:** [NIFTY | NIFTY100 | NIFTY500] — sector pages are **derived from stock-level data + sector mapping**, not sector indices. Filter actually narrows the constituent set.

**Three tabs (consistent column schema, §5):**
- **Stocks** (default) — sorted by composite signal
- **Mutual Funds** — MFs mapped to sector (uses corrected sector→category map, fixes v2 §6 bug)
- **ETFs** — sector-themed ETFs (empty state if none)

Each row click → instrument detail page.

### 4.5 View 4 — Book + Action Queue (`/book`)

Tab at top: **Holdings | Watchlist** (same component, different data).

Three stacked sections inside Holdings:
1. **Action queue** (top) — EXIT (red), WARN (amber), CONFIRM (green) signals on holdings, sorted by signal strength × position size. Insider sells + corporate actions overlaid as event flags.
2. **Holdings table** — every position scored on 4 lenses, signal flags, current vs entry conviction, P&L.
3. **Performance attribution** — by sector / signal type / hold period, using atlas's 5y history.

### 4.6 Instrument detail page (3 routes, shared structure)

**Hero block (sticky):**
- Symbol / name / sector / current price + change
- 4-lens card with benchmark switcher (live values + per-lens signal flags)
- Composite action: BUY / HOLD / WATCH / AVOID / SELL with one-line reason
- Conviction score 0-100 + suggested weight band

**Six sub-tabs below the hero (mirror the 3-decision flow + depth):**

| Tab | Stock fields | ETF fields | MF fields |
|---|---|---|---|
| **Overview** | Price chart + 50/200 DMA, 4-lens radar, signal timeline | NAV chart + tracking error, 4-lens radar | NAV chart vs benchmark, 4-lens radar |
| **Selection** | RS vs all benchmarks, momentum decomposition, abs returns 1M-5Y, sector rank, universe rank | + index tracked | + category rank |
| **Weighting** | P/E zone, earnings momentum, FCF, leverage, RoCE → conviction → weight band | Expense ratio, AUM, holdings concentration, premium/discount → weight band | NAV, AUM, expense, fund-mgr tenure, top holdings → weight band |
| **Timing** | Breadth contribution to sector, volume profile, institutional flow proxy, historical signal accuracy | Volume + flow, premium/discount history | Inflow/outflow trend, category breadth |
| **Events** | Insider trades, corporate actions, earnings calendar | Holdings rebalance events | Manager change, scheme merge, exit-load |
| **Backtest** | "If today's signals fired N weeks ago, what's the P&L now?" + per-ticker historical signal accuracy | Same | Same |

### 4.7 Conviction Sizer (drawer, not a route)

Triggered from a row's "Size it" button on Leaders Board or Book. Slides in from right (~400px). Per instrument:
- Fundamentals stack (per asset class)
- Conviction score 0-100 = w₁·selection + w₂·value + w₃·regime_fit (weights tunable in `signal_thresholds.yaml`)
- Suggested weight: 1% / 3% / 5% buckets, with rule shown ("RICH zone caps at 1% even if RS top decile")
- Portfolio impact preview: "Adding this at 3% raises sector exposure to X%, factor tilt to Y"

Drawer never blocks navigation. Closing it does not lose context.

---

## 5. Consistent column schema (every instrument table)

All tables under `/leaders`, `/sector/*`, `/book` share these columns. Order locked. Sortable on every column.

| # | Column | Type | Source |
|---|---|---|---|
| 1 | Symbol / Name | text | row PK |
| 2 | RS vs N500 | num + signal pill | lens engine |
| 3 | RS vs Gold | num + signal pill | lens engine |
| 4 | Momentum | num + signal pill | lens engine |
| 5 | Breadth contrib | num + color | breadth engine |
| 6 | Volume signal | text + signal pill | volume engine |
| 7 | Abs Return (selected period) | num | atlas RS cache |
| 8 | Composite action | BUY/HOLD/WATCH/AVOID/SELL | rule engine |
| 9 | Conviction | 0-100 | sizer service |
| 10 | Weight band | 1%/3%/5% | sizer service |
| 11 | Signal flags | icons (E/X/R/W/C) | rule engine |

Component: `<InstrumentTable rows={...} mode="stock|etf|mf" />`. One implementation, three modes.

---

## 6. Backend contract (one shared service, thin route wrappers)

Per CLAUDE.md hard stop: every route MUST go through the shared UQL service. No SQL in route handlers.

### 6.1 New endpoints

```
GET  /api/v1/lens/{scope}/{id}?benchmark=&period=
     → { scope, id, lenses: { rs, momentum, breadth, volume }, signals: [...], composite_action, conviction, weight_band, reason, data_as_of }
     scope ∈ {country, sector, stock, etf, mf}

GET  /api/v1/regime
     → { posture: SELECTIVE|RISK_ON|RISK_OFF, confidence, global: {...}, india: {...}, sectors: [...], data_as_of }

GET  /api/v1/leaders?universe=&benchmark=&period=&aligned_only=
     → { rows: [...consistent column schema...], _meta }

GET  /api/v1/sector/{key}?universe=NIFTY|NIFTY100|NIFTY500
     → { sector_summary: {...4-lens...}, stocks: [...], mfs: [...], etfs: [...], _meta }

POST /api/v1/conviction/score
     body { instrument_id, scope }
     → { score, weight_band, components: {selection, value, regime_fit}, suggested_weight_pct }

GET  /api/v1/book
     → { holdings: [...], watchlist: [...], action_queue: [...], performance: {...} }
```

### 6.2 Read-only over existing tables

No new tables. No new Alembic migrations. Sector aggregation is computed from stock-level data + existing sector mapping (per the user's instruction in §4.4). Conviction score reuses existing fundamentals tables. Insider/corp-action overlay reads existing JIP-sourced tables.

If S2-0 discovers a missing source field, the chunk **STOPS** and logs to `BUILD_STATUS.md` per CLAUDE.md hard stop conditions. Does not invent a table.

### 6.3 API standard compliance

Every new route MUST pass `python scripts/check-api-standard.py` (spec §17 UQL + §18 include + §20 principles). Fixed endpoints above are thin wrappers over a shared `LensService`, `RegimeService`, `SectorService`, `ConvictionService`, `BookService`. Each service is itself a UQL composer.

---

## 7. Chunk ledger (9 chunks, model assigned per chunk)

| ID | Chunk | Model | Est. $ | Depends on |
|---|---|---|---|---|
| **S2-0** | Backend: `LensService` + 5-signal engine + threshold YAML + sector aggregation + 5 endpoints (§6) + `check-api-standard.py` green | **Opus** | $8 | — |
| **S2-1** | Shared primitives: `<FourLensRRG>`, `<InstrumentTable>`, `<RegimeGauge>`, `<SignalPill>`, `<ConvictionDrawer>` (skeleton) | Sonnet | $4 | S2-0 |
| **S2-2** | View 1 — Regime Cockpit (`/`): 3 bands, posture banner, sector heatmap with drill links | Sonnet | $5 | S2-1 |
| **S2-3** | View 2 — Leaders Board (`/leaders`): 4-lens RRG + universe/benchmark/period toggles + leaders table + sector-bubble drill + Size-it button | Sonnet | $5 | S2-1 |
| **S2-4** | View 3 — Sector Page (`/sector/[key]`): header + universe filter + 3 tabs (Stocks/MFs/ETFs) sharing column schema | Sonnet | $4 | S2-1 |
| **S2-5** | Instrument detail consistency pass: 3 routes × 6 sub-tabs (Overview/Selection/Weighting/Timing/Events/Backtest) sharing hero + 4-lens card + signal block | Sonnet | $8 | S2-1 |
| **S2-6** | Conviction Sizer drawer: full implementation behind the skeleton from S2-1 + `POST /conviction/score` wiring + portfolio impact preview | Sonnet | $5 | S2-1, S2-3 |
| **S2-7** | View 4 — Book (`/book`): action queue + holdings table + performance attribution + insider/corp-action overlay + Holdings/Watchlist tabs | Sonnet | $6 | S2-1, S2-6 |
| **S2-8** | Cross-view wiring: regime gates Leaders default universe; sector links from Cockpit + Book unify to `/sector/[key]`; nav cleanup; retire v1 freelance shells `/global` `/india` `/sector/*` `/etf/[ticker]` (delete or redirect) | Sonnet | $3 | all |
| | **Total** | | **$48 chunks + $5 this session + $15 retry buffer = $68 + $15 = $83** | |

Buffer covers ~2-3 quality-gate retries (atlas's 7-dim gate fails ~20% of chunks first pass).

---

## 8. Resolved-in-spec questions (avoiding `/speckit-clarify` cost)

| # | Q | Resolution |
|---|---|---|
| 1 | Sector data source — sector index or stock-aggregation? | **Stock-aggregation** (§4.4). User instruction. Universe filter must work, sector indices have fixed constituents. |
| 2 | Instrument detail — new route or panel? | **Existing route** (`/stocks`, `/etf`, `/funds`), upgraded to 6-tab structure (§4.6). Right-side panel was too thin. |
| 3 | Conviction Sizer — route or drawer? | **Drawer** (§4.7). Lighten the load. |
| 4 | Breadth color thresholds for RRG bubble | Green ≥ 60, Amber 40–60, Red < 40. Tunable in `signal_thresholds.yaml`. |
| 5 | "Aligned leaders only" filter exact rule | RS-pct > 50 AND Momentum > 0 AND Abs-Return (selected period) > 0. Default ON. |
| 6 | Default universe in Leaders by regime | BULL→Stocks, CAUTIOUS→Sectors, CORRECTION→ETFs, BEAR→ETFs. PM override sticky in localStorage. |
| 7 | MF→sector mapping (fixes v2 bug) | Use `de_mf_classification` category → curated sector map in `backend/config/mf_sector_map.yaml`. No substring match. |
| 8 | Methodology surface | Per-view "How this works" drawer (5 total). No top-level `/methodology` route. |
| 9 | Five signal threshold values | Locked in §3.3 with full numbers. Live in `signal_thresholds.yaml`. |
| 10 | Should Backtest tab actually backtest live? | **No** — read precomputed `atlas_signal_history` table (already exists). If gaps, render insufficient_data envelope per spec §18. |

---

## 9. Visual baseline & references

- `docs/design/reference/s2-drill-spine/*.png` — 6 atlas screenshots from v1 freelance (visual reference for what to retire)
- `/tmp/mp-shots/*.png` — 12 MarketPulse screenshots (visual baseline to elevate, NOT mirror)
- MarketPulse source for design parity reads only: `https://github.com/nimishshah1989/fie2` (cloned at `/tmp/fie2`)
- `frontend/src/components/lenses/FourLens.tsx` — existing 4-lens card, reuse + extend
- `frontend/src/components/funds/FundHeroBlock.tsx`, `frontend/src/components/stocks/StockHeroBlock.tsx` — existing hero blocks, reuse + reorganise into 6-tab structure

---

## 10. Done definition

S2 is DONE when **all 9 chunks** are DONE per orchestrator + post-chunk sync invariant (CLAUDE.md), AND:

- [ ] `/`, `/leaders`, `/sector/[key]`, `/book` live on `atlas.jslwealth.in`
- [ ] `/stocks/[symbol]`, `/etf/[ticker]`, `/funds/[id]` show the 6-tab structure
- [ ] Conviction Sizer drawer opens from any "Size it" button
- [ ] All 5 signal types render on every lens at every level (transparency rule)
- [ ] `signal_thresholds.yaml` is the single source of truth and is hot-reloadable
- [ ] `python scripts/check-api-standard.py` green
- [ ] `python scripts/check-spec-coverage.py` green
- [ ] `python .quality/checks.py` ≥ 80 on all 7 dims
- [ ] No new tables, no new Alembic migrations
- [ ] v1 freelance shells (`/global`, `/india`, `/sector/*`, `/etf/[ticker]`) retired (deleted or redirected)
- [ ] Sub-$100 burn confirmed against actual cost ledger

---

## 11. Kickoff

Fresh session, run:

```
/chunkmaster S2-0 — slice: docs/specs/slices/s2-drill-spine.md
                    model: opus for S2-0; sonnet for S2-1..S2-8
                    skip: speckit-clarify (resolved in §8)
```
