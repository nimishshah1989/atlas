# V7-4: Pro shell /pro/etf — RotationMap reuse + ETFUniverseTable + MacroContextPanel

**Slice:** V7
**Depends on:** V7-1, V7-3
**Blocks:** V7-5
**Complexity:** M (5–6 hours)
**Quality targets:** frontend: 82, code: 80

---

## Step 0 — Boot context

1. `cat CLAUDE.md`
2. Memory: `project_design_language.md`, `project_v15_chunk_status.md`, `project_c_der_signal_engine.md`
3. Read `docs/design/design-principles.md §10` (Gold RS amplifier), `frontend-viz.md`
4. Inspect existing `frontend/components/rotation-map/RotationMap.tsx` from C-DER-3 — **reuse, do not copy**

## Goal

`/pro/etf` renders three panels with real data, each wrapped in a per-panel `ErrorBoundary`:
- Top-left: RotationMap (reused from C-DER-3, fed by `/api/etf/universe?include=rs`)
- Top-right: MacroContextPanel (9 ratios + sparklines from `/api/global/ratios`)
- Bottom: ETFUniverseTable (AG Grid, Gold RS chip column, CSV export)

## Files

### New
- `frontend/components/etf/ETFUniverseTable.tsx` ≥ 180 lines
- `frontend/components/global/MacroContextPanel.tsx` ≥ 120 lines
- `frontend/components/gold-rs/GoldRSChip.tsx` ≥ 50 lines (reused by V7-5 + V7-6)
- `frontend/app/pro/etf/page.tsx` ≥ 100 lines
- `frontend/tests/e2e/pro-etf.spec.ts` ≥ 2 tests

## Punch list

1. Visit `/pro/etf` in dev server → renders without errors.
2. RotationMap shows real ETF quadrant positions from `/api/etf/universe?include=rs`.
3. MacroContextPanel renders exactly 9 sparklines with Indian number formatting + MoM chip (green/red, ±).
4. ETFUniverseTable lists ≥100 US ETFs with sortable Gold RS chip column (5-state color).
5. Hovering Gold RS chip shows tooltip with `rs_1m..rs_12m` + `gold_series`.
6. Per-panel `<ErrorBoundary>` — kill one endpoint → other two panels still render.
7. No `mockData` / hardcoded arrays (`grep` clean).
8. `npm run lint` clean, `npm run type-check` clean.

## Tests (Playwright)

1. `test_pro_etf_renders_all_three_panels` — golden path.
2. `test_pro_etf_macro_panel_failure_does_not_blank_table` — chaos: intercept `/api/global/ratios` → 500; assert RotationMap + ETFUniverseTable still render.

## Post-chunk sync

`scripts/post-chunk.sh V7-4`. Visual verify — take screenshot, paste URL into session log.
