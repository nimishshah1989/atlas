---
id: V2FE-1
title: "Backend gaps: zone-events + global-events + divergences + flows + UQL templates + conviction_series"
status: PENDING
estimated_hours: 10
deps: []
gate_criteria:
  - GET /api/v1/stocks/breadth/zone-events?universe=nifty500&range=5y returns 200 with zone_events.schema.json-valid payload
  - GET /api/v1/global/events?scope=india,global returns 200 with events.schema.json-valid payload
  - GET /api/v1/stocks/breadth/divergences?universe=nifty500 returns 200 with divergences[] array
  - GET /api/v1/global/flows?scope=fii_equity,dii_equity returns 200 or empty + insufficient_data true
  - POST /api/v1/query/template {template:"sector_rotation"} returns >=11 rows with sector_id, rs, rs_gold, conviction
  - POST /api/v1/query/template {template:"top_rs_gainers", params:{limit:10}} returns exactly 10 rows
  - POST /api/v1/query/template {template:"fund_1d_movers", params:{limit:5}} returns 5 rows
  - POST /api/v1/query/template {template:"mf_rank_composite"} parses against mf_rank_universe.schema.json
  - GET /api/v1/stocks/breadth?include=conviction_series returns conviction_series in response
  - Every new response carries _meta envelope per §6.4
  - scripts/check-api-standard.py exits 0 for all new routes
---

## Objective

Close the 5 backend gaps identified in §4.2 and §4.3 of the V2 spec that the per-page wiring chunks (V2FE-2..7) depend on. This is the backend-first chunk; no page wiring is allowed before this lands (Four Laws Law 3).

## Punch list

1. [ ] **Service: `backend/services/breadth_zone_detector.py`** (new)
   - Edge-triggered zone detector that replays the 5Y `de_equity_technical_daily` breadth count series (21EMA, 50DMA, 200DMA) and emits one row per zone entry/exit event.
   - Must include `prior_zone_duration_days` and `thresholds` block in output.
   - Deterministic: same `(universe, range, indicator, eod_date)` → same rows. No writes to JIP tables.
   - Redis cache TTL = 24h keyed on `(universe, range, indicator, eod_date)`. Use existing hiredis client from V7.
   - Output schema must match `frontend/mockups/fixtures/schemas/zone_events.schema.json`.

2. [ ] **Route: `GET /api/v1/stocks/breadth/zone-events`** — add to `backend/routes/stocks.py`.
   - Params: `universe` (enum), `range` (1y | 5y | all), `indicator` (21ema | 50dma | 200dma | all, default all).
   - Must register **before** any `/{symbol}` path-param route (FastAPI static-before-param rule).
   - Must go through `BreadthZoneDetector` service, no SQL in route handler.

3. [ ] **Service: `backend/services/event_marker_service.py`** (new)
   - Reads from new `atlas_key_events` table (seeded via Alembic migration).
   - Params: `scope` (csv of `india, global, sector:<slug>`), `range` (default 5y), `categories` (optional csv).
   - Redis cache TTL = 7d.
   - Output schema matches `frontend/mockups/fixtures/schemas/events.schema.json`.

4. [ ] **Alembic migration: `atlas_key_events`** (new table)
   - Columns: id (UUID PK), date (Date), category (String), severity (String), affects (JSONB), label (String), source (String), created_at, updated_at.
   - Seed migration: read `frontend/mockups/fixtures/events.json` and INSERT all rows in the migration's `upgrade()`. Idempotent: use `ON CONFLICT DO NOTHING`.
   - Downgrade drops the table.

5. [ ] **Route: `GET /api/v1/global/events`** — create `backend/routes/global_intel.py` (new module).
   - Params: `scope` (csv), `range`, `categories`.
   - Register via bare-import route registration pattern (parent adds import to main app).

6. [ ] **Service: `backend/services/breadth_divergence_detector.py`** (new)
   - Params: `universe`, `window` (days, default 20), `lookback` (months, default 3).
   - Computes divergences between Nifty 500 price change and `% above 50-DMA` breadth change over the window.
   - Empty result: `divergences: []` with `_meta.insufficient_data: false`.
   - Missing underlying: `_meta.insufficient_data: true`, block renders empty-state not error.
   - Response shape per §4.2.3.

7. [ ] **Route: `GET /api/v1/stocks/breadth/divergences`** — add to `backend/routes/stocks.py`. Must register before `/{symbol}` param routes.

