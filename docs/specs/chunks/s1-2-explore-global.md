# S1-2: explore-global.html — global market regimes + universal benchmarks

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE
**Blocks:** S1-11
**Complexity:** M (4 hours)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 85, architecture: 85, frontend: 90

## Page-specific goal

Global view: 4 universal benchmarks + regional indices + Gold RS context.
Entry point into Country drill-down.

Spec §: §4. DP §: §3 (benchmarks), §10 (gold-rs), §12 (regime), §14 (dual-axis), §15.

## Files

### New (or rewrite)
- `frontend/mockups/explore-global.html`
- `frontend/mockups/fixtures/explore-global.json`
- `scripts/seed-explore-global.py`
- `tests/unit/fe_pages/test_explore_global_structure.py`

## Page skeleton (top to bottom)

1. Regime banner (global)
2. Four universal benchmarks (DP §3, mandatory) — with dual-axis chart comparing each vs a shared reference period
3. Regional grid: US / Europe / Japan / EM / India — one row per region with 4 RRG chips + Gold-RS amplifier
4. Gold RS amplifier strip — per-region amplifier verdict (AMPLIFIES_BULL/BEAR/NEUTRAL_BENCH_ONLY/FRAGILE/STALE)
5. Interpretation sidecar (EXPLAIN + DESCRIBE)
6. Deep-links to explore-country for each region
7. Methodology footer

## Fixture shape (`explore-global.json`)

```json
{
  "data_as_of": "2026-04-17",
  "source": "JIP de_global_price_daily + atlas_gold_rs_cache",
  "regime_global": {...},
  "benchmarks": [ msci-world · sp500 · nifty50tri · gold ],
  "regions": [
    {"region":"US", "chips": {"rs":"G","momentum":"G","volume":"A","breadth":"G"}, "gold_rs_signal":"AMPLIFIES_BULL", "data_as_of":"..."},
    ...
  ]
}
```

## Criteria ids this chunk must pass

- `fe-p4-01..03` — §4 Global structural
- `fe-dp-01`, `fe-dp-05`, `fe-dp-08`, `fe-dp-09`, `fe-dp-15`
- `fe-mob-02`, `fe-state-01/02/08`, `fe-c-01/02`

## Tests (≥ 5)

1. DOM: four-universal-benchmarks has 4 benchmark rows
2. DOM: regions grid has ≥ 5 rows, each with 4 chip attributes
3. DOM: every region row has `gold-rs-chip` with signal attr in allowed enum
4. Data: benchmarks carry numeric r_1d/r_1m/r_1y
5. Data: zero regional row missing `data_as_of`
