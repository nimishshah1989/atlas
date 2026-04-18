# S1-7: mf-rank.html — 4-factor composite ranking (dimensional-fix formula)

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE (consumes mf_rank_universe.json seeded there)
**Blocks:** S1-11
**Complexity:** M (5 hours)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 85, architecture: 90, frontend: 95

## Page-specific goal

The 4-factor MF ranking table. Implements the v1.1 dimensional-fix:
each raw factor is category-z-normalised via `z_cat(x)`, mapped through
Φ to 0..100, then composite = mean of four component scores to 1dp,
with explicit tie-break order Consistency → Risk → Returns → Resilience.

Spec §: §9. DP §: §10, §12, §13, §15, §16.

## Files

### New
- `frontend/mockups/mf-rank.html`
- `tests/unit/fe_pages/test_mf_rank_structure.py`

### Consumed (no new fixtures)
- `frontend/mockups/fixtures/mf_rank_universe.json` (from S1-PRE-1)

## Page skeleton

1. Regime banner
2. Category filter strip (chip-style multi-select)
3. 4-factor legend — explains each factor, its normalisation (z_cat + Φ), and tie-break order. **Formula disclosure is mandatory** (kill-list exception: expressing methodology is not a verdict).
4. Rank table — one row per fund:
   - rank, scheme name, AMC, category
   - Returns score, Risk score, Resilience score, Consistency score
   - Composite (1dp)
   - Tie-break rank
   - 7-chip strip
   - deep-link to mf-detail
5. Sparklines per row: 5y NAV mini-chart
6. Interpretation sidecar (explains what to notice, not what to buy)
7. Simulate-this (deep-link to lab with selected fund)
8. Methodology footer + formula block

## Criteria ids

- `fe-p9-01..04` — §9 MF-rank structural
- `fe-m-01..03` — MF-rank methodology + formula disclosure
- `fe-dp-03/04/05/06/09/15`
- `fe-mob-07`, `fe-mob-11`, `fe-state-*`, `fe-c-*`
- `fe-f-04`, `fe-f-05` — fixture shape + composite precision

## Tests (≥ 7)

1. DOM: rank table has ≥ 30 rows (matches fixture)
2. DOM: every row has 4 factor-score cells + composite + tie-break-rank
3. DOM: formula block present with text "z_cat" AND "composite" AND tie-break order
4. Data: composite score = round((returns+risk+resil+consist)/4, 1) for a sampled 5 rows
5. Data: tie-break ordering honoured — 2 rows with identical composite should sort by Consistency first
6. Data: no fund row has a factor score outside 0..100
7. Kill-list: no "BUY" / "TOP PICK" / "RECOMMEND" tokens
