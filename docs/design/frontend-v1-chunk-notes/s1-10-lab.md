# S1-10: lab.html — Signal Playback simulator (14-parameter v1.1)

**Slice:** V1-Frontend-Stage1
**Depends on:** S1-PRE-1 DONE, S1-8 breadth.html (Lab is its interactive twin)
**Blocks:** S1-11
**Complexity:** L (10 hours — most interactive page)
**Inherits:** docs/specs/chunks/s1-common.md
**Quality targets:** code: 90, architecture: 90, frontend: 95, security: 90

## Page-specific goal

The interactive simulator. Implements §10.5 Signal Playback with all 14
parameters — including the v1.1-elevated `L_exit` (was magic 350) and
`L_sip_resume` (was magic 200), plus formalised zone triggers `L_ob` and
`L_os`. No magic numbers anywhere in the rendered page or simulator
implementation.

Spec §: §10.5. DP §: §11, §12, §15, §18 (Lab is the canonical
simulation surface).

## Files

### New
- `frontend/mockups/lab.html` (derive from `breadth-simulator-v8.html` but rewrite for v1.1 parameter set)
- `frontend/mockups/fixtures/lab.defaults.json` — default param values (all 14)
- `frontend/mockups/lab.sim.js` — vanilla JS simulator; zero framework; deterministic
- `tests/unit/fe_pages/test_lab_structure.py`
- `tests/unit/fe_pages/test_lab_sim_determinism.py`

### Consumed
- `frontend/mockups/fixtures/breadth_daily_5y.json` (existing; real JIP source)
- `frontend/mockups/fixtures/zone_events.json`
- `frontend/mockups/fixtures/events.json`

## 14-parameter input panel (mandatory ids, §10.5.1)

Every input must carry the exact id the gate watches for:

```
i_initial        initial corpus (₹ lakh)
i_sip            monthly SIP (₹ k)
i_lumpsum        event-triggered lumpsum (₹ lakh)
i_sell400        sell % on extreme overbought
i_furtherLvl     further deployment trigger breadth level
i_furtherPct     further deployment %
i_redeployLvl    first redeploy breadth level
i_redeployPct    first redeploy %
i_redeploy2Lvl   second redeploy level
i_redeploy2Pct   second redeploy %
i_l_os           oversold sim trigger (L_os)
i_l_ob           overbought sim trigger (L_ob)
i_l_exit         exit-mode breadth threshold (formerly magic 350)
i_l_sip_resume   SIP-resume breadth threshold (formerly magic 200)
```

All 14 must be present, labelled, and numeric with tooltips citing
§10.5.1. Default values from `lab.defaults.json`. FIFO tax accounting
implemented in `lab.sim.js` with the 2024-07-23 regime split (STCG/LTCG
rate change date).

## Page skeleton

1. Regime banner (historical regime at t=simulation-start, not live today)
2. Parameter panel with all 14 inputs (grouped: capital / triggers / zones)
3. Methodology footer callout at the top near params: "every trigger is
   an editable parameter; nothing magic"
4. Run-simulation button → computes path → updates charts + result cards
5. Result visualisations:
   - Equity-curve chart (strategy vs buy-and-hold)
   - Deployments/redemptions timeline overlaid on breadth chart
   - Tax ledger table (FIFO lots + STCG/LTCG per the 2024-07-23 split)
6. Four-decision card grid — populated from the run: how many Buy/Size-up/Size-down/Sell-side triggers fired
7. Interpretation sidecar — EXPLAIN what the curve means, DESCRIBE what the params did
8. Methodology footer + disclosure

## Simulator determinism (lab.sim.js)

- No `Math.random()` anywhere
- No `new Date()` except for parsing fixture timestamps
- Input → output mapping must be a pure function of (params, fixture_data)
- Re-running with same params on same fixture: byte-identical result
  object (verified by `test_lab_sim_determinism.py` — runs 5x, asserts
  diff-free)

## Criteria ids

- `fe-p10_5-01` — 14 input ids present
- `fe-p10_5-02..08` — simulator behaviour checks (magic-number absence,
  tax ledger shape, FIFO correctness on sampled case)
- `fe-dp-01/12/13/14/15`
- `fe-mob-10`, `fe-state-*`, `fe-c-*`

## Tests (≥ 10)

1. DOM: all 14 `#i_*` inputs present with `type="number"` and tooltip refs
2. DOM: run button present; four-decision-card present
3. DOM: equity curve chart carries full chart_contract slots
4. Source: zero `350` or `200` literals in lab.html or lab.sim.js (except version strings); gate uses grep_forbid
5. Behaviour: clicking run with default params produces a deterministic result object (checksum match)
6. Behaviour: changing `i_l_exit` from default to 300 produces a different checksum
7. Behaviour: FIFO tax for a scenario crossing 2024-07-23 uses correct rate per lot
8. Behaviour: zero negative NAV state produced by the simulator
9. Kill-list clean (no BUY/SELL/RECOMMEND copy)
10. a11y: axe-core WCAG AA zero-violations (numeric inputs labelled)

## Post-chunk sync invariant

`scripts/post-chunk.sh S1-10` green. MEMORY.md entry
`reference_lab_simulator.md` capturing the 14-param table + determinism
protocol.