8. [ ] **Service: `backend/services/flows_service.py`** (new)
   - Source: JIP `de_fii_dii_daily`. Verify table exists and row count > 0 using inline DB health gate pattern before computing.
   - If empty: return `{"_meta": {..., "insufficient_data": true}, "series": []}` (empty-state, not error).
   - Financial values: `Decimal`, INR crore at API boundary.
   - All date series must be IST-aware.

9. [ ] **Route: `GET /api/v1/global/flows`** — add to `backend/routes/global_intel.py`.

10. [ ] **UQL templates** in `backend/services/uql/templates/`: create 6 SQL template files (or extend template registry):
    - `sector_rotation.sql` — joins `de_equity_technical_daily` sectors with RS, gold_rs, momentum, conviction; returns 11+ sector rows.
    - `top_rs_gainers.sql` — top N stocks by RS delta descending.
    - `top_rs_losers.sql` — bottom N by RS delta.
    - `fund_1d_movers.sql` — top N funds by 1d NAV return.
    - `mf_rank_composite.sql` — 4-factor composite with Returns/Risk/Resilience/Consistency CDFs.
    - `mf_rank_history.sql` — batched rank history by `mstar_ids`.

11. [ ] **`include=conviction_series` on `GET /api/v1/stocks/breadth`** — extend existing breadth service to join `atlas_gold_rs_cache` and return per-date conviction chip state alongside breadth counts.

12. [ ] **Tests**:
    - `tests/services/test_breadth_zone_detector.py` — ≥6 tests covering zone entry/exit detection, prior_duration calculation, caching, empty-series handling.
    - `tests/services/test_breadth_divergence_detector.py` — ≥4 tests covering divergence detection, empty result, insufficient_data flag.
    - `tests/services/test_event_marker_service.py` — ≥4 tests covering scope filter, range filter, schema validation.
    - `tests/services/test_flows_service.py` — ≥4 tests covering empty-table path, Decimal enforcement, date range.
    - `tests/routes/test_global_intel.py` — ≥4 route-level tests.

13. [ ] Run `scripts/check-api-standard.py` — all new routes must pass UQL/include/error-shape compliance.

## Exit criteria

- `pytest tests/services/test_breadth_zone_detector.py tests/services/test_breadth_divergence_detector.py tests/services/test_event_marker_service.py tests/services/test_flows_service.py tests/routes/test_global_intel.py -v` all green.
- `curl -sf "http://localhost:8000/api/v1/stocks/breadth/zone-events?universe=nifty500&range=5y" | python -m json.tool` outputs valid JSON with `zone_events` array.
- `curl -sf "http://localhost:8000/api/v1/stocks/breadth/divergences?universe=nifty500" | python -m json.tool` outputs valid JSON.
- `curl -sf "http://localhost:8000/api/v1/global/events?scope=india" | python -m json.tool` outputs valid JSON.
- `curl -sf "http://localhost:8000/api/v1/global/flows" | python -m json.tool` outputs valid JSON (or empty + `insufficient_data: true`).
- `curl -sf -X POST "http://localhost:8000/api/v1/query/template" -H "Content-Type: application/json" -d '{"template":"sector_rotation","params":{}}' | python -m json.tool` returns ≥11 rows.
- `scripts/check-api-standard.py` exits 0.
- `alembic upgrade head` succeeds; `alembic downgrade -1` succeeds.
- `ruff check backend/routes/stocks.py backend/routes/global_intel.py backend/services/breadth_zone_detector.py backend/services/breadth_divergence_detector.py backend/services/event_marker_service.py backend/services/flows_service.py --select E,F,W` exits 0.
- No `float` in any new service file (grep clean).

## Domain constraints

- Read from JIP `de_*` tables only via `backend/clients/jip_data_service.py` — no direct SQL in service files.
- `de_adjustment_factors_daily` has 0 rows; `de_fo_bhavcopy` has 0 rows; `de_fii_dii_daily` must be probed before use (inline DB health gate pattern).
- All financial values `Decimal`. INR crore at API boundary for flows.
- All dates IST-aware. Use Arrow or pendulum, never naive datetime.
- Redis reuse: use the existing hiredis client from V7 (`backend/services/redis_client.py` or equivalent). Do not add a second cache layer.
- No SQL in route handlers — services only.
- `atlas_key_events` is the only new `atlas_*` table. No writes during read-path requests.
- Template SQL files must be parameterized (no string interpolation of user values).
