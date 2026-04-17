# V7-2: ETF detail + chart-data + rs-history routes

**Slice:** V7
**Depends on:** V7-1
**Blocks:** V7-5
**Complexity:** M (4–5 hours)
**Quality targets:** api: 85, code: 82

---

## Step 0 — Boot context

1. `cat CLAUDE.md` — **READ §17/§18/§20 IN FULL**
2. Memory: `project_v15_chunk_status.md`
3. Read `specs/014-v7-etf-global-goldrs/contracts/etf-detail.md`, `etf-chart-data.md`, `etf-rs-history.md`, `spec.md §FR-003..005`

## Goal

Three routes complete the ETF backend surface:
- `GET /api/etf/{ticker}` — summary + RS + technicals + optional gold_rs
- `GET /api/etf/{ticker}/chart-data?from=&to=` — OHLCV + technicals joined per date
- `GET /api/etf/{ticker}/rs-history?months=12` — daily RS points

## Files

### Modified
- `backend/services/etf_service.py` — add `get_detail`, `get_chart_data`, `get_rs_history`
- `backend/routes/etf.py` — add 3 routes
- `backend/schemas/etf.py` — add `ETFDetailResponse`, `ETFChartRow`, `RSHistoryPoint`

### New
- `tests/api/test_etf_detail.py` — ≥4 tests
- `tests/api/test_etf_chart_data.py` — ≥4 tests
- `tests/api/test_etf_rs_history.py` — ≥3 tests

## Punch list

1. `GET /api/etf/SPY` returns summary (`expense_ratio`, `benchmark`, `inception_date`) + rs + technicals + optional gold_rs.
2. `GET /api/etf/UNKNOWN` → 404 `ETF_NOT_FOUND`.
3. `GET /api/etf/SPY/chart-data` returns ~252 rows (default 1y window) each with date + OHLCV (Decimal) + 24 technicals.
4. `from`/`to` outside master range → 400 `INVALID_DATE_RANGE`.
5. Window > 1825 days → 400 `DATE_RANGE_TOO_LARGE`.
6. `GET /api/etf/SPY/rs-history?months=12` returns ~252 points; `months ∈ {1,3,6,12,24}`.
7. All DISTINCT ON wrapped.
8. `scripts/check-api-standard.py` exits 0.

## Tests (≥11)

1. `test_detail_returns_summary` — SPY core fields present, Decimal.
2. `test_detail_unknown_ticker_404_envelope`.
3. `test_detail_include_gold_rs_additive`.
4. `test_detail_distinct_on_no_duplicate_date`.
5. `test_chart_data_default_window_returns_252_rows` (±10).
6. `test_chart_data_date_range_too_large_400`.
7. `test_chart_data_invalid_date_range_400`.
8. `test_chart_data_decimal_not_float`.
9. `test_rs_history_returns_252_points_for_12m`.
10. `test_rs_history_invalid_months_400`.
11. `test_rs_history_unknown_ticker_404`.

## Post-chunk sync

`scripts/post-chunk.sh V7-2`. Smoke: `curl -s localhost:8010/api/etf/SPY/chart-data | jq '.data | length'`.
