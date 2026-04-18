# S1-3: explore-country.html — India market view + instrument row grid

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE
**Blocks:** S1-11
**Complexity:** M (5 hours)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 85, architecture: 85, frontend: 90

## Page-specific goal

India market regime + searchable list of ~50 headline stocks with 7-chip
signal strip per row. Deep-link to stock-detail.

Spec §: §5. DP §: §3, §10, §12, §13, §14, §15.

## Files

### New / rewrite
- `frontend/mockups/explore-country.html`
- `frontend/mockups/fixtures/explore-country.json`
- `scripts/seed-explore-country.py`
- `tests/unit/fe_pages/test_explore_country_structure.py`

## Page skeleton

1. Regime banner (India)
2. Four universal benchmarks row
3. Nifty 50 + Nifty Midcap 100 + Smallcap 100 headline chart (dual-axis vs Gold as fourth universal)
4. Stock-row grid — ≥ 50 rows, each with:
   - symbol + name + market-cap band
   - 7 chips: RS / Momentum / Volume / Breadth / Gold-RS / Conviction / Divergences-flag
   - 1d / 1m / 1y returns with color-signed
   - deep-link to stock-detail.html?symbol=…
5. Mobile wrapper: `.mobile-scroll` around the grid for XS/S viewports
6. Interpretation sidecar
7. Simulate-this → lab.html?preset=country-view
8. Methodology footer

## Fixture shape

```json
{
  "data_as_of": "...", "source": "...",
  "regime_country": {...},
  "benchmarks": [...4...],
  "headline_indices": [{"key":"nifty50","series":[[d,v],...]}, ...],
  "stocks": [
    {
      "symbol":"RELIANCE", "name":"...", "cap_band":"LARGE",
      "chips": {"rs":"G","momentum":"G","volume":"A","breadth":"G","gold_rs":"AMPLIFIES_BULL","conviction":{"score":78,"band":"high"},"divergences_count":0},
      "r_1d":0.8, "r_1m":3.2, "r_1y":14.1, "data_as_of":"..."
    }
  ]
}
```

## Criteria ids

- `fe-p5-01..04` — §5 structural
- `fe-dp-03`, `fe-dp-04`, `fe-dp-05`, `fe-dp-06`, `fe-dp-08`, `fe-dp-09`, `fe-dp-14`, `fe-dp-15`
- `fe-mob-03`, `fe-mob-11`, `fe-state-*`, `fe-c-*`

## Tests (≥ 6)

1. DOM: ≥ 50 stock rows
2. DOM: every row has 7 chip elements
3. DOM: every row has a deep-link anchor to stock-detail
4. Data: every stock has non-null symbol + cap_band
5. Data: conviction.score integer 0..100
6. Data: chips.gold_rs ∈ {AMPLIFIES_BULL,AMPLIFIES_BEAR,NEUTRAL_BENCH_ONLY,FRAGILE,STALE}
