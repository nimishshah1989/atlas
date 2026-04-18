# Atlas Sanitization Plan — V11 Series

**Goal:** Bring backend + data layer to a state where frontend work can begin without inheriting hidden debt — agile, observable, declaratively-configured, FOSS-leveraged.

**Non-negotiables baked in (per user mandate):**
1. **Agile** — every chunk ≤3 days, ships independently, reversible
2. **Responsive** — every routine + table emits status to a single dashboard
3. **Non-hardcoded** — table names, SLAs, source URLs all in YAML manifests; never in code
4. **Scalable** — adding a new data source = manifest edit + routine restart, no code change in Atlas
5. **Failure-localised** — health rubric scores 6 dimensions independently so a regression points to one dimension on one table

---

## Architecture decisions locking these in

| Decision | Where | Why |
|---|---|---|
| Single source of truth for tables | `docs/specs/data-coverage.yaml` | Adding a table never requires editing scripts |
| JIP↔Atlas contract is YAML | `docs/specs/jip-source-manifest.yaml` | Consumer + producer share one schema |
| Health is 6-dim, not boolean | `scripts/check-data-coverage.py` | Coverage gap ≠ freshness gap ≠ continuity gap; treating differently means faster MTTR |
| Routines visible, not cron | `de_routine_runs` + `/forge/routines` page | Cron is invisible; this surfaces every run |
| FOSS-first for analytics | empyrical, vectorbt, OpenBB, FinanceToolkit | Hand-rolled = bug surface + maintenance debt |
| Fail loud, not silent | `--strict` flag on health-check, gate in CI | Silent rot is worse than red CI |

---

## Chunk sequence

### V11-0 — Routine Visibility (foundation, do first)
**Scope:** systemd units + timers for every JIP routine; `de_routine_runs` table; Atlas `/api/system/routines` endpoint; `/forge/routines` Next.js page.
**Why first:** Everything downstream depends on knowing which routines ran, when, with what result. Without this, all sanitization work is blind.
**Effort:** 2–3 days. JIP-side systemd config + Atlas-side dashboard route.
**Frontend touch:** new `/forge/routines` page (read-only); reuses `/forge` chrome.
**Acceptance:** kill any routine — dashboard shows it red within 60s.

### V11-1 — Manifest + Health-Check Wiring (meta-chunk)
**Scope:** Adopt `docs/specs/data-coverage.yaml` as source of truth. Wire `scripts/check-data-coverage.py` into CI, post-chunk hook, and `/forge/data-health` page. Remove all hardcoded table-name lists from existing scripts.
**Why second:** Once V11-0 surfaces routines, V11-1 surfaces table-level health. Together they answer "is the data layer healthy?" objectively.
**Effort:** 1–2 days.
**Acceptance:** `python scripts/check-data-coverage.py --strict` runs in CI; failing health blocks merge.

### V11-2 — Adjustment Factors + Adjusted-Price View
**Scope:** JIP populates `de_adjustment_factors_daily` from `de_corporate_actions`. Atlas exposes `?adjusted=true` query param on price routes (default true).
**Why before frontend:** every chart shipped without this is wrong on day one for any stock with a split/bonus.
**Effort:** JIP 2 days, Atlas 1 day.
**Acceptance:** known split (e.g. RELIANCE 1:1 bonus history) renders smoothly.

### V11-3 — Gold Lens
**Scope:** `?denomination=inr|gold|usd` query param on instrument + index routes. Compute on the fly via `gold_view_service.py` (already exists, populate `atlas_gold_rs_cache`). Frontend toggle in chart header.
**Why:** wishlist item (i); user explicitly approved as derived view, not parallel storage.
**Effort:** 2 days.
**Acceptance:** RS-vs-gold for any instrument matches manual computation; chart toggle works.

### V11-4 — Derivatives + VIX Ingestion
**Scope:** JIP ships `de_fo_bhavcopy_daily`, `de_fo_participant_oi_daily`, `de_india_vix_daily`. Atlas exposes `/api/derivatives/{symbol}/oi`, `/api/derivatives/pcr/{symbol}`, `/api/macros/vix`. PCR + max-pain computed on the fly.
**Why:** unlocks options-driven sentiment in commentary engine.
**Effort:** JIP 5–7 days (largest single-table backfill); Atlas 2 days.
**Acceptance:** PCR for NIFTY matches NSE-published value; OI buildup chart renders.

