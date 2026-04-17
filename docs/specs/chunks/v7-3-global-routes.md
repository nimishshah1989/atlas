# V7-3: Global routes — /api/global/ratios + /rs-heatmap + /indices

**Slice:** V7
**Depends on:** V7-0
**Blocks:** V7-6
**Complexity:** M (4–6 hours)
**Quality targets:** api: 85, code: 82, architecture: 85

---

## Step 0 — Boot context

1. `cat CLAUDE.md` — **READ §17/§18/§20 IN FULL**
2. Memory: `reference_jip_data_atlas.md`
3. Read `specs/014-v7-etf-global-goldrs/contracts/global-ratios.md`, `global-rs-heatmap.md`, `global-indices.md`, `spec.md §FR-006..009`

## Goal

Three routes surface the Global slice:
- `/api/global/ratios` — 9 macro series + 10-pt sparklines + MoM change
- `/api/global/rs-heatmap` — 131 instruments grouped by `instrument_type`
- `/api/global/indices` — 4-bench RS + `gold_rs_signal` + `four_bench_verdict`

## Files

### New
- `backend/services/global_service.py` — 3 service fns (≥200 lines)
- `backend/schemas/global_.py` — `MacroRatio`, `RSHeatmapGroup`, `GlobalIndicesRow` (≥120 lines)
- `backend/routes/global_.py` — 3 routes (≥60 lines)
- `tests/api/test_global_ratios.py` ≥3 tests
- `tests/api/test_global_rs_heatmap.py` ≥3 tests
- `tests/api/test_global_indices.py` ≥5 tests

### Modified
- `backend/main.py` — register `global_.router`

## Punch list

1. `/api/global/ratios` returns exactly 9 series (US10Y, US2Y, DXY, Gold, WTI, VIX, BTC, USD/INR, India10Y).
2. Each series has `latest`, `sparkline` (10 Decimal points), `mom_change` (Decimal).
3. `/api/global/rs-heatmap` total count across 5 groups = 131.
4. Each heatmap row has `rs_score`, `rs_momentum`, `quadrant ∈ {LEADING, IMPROVING, WEAKENING, LAGGING}`.
5. `/api/global/indices` every row has 4 RS fields + `gold_rs_signal` (5-enum) + `four_bench_verdict` (5-enum).
6. Verdict derivation: count of `rs_* > 0` → 4=STRONG_BUY, 3=BUY, 2=HOLD, 1=CAUTION, 0=AVOID; nulls count as non-positive.
7. DISTINCT ON wraps `de_global_technical_daily` + `de_rs_scores` reads.
8. Redis 5-min cache.
9. `scripts/check-api-standard.py` exits 0.

## Tests (≥11)

1. `test_ratios_returns_nine_series`.
2. `test_ratios_sparkline_is_ten_decimals`.
3. `test_ratios_mom_change_decimal_not_float`.
4. `test_heatmap_total_is_131`.
5. `test_heatmap_five_groups_present` — indices, forex, commodities, crypto, bonds.
6. `test_heatmap_quadrant_enum`.
7. `test_indices_four_bench_verdict_strong_buy` — all 4 RS > 0 → STRONG_BUY.
8. `test_indices_four_bench_verdict_avoid` — all 4 RS ≤ 0 → AVOID.
9. `test_indices_null_rs_treated_as_non_positive` — 2 real positive + 2 null → HOLD.
10. `test_indices_gold_rs_signal_five_enum_values`.
11. `test_indices_decimal_not_float`.

## Post-chunk sync

`scripts/post-chunk.sh V7-3`. Smoke: `curl -s localhost:8010/api/global/indices | jq '.data | length'`.
