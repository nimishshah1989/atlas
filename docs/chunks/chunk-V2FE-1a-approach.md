# Chunk V2FE-1a — Approach

## Scope
Backend: zone-events + breadth divergences endpoints

## Data Scale
- de_breadth_daily: check at runtime (medium, ~2-5 years of daily data)
- de_bhavcopy_eq / de_equity_ohlcv: accessed via JIPDataService.get_chart_data — not loading raw tables directly
- de_fo_bhavcopy: 0 rows (confirmed empty — do NOT use)

## Chosen Approach

### detect_zone_events function
- Standalone module-level function in breadth_zone_detector.py
- Takes `symbol: str`, `lookback_days: int = 365`, plus a `JIPDataService` instance
- Calls `jip_svc.get_chart_data(symbol, from_date, to_date)` — which reads de_equity_ohlcv + de_equity_technical_daily
- Processes the returned dicts (date, close, sma_20, sma_200) in pure Python (only ~250 rows for 1y lookback — well under 1K row threshold)
- Tracks prev day zone state; emits crossing event when zone changes
- Returns list of dicts with Decimal values
- Fault-tolerant: empty list on sparse/missing JIP data

### detect_divergences function
- Thin wrapper in breadth_divergence_detector.py
- Delegates to existing `BreadthDivergenceDetector(session).compute(universe, window=20, lookback=lookback_days//30)`
- Wraps result in `{"divergences": ..., "_meta": {..., "source": "de_bhavcopy_eq"}}`

### Routes
- Two new GET routes in stocks.py BEFORE the /{symbol}/chart-data and /{symbol} catch-all routes
- Plain dict return (not Pydantic model) per §20.4 for near-realtime/opaque-upstream routes
- Fault-tolerant: always 200, never 500

## Wiki Patterns Checked
- [Plain Dict §20.4 Envelope](patterns/plain-dict-envelope-external-routes.md) — return dict[str, Any] directly for routes with variable schema
- [FastAPI Static Route Before Path Param](bug-patterns/fastapi-static-route-before-path-param.md) — CRITICAL: /breadth/zone-events and /breadth/divergences must be registered BEFORE /{symbol} and /{symbol}/chart-data
- [Conftest Integration Marker Trap](bug-patterns/conftest-integration-marker-trap.md) — tests/api/ conftest auto-marks all as integration; put new tests in tests/routes/ to avoid the trap

## Existing Code Being Reused
- `BreadthZoneDetector` class: KEPT INTACT, adding standalone function only
- `BreadthDivergenceDetector.compute()`: reused via wrapper function
- `JIPDataService.get_chart_data()`: existing method, takes (symbol, from_date: date, to_date: date)
- `_dec()` helper from stocks.py for Decimal conversion

## Test Strategy
- Tests go in `tests/routes/` NOT `tests/api/` to avoid the conftest integration marker trap
- Use AsyncClient with ASGITransport(app=app) pattern (same as tests/routes/test_system.py)
- Mock JIPDataService.get_chart_data and BreadthDivergenceDetector.compute via patch
- Must patch `get_db` even when handler doesn't call it directly (FastAPI resolves Depends eagerly)

## Edge Cases
- JIP returns empty list (sparse stock data): return `{"data": [], "_meta": {..., "insufficient_data": True}}`
- sma_20 or sma_200 is None for a day: skip that day (no zone assignment)
- lookback_days=0: treated as 1 day minimum
- All values None: return empty list
- Decimal serialization: FastAPI handles Decimal->str in JSON fine

## Expected Runtime
- detect_zone_events: < 100ms (only ~250 rows of data for 1y)
- detect_divergences: < 200ms (delegates to BreadthDivergenceDetector)
- Route handler total: < 300ms on t3.large

## Files Modified
1. backend/services/breadth_zone_detector.py — add detect_zone_events function
2. backend/services/breadth_divergence_detector.py — add detect_divergences wrapper
3. backend/routes/stocks.py — add 2 new routes BEFORE /{symbol} catch-alls
4. tests/routes/test_breadth_zone_events.py — new test file (NOT tests/api/)
5. tests/routes/test_breadth_divergences.py — new test file (NOT tests/api/)