### V11-5 — empyrical Adoption (FOSS migration #1)
**Scope:** Replace hand-rolled risk metrics in `backend/services/simulation/analytics.py` with empyrical (Sharpe, Sortino, Calmar, max drawdown, downside deviation, tail ratio, VaR, CVaR). Side-by-side validation: empyrical vs hand-rolled must agree to 4 decimals on a fixture set before cutover.
**Why:** lower bug surface, free upgrades, industry-standard semantics.
**Effort:** 1–2 days.
**Acceptance:** all simulation endpoints return identical numbers; hand-rolled code deleted.

### V11-6 — vectorbt Port of Backtest Engine (FOSS migration #2)
**Scope:** Re-implement `backend/services/simulation/backtest_engine.py` on vectorbt. Keep old engine behind `?engine=legacy` for one chunk; cut over once parity verified on 5 reference simulations.
**Why:** vectorbt is 100–1000x faster for parameter sweeps; the simulation roadmap (regime sweeps, multi-asset rotation backtests) requires this.
**Effort:** 3 days.
**Acceptance:** parity vs legacy on reference simulations; ≥10x speedup on a sweep.

### V11-7 — Macro Layer (yields + FX + RBI policy)
**Scope:** JIP ships `de_in_gsec_yields_daily`, `de_fx_rates_daily`, `de_rbi_policy_rates`. Atlas exposes `/api/macros/yield-curve`, `/api/macros/fx`, `/api/macros/policy-events`. Frontend macro page consumes.
**Effort:** JIP 3 days; Atlas 2 days.

### V11-8 — Insider + Bulk/Block Deals
**Scope:** JIP ships `de_insider_trades`, `de_bulk_deals`, `de_block_deals`. Atlas surfaces on stock detail page + alerts.
**Effort:** JIP 2 days; Atlas 1 day.

### V11-9 — OpenBB + FinanceToolkit Pilot (FOSS migration #3)
**Scope:** Pick one route (suggest `/api/stocks/{symbol}/analysis`). Replace bespoke analysis composition with OpenBB SDK + FinanceToolkit. If commentary quality + perf hold, broaden in V9.
**Effort:** 2 days for pilot.
**Acceptance:** A/B vs current analysis route shows richer structured signals at ≤1.5x latency.

### V11-10 — Backfill + Coverage Sweep (close-out)
**Scope:** Backfill `de_institutional_flows` 10y, shareholding pattern 5y, securities-in-ban 3y. Re-run health check, expect ≥90 overall on every domain.
**Effort:** JIP 3 days; Atlas verifies.
**Acceptance:** `python scripts/check-data-coverage.py --strict` green across all domains.

---

## Total effort

- **Atlas-side:** ~12–14 working days across V11-0 → V11-10
- **JIP-side:** ~18–22 working days (P1+P2+P3 ingestion + observability)
- **Parallelisable:** Atlas can ship V11-0/V11-1/V11-3/V11-5/V11-6/V11-9 without waiting on JIP

---

## What unblocks frontend (in priority order)

| Frontend module | Required before shipping |
|---|---|
| Stocks/MFs basic charts + lists | V11-0, V11-1, V11-2 |
| Gold-denominated view toggle | V11-3 |
| RRG + sector rotation | already unblocked |
| Market commentary (text) | V11-1 + V11-4 (VIX) |
| Options chain / PCR / max-pain | V11-4 |
| Macro dashboard | V11-7 |
| Insider/bulk-deal feed | V11-8 |
| Simulation UI (existing engine) | already unblocked |
| Simulation UI (vectorbt sweeps) | V11-6 |

**Frontend can start in parallel** with V11-0 + V11-1 — they're ~3 days combined and produce the observability surface frontend needs anyway. The blocker pattern is "ship Atlas frontend X only after V11-Y green."

---

## Architectural guardrails (enforced by hooks)

- Any new table → must be in `data-coverage.yaml` first; CI fails otherwise.
- Any new external data source → must be in `jip-source-manifest.yaml`; JIP CI fails otherwise.
- Any hand-rolled risk/portfolio/backtest math → ruff custom rule flags it; reviewer asks for FOSS lib.
- Health-check failure → `/forge/data-health` shows red; frontend module dependent on that domain auto-disabled (feature flag wired to health JSON).
