# S1-9: portfolios.html — watchlist + portfolio overview

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE
**Blocks:** S1-11
**Complexity:** M (5 hours)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 85, architecture: 85, frontend: 90

## Page-specific goal

Per-user portfolios + watchlist grid. Each holding row shows 7-chip
signal strip. Aggregate regime rollup at the top.

Spec §: §11. DP §: §3, §10, §12, §13, §15.

## Files

### New / rewrite
- `frontend/mockups/portfolios.html`
- `frontend/mockups/fixtures/portfolios.demo.json` — demo portfolio using real JIP scheme_codes
- `scripts/seed-portfolios.py`
- `tests/unit/fe_pages/test_portfolios_structure.py`

## Page skeleton

1. Portfolio selector + regime rollup
2. 4-universal-benchmarks row (portfolio vs each)
3. Holdings grid — one row per position:
   - symbol / scheme + weight
   - 7 chips
   - contribution to portfolio 1d/1m/1y return
   - deep-link to stock-detail or mf-detail
4. Portfolio-level divergences block
5. Interpretation sidecar
6. Simulate-this (what-if: rebalance via Lab)
7. Methodology footer

## Criteria ids

- `fe-p11-01..04` — §11 Portfolios structural
- `fe-dp-03/04/05/06/09/15`
- `fe-mob-09`, `fe-mob-11`, `fe-state-*`, `fe-c-*`

## Tests (≥ 5)

1. DOM: holdings grid has ≥ 8 rows
2. DOM: every row has 7 chips + weight + contribution
3. Data: weights sum to 1.0 ± 0.01
4. Data: every holding has real JIP-traceable identifier
5. Kill-list clean
