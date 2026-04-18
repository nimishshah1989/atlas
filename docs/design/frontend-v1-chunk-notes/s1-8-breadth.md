# S1-8: breadth.html — market breadth terminal

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE
**Blocks:** S1-10 lab.html (lab embeds breadth sim; breadth page is the read surface)
**Complexity:** M (6 hours)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 85, architecture: 90, frontend: 95

## Page-specific goal

Breadth terminal: advance/decline, % above 200DMA, new highs/lows,
zone-event history. The read-only companion to Lab's Signal Playback.

Spec §: §10. DP §: §10, §12, §13, §14, §15, §16, §18.

## Files

### New
- `frontend/mockups/breadth.html`
- `frontend/mockups/fixtures/breadth-page.json`
- `scripts/seed-breadth-page.py`
- `tests/unit/fe_pages/test_breadth_structure.py`

### Consumed
- `frontend/mockups/fixtures/breadth_daily_5y.json` (exists)
- `frontend/mockups/fixtures/zone_events.json` (exists)

## Page skeleton

1. Regime banner
2. Headline breadth chart — 5y daily % above 200DMA, with current zone banding (oversold / neutral / overbought)
3. Zone reconciliation note (§1.11) — distinguish reporting thresholds (OB/OS 400/100) from simulator-editable params (L_ob / L_os)
4. Advance/decline differential chart
5. New highs vs new lows chart
6. Zone-event history table — last 24 months of regime transitions
7. Interpretation sidecar
8. Simulate-this (DP §18) — deep-link to lab.html?preset=breadth-sim
9. Signal history table
10. Methodology footer

## Criteria ids

- `fe-p10-01..05` — §10 Breadth structural
- `fe-dp-08/09/11/14/15/16`
- `fe-mob-08`, `fe-state-*`, `fe-c-*`

## Tests (≥ 6)

1. DOM: headline chart carries legend+axis+source+tooltip+explain
2. DOM: zone-event table has ≥ 10 rows over trailing 24m
3. DOM: zone reconciliation note present ("OB_THRESHOLD" AND "L_ob" both referenced)
4. Data: every zone_events row has ts + from_zone + to_zone
5. Data: signal_history table aligns with zone_events (every REGIME entry has a corresponding zone event)
6. Kill-list clean
