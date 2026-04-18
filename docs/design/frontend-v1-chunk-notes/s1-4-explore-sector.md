# S1-4: explore-sector.html — Sector RRG chart + rotation table

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE (consumes sector_rrg.json seeded there)
**Blocks:** S1-11
**Complexity:** M (5 hours)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 85, architecture: 85, frontend: 95

## Page-specific goal

Sector rotation view. RRG chart (RS-ratio x RS-momentum, 4 quadrants,
8-week tails) as the headline. Sector-level signal strip rows below.

Spec §: §6. DP §: §3, §10, §12, §13, §14, §15.

## Files

### New / rewrite
- `frontend/mockups/explore-sector.html`
- `tests/unit/fe_pages/test_explore_sector_structure.py`

### Consumed (no new fixtures)
- `frontend/mockups/fixtures/sector_rrg.json` (seeded in S1-PRE-1)

## Page skeleton

1. Regime banner
2. RRG chart — SVG or canvas, 4 quadrants (leading/weakening/lagging/improving), 12 sector points each with 8-week tail
3. Sector table — 12 rows, each with: sector name, quadrant badge, 7 chips, Gold-RS signal, deep-link to filtered country view
4. Dual-axis overlay: top sector vs NIFTY 50 TRI
5. Interpretation sidecar
6. Simulate-this
7. Methodology footer

## Criteria ids

- `fe-p6-01..03` — §6 Sector RRG structural
- `fe-dp-03/04/05/08/09/14/15`
- `fe-mob-04`, `fe-state-*`, `fe-c-*`
- `fe-f-06`, `fe-f-07`, `fe-f-08` — sector_rrg fixture shape

## Tests (≥ 5)

1. DOM: RRG SVG/canvas contains 12 sector points
2. DOM: every sector row has quadrant badge with value in allowed enum
3. DOM: sector table has ≥ 12 rows, each with 7 chips
4. Data: every sector has tail length ≥ 8
5. Data: every sector's quadrant is consistent with (rs_ratio - 100, rs_momentum - 100) sign pair
