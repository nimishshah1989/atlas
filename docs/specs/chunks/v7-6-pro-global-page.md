# V7-6: Pro shell /pro/global — MacroContextPanel + GlobalIndicesTable

**Slice:** V7
**Depends on:** V7-3
**Blocks:** V7-7
**Complexity:** S (3–4 hours)
**Quality targets:** frontend: 82

---

## Step 0 — Boot context

1. `cat CLAUDE.md`
2. Read `specs/014-v7-etf-global-goldrs/contracts/global-indices.md`, `global-ratios.md`, `global-rs-heatmap.md`
3. Reuse `MacroContextPanel` from V7-4.

## Goal

`/pro/global` renders two panels:
- Top: `MacroContextPanel` (reused from V7-4, fed by `/api/global/ratios`)
- Below: `GlobalIndicesTable` — 4-bench RS columns + `gold_rs_signal` chip + `four_bench_verdict` chip

## Files

### New
- `frontend/components/global/GlobalIndicesTable.tsx` ≥ 180 lines
- `frontend/app/pro/global/page.tsx` ≥ 80 lines
- `frontend/tests/e2e/pro-global.spec.ts` ≥ 2 tests

## Punch list

1. `/pro/global` renders with real data; no mocks.
2. GlobalIndicesTable columns: ticker, name, currency, `rs_vs_msci_world`, `rs_vs_sp500`, `rs_vs_nifty50`, `rs_vs_gold_usd`, `gold_rs_signal` chip, `four_bench_verdict` chip.
3. Sortable by any RS column. Right-aligned numbers per frontend-viz.md.
4. `four_bench_verdict` chip colors: STRONG_BUY green / BUY light-green / HOLD grey / CAUTION orange / AVOID red.
5. Per-panel ErrorBoundary.
6. `npm run lint` + `type-check` clean.

## Tests (Playwright)

1. `test_pro_global_renders_both_panels`.
2. `test_pro_global_indices_table_sortable_by_rs_column`.

## Post-chunk sync

`scripts/post-chunk.sh V7-6`.
