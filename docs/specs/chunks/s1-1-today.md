# S1-1: today.html — Pulse page (regime banner + 4-decision grid + universal benchmarks)

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE, S1-0 (not a hard block but easier to preview)
**Blocks:** S1-11 (screenshot baseline)
**Complexity:** M (4–5 hours)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 85, architecture: 90, frontend: 95, security: 85

## Page-specific goal

The fund-manager's morning read: what's the market regime, what are the
four decisions to consider today, how are the four universal benchmarks
doing, what's moved overnight. Pure read-surface; Lab is where
simulation lives.

Spec § covered: §3 (Today page composition).
DP §: §3 (benchmarks), §10 (chips), §11 (four-decision card), §12
(regime banner), §13 (signal strip summary), §15 (interpretation
sidecar for the headline chart).

## Files

### New
- `frontend/mockups/today.html` (rewrite existing — take pulse-* artefacts as reference, not code)
- `frontend/mockups/fixtures/today.json` (page-level aggregate fixture)
- `scripts/seed-today-fixture.py` — pulls regime + 4-decision triggers + universal-benchmark returns from real JIP tables
- `tests/unit/fe_pages/test_today_structure.py`

## Page skeleton (mandatory blocks, top to bottom)

1. Regime banner (DP §12) — `data-regime` ∈ {risk-on,risk-off,neutral,mixed}, `data-as-of`
2. Four universal benchmarks row (DP §3) — MSCI World · S&P 500 · Nifty 50 TRI · Gold with 1d / 1m / 1y returns
3. Four-decision card grid (DP §11) — Buy-side / Size-up / Size-down / Sell-side, each showing the count of triggered rules from V1.1 rule set
4. Signal strip summary (DP §13) — aggregate counts: how many instruments have each chip green
5. Interpretation sidecar (DP §15) — EXPLAIN tier default, DESCRIBE tier toggle
6. "What changed overnight" section — top 5 regime/signal transitions since yesterday, deep-linking to stock-detail / mf-detail
7. Simulate-this affordance (DP §18) — deep-link to lab.html with today's regime pre-loaded
8. Methodology footer (data-as-of + source + disclaimer + kill-list disclosure)

## Fixture shape (`today.json`)

```json
{
  "data_as_of": "2026-04-17",
  "source": "JIP de_* tables + atlas_gold_rs_cache",
  "regime": {
    "label": "risk-on",
    "confidence": 0.72,
    "rationale_explain": "...",
    "rationale_describe": "Breadth 78% above 200DMA..."
  },
  "benchmarks": [
    {"key":"msci-world", "label":"MSCI World", "r_1d": 0.8, "r_1m": 3.2, "r_1y": 14.1, "data_as_of":"..."},
    ...four total...
  ],
  "four_decisions": [
    {"key":"buy-side", "triggered_count": 3, "rule_ids":["Zweig-1","JT-1","Minervini-1"]},
    ...four total...
  ],
  "signal_strip_summary": { "rs_green_count": 45, "momentum_green_count": 38, ... },
  "overnight_transitions": [ {"entity_id":"RELIANCE","from":"neutral","to":"risk-on","ts":"..."} ]
}
```

Zero synthetic data. Seed script queries JIP.

## Criteria ids this chunk must pass (selection)

- `fe-p3-01..05` — Today page §3 structural checks (GROUP 2)
- `fe-dp-01`, `fe-dp-12`, `fe-dp-13`, `fe-dp-15` — DP components on today
- `fe-mob-01` — no horizontal scroll at 360px
- `fe-state-01`, `fe-state-02`, `fe-state-08` — staleness + methodology footer
- `fe-c-01`, `fe-c-02` — EXPLAIN/DESCRIBE tier only, no RECOMMEND

## Tests (≥ 6 cases)

1. DOM: regime-banner present, data-regime is allowed enum
2. DOM: four-decision-card carries all 4 `data-card` values
3. DOM: four-universal-benchmarks row has exactly 4 `data-benchmark` nodes
4. Data: regime.label ∈ {risk-on,risk-off,neutral,mixed}
5. Data: every benchmark row has numeric r_1d/r_1m/r_1y
6. Data: `four_decisions[*].triggered_count` is integer ≥ 0
7. Kill-list: page source contains zero "BUY"/"SELL"/"recommend" standalone tokens
8. Seed-script determinism: re-run same `data_as_of`, zero diff
