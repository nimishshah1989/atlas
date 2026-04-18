# S1-5: stock-detail.html — instrument deep-dive (stock hub spoke)

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE
**Blocks:** S1-11
**Complexity:** L (8 hours — this page is the richest)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 85, architecture: 90, frontend: 95

## Page-specific goal

The single-stock hub: regime · 7 chips · price/volume/breadth overlays ·
divergences block · signal history · four universal benchmarks ·
interpretation ladder · simulate affordance.

Spec §: §7. DP §: §3, §10, §11 (no 4-decision here — Today owns it), §12, §13, §14, §15, §16, §18.

## Files

### New / rewrite
- `frontend/mockups/stock-detail.html`
- `frontend/mockups/fixtures/stock-detail.reliance.json` (exemplar, sourced via JIP)
- `scripts/seed-stock-detail.py` — parameterised; committed with RELIANCE default
- `tests/unit/fe_pages/test_stock_detail_structure.py`

## Page skeleton

1. Instrument header: symbol, name, sector, market-cap band, last close, data-as-of
2. Regime banner (instrument-contextualised: regime blends country + sector + stock chips)
3. Signal strip with all 7 chips (RS/Momentum/Volume/Breadth/Gold-RS/Conviction/Divergences)
4. Four universal benchmarks row (instrument vs each)
5. Headline chart — dual-axis: price (left) vs NIFTY 50 TRI (right) with volume subplot
6. Divergences block (DP §10) — price-breadth / price-volume divergences with timestamps
7. Signal history table (DP §16) — last 30 transitions: ENTRY/EXIT/REGIME/WARN/CONFIRM + rule id
8. Interpretation sidecar (EXPLAIN + DESCRIBE)
9. Simulate-this → lab.html?symbol=RELIANCE
10. Methodology footer

## Fixture shape (stock-detail.reliance.json)

```json
{
  "data_as_of": "...", "source": "JIP de_stock_* + atlas_gold_rs_cache",
  "instrument": {"symbol":"RELIANCE","name":"...","sector":"Energy","cap_band":"LARGE","last_close":2890.50},
  "regime_blend": {"label":"risk-on","score":72},
  "chips": {"rs":"G","momentum":"G","volume":"A","breadth":"G","gold_rs":"AMPLIFIES_BULL","conviction":{"score":78,"band":"high"},"divergences_count":1},
  "benchmarks_rs": [{"key":"msci-world","rs_1m":1.2,"rs_3m":2.1,"rs_6m":0.8,"rs_12m":3.4}, ...4 rows...],
  "price_series": [[date,close,volume], ...5y...],
  "benchmark_series": [[date,nifty50tri_close], ...5y...],
  "divergences": [{"kind":"price-vs-breadth","detected_at":"...","severity":"medium"}],
  "signal_history": [{"ts":"...","class":"ENTRY","rule_id":"Zweig-1","direction":"bull"}, ...30...]
}
```

## Criteria ids

- `fe-p7-01..06` — §7 Stock Detail structural
- `fe-dp-03/04/05/06/07/08/09/11/14/15/16`
- `fe-mob-05`, `fe-state-*`, `fe-c-*`

## Tests (≥ 8)

1. DOM: all 7 chips present with correct `data-chip` values
2. DOM: four-universal-benchmarks has 4 rows
3. DOM: dual-axis chart has legend + axis + source + tooltip + explain slots (chart_contract)
4. DOM: divergences-block present (even if count=0, renders zero-state)
5. DOM: signal-history-table ≥ 1 tbody row when history non-empty
6. DOM: `data-tier='recommend'` absent
7. Data: conviction.score integer 0..100
8. Data: chips.gold_rs value ∈ allowed enum
