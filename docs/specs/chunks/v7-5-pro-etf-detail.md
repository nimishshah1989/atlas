# V7-5: Pro shell /pro/etf/[ticker] — candlestick + RSHistory + Technicals + GoldRS chip

**Slice:** V7
**Depends on:** V7-2, V7-4
**Blocks:** V7-7
**Complexity:** L (6–7 hours)
**Quality targets:** frontend: 82, code: 80

---

## Step 0 — Boot context

1. `cat CLAUDE.md`
2. Memory: `project_v6_tv_sidecar.md` (lightweight-charts already integrated), `project_design_language.md`
3. Read `specs/014-v7-etf-global-goldrs/spec.md §FR-003`, `contracts/etf-detail.md`, `etf-chart-data.md`, `etf-rs-history.md`

## Goal

`/pro/etf/[ticker]` renders the full deep-dive: candlestick chart, 12-month RS line, 4-tile technicals panel, Gold RS amplifier chip with 5-state tooltip, and the summary row (expense_ratio, benchmark, inception_date).

## Files

### New
- `frontend/components/etf/CandlestickChart.tsx` ≥ 120 lines (uses existing lightweight-charts from V6 TV sidecar)
- `frontend/components/etf/RSHistoryChart.tsx` ≥ 100 lines (recharts line)
- `frontend/components/etf/TechnicalsPanel.tsx` ≥ 120 lines (4 tiles: RSI, MACD, Bollinger, ADX)
- `frontend/components/gold-rs/GoldRSAmplifierChip.tsx` ≥ 80 lines (reuses GoldRSChip from V7-4 with expanded tooltip)
- `frontend/app/pro/etf/[ticker]/page.tsx` ≥ 120 lines
- `frontend/tests/e2e/pro-etf-detail.spec.ts` ≥ 3 tests

## Punch list

1. Visit `/pro/etf/SPY` → renders without errors; all panels populated from real API.
2. CandlestickChart shows ~252 bars for default 1y window; Decimal OHLC formatted.
3. RSHistoryChart shows 12-month daily RS line with hover tooltip (exact value).
4. TechnicalsPanel shows 4 tiles with current RSI / MACD / Bollinger position / ADX values + green/red indicator.
5. GoldRSAmplifierChip displays one of 5 signals (AMPLIFIES_BULL / AMPLIFIES_BEAR / NEUTRAL_BENCH_ONLY / FRAGILE / STALE) with color coding per design-principles.md §10.
6. Tooltip on chip shows `rs_1m`, `rs_3m`, `rs_6m`, `rs_12m` + `gold_series`.
7. Summary row shows expense_ratio (2dp %), benchmark (name), inception_date (DD-MMM-YYYY).
8. Per-panel `ErrorBoundary` prevents one failure from blanking page.
9. No mocks. `npm run lint` + `type-check` clean.

## Tests (Playwright)

1. `test_detail_renders_all_panels_for_spy` — golden path, all four components visible.
2. `test_detail_gold_rs_chip_shows_one_of_five_signals`.
3. `test_detail_rs_history_chart_shows_252_points`.

## Post-chunk sync

`scripts/post-chunk.sh V7-5`. Visual verify via browser screenshot.
