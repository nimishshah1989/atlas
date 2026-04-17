# V7-1: ETF Universe API — /api/etf/universe + DISTINCT ON helper

**Slice:** V7
**Depends on:** V7-0
**Blocks:** V7-2, V7-4
**Complexity:** M (4–6 hours)
**Quality targets:** api: 85, code: 82, architecture: 85

---

## Step 0 — Boot context

1. `cat CLAUDE.md` — **READ §17 UQL + §18 include + §20 principles IN FULL** (mandatory for any `backend/routes/` chunk).
2. `cat ~/.claude/projects/-home-ubuntu-atlas/memory/MEMORY.md` + `project_v15_chunk_status.md` + `reference_jip_data_atlas.md`
3. Read `specs/014-v7-etf-global-goldrs/contracts/etf-universe.md`, `spec.md §FR-001..005`, `data-model.md` DISTINCT ON template, `research.md` R-3 / R-9
4. `sed -n '1568,2100p' ATLAS-DEFINITIVE-SPEC.md` — §17 UQL + §18 include + §20 error envelope

## Goal

Ship `GET /api/etf/universe` as a thin wrapper over the shared UQL service. Reads ETF master + technicals + RS from JIP (DISTINCT ON wrapped). `include=gold_rs` is opt-in and additive — default shape stays stable.

## Files

### New
- `backend/services/jip_helpers.py` — `latest_per_ticker(session, table, tickers, as_of)` DISTINCT ON helper (≥60 lines)
- `backend/services/etf_service.py` — `get_universe(country, benchmark, include)` (≥150 lines)
- `backend/schemas/etf.py` — `ETFUniverseRow`, `ETFTechnicals` (24 fields), `ETFUniverseResponse` (≥80 lines)
- `backend/routes/etf.py` — `GET /api/etf/universe` (≥50 lines)
- `tests/api/test_etf_universe.py` — ≥8 tests

### Modified
- `backend/main.py` — register `etf.router`

## Punch list / acceptance criteria

1. `GET /api/etf/universe?country=US` → 200 with ≥100 rows.
2. Each row carries `ticker`, `name`, `country`, `currency`, `benchmark`, `expense_ratio` (Decimal).
3. `include=technicals` adds a `technicals` block with 24 fields; Decimal-typed.
4. `include=rs` adds `rs_composite`, `rs_momentum`, `quadrant`.
5. `include=gold_rs` adds the `gold_rs` block per `contracts/gold-rs-block.md`.
6. Default response (no include) is shape-stable: just the ETFUniverseRow core fields.
7. DISTINCT ON wraps every read of `de_etf_technical_daily` and `de_rs_scores`.
8. Error envelope `{error: {code, message, details}}` with codes `INVALID_INCLUDE`, `JIP_UNAVAILABLE`.
9. `scripts/check-api-standard.py` exits 0.
10. Redis 5-min cache keyed by `country|benchmark|sorted(include)`.

## Tests (≥8)

1. `test_universe_returns_us_etfs` — `country=US` → ≥100 rows, Decimal types.
2. `test_universe_no_duplicate_ticker_date` — assert `(ticker, date)` uniqueness in response.
3. `test_universe_include_technicals_adds_block` — block has RSI, MACD, Bollinger, ADX.
4. `test_universe_include_rs_adds_rs_fields` — rs_composite Decimal, quadrant enum.
5. `test_universe_include_gold_rs_additive` — default response shape unchanged when `gold_rs` omitted.
6. `test_universe_invalid_include_returns_400_envelope` — `include=foo` → 400 with `INVALID_INCLUDE`.
7. `test_universe_jip_down_returns_503_envelope` — mock client raises → 503 `JIP_UNAVAILABLE`.
8. `test_universe_decimal_types_not_float` — no `float` in serialized response (string-formatted Decimal).

## Post-chunk sync

`scripts/post-chunk.sh V7-1` — 5 phases. Smoke probe: `curl -s localhost:8010/api/etf/universe?country=US | jq '.data | length'` > 100.
