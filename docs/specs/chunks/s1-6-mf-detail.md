# S1-6: mf-detail.html — mutual fund deep-dive (MF hub spoke)

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE
**Blocks:** S1-11
**Complexity:** L (7 hours)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 85, architecture: 90, frontend: 95

## Page-specific goal

Single-fund hub, parallel structure to stock-detail but NAV-axis rather
than price-axis, with weighted-technicals block (derived from underlying
holdings) replacing raw volume.

Spec §: §8. DP §: §3, §10, §12, §13, §14, §15, §16, §18.

## Files

### New / rewrite
- `frontend/mockups/mf-detail.html`
- `frontend/mockups/fixtures/mf-detail.ppfas_flexi.json` (already has nav series; extend)
- `scripts/seed-mf-detail.py`
- `tests/unit/fe_pages/test_mf_detail_structure.py`

## Page skeleton

1. Fund header: scheme name, AMC, category, AUM, expense ratio, last NAV, data-as-of
2. Regime banner (category-contextualised)
3. Signal strip — 7 chips (weighted-technicals-derived RS/Momentum/Volume/Breadth + Gold-RS + Conviction + Divergences)
4. Four universal benchmarks row (fund vs each)
5. Headline chart — dual-axis NAV (left) vs category average (right), 5y
6. Weighted-technicals block — aggregated chips across top holdings
7. Divergences block (fund-level: NAV vs weighted-technical aggregate)
8. Signal history table
9. Interpretation sidecar
10. Simulate-this → lab.html?mf=<scheme_code>
11. Methodology footer

## Criteria ids

- `fe-p8-01..06` — §8 MF Detail structural
- `fe-dp-03/04/05/06/07/08/09/11/14/15/16`
- `fe-mob-06`, `fe-state-*`, `fe-c-*`

## Tests (≥ 7)

1. DOM: fund header carries scheme_code, AMC, category
2. DOM: 7 chips present
3. DOM: weighted-technicals block present with per-chip aggregate
4. DOM: signal-history-table present
5. Data: last NAV is Decimal-like (not float-looking scientific notation)
6. Data: benchmarks_rs carries 4 rows
7. Kill-list: no "RECOMMEND" / "BUY this fund" language
