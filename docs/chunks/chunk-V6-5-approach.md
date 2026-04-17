---
chunk: V6-5
project: ATLAS
date: 2026-04-17
status: in_progress
---

# V6-5 Approach: Stock Conviction Pillar 3 (TV TA) + Chart-Data Endpoint

## Data Scale
- `de_equity_technical_daily`: 3,461,004 rows — needs WHERE date = latest + instrument_id predicate
- `de_equity_ohlcv`: 0 rows (base table) — data lives in year-partitioned tables `de_equity_ohlcv_y{year}`
- `de_equity_ohlcv` parent table IS queryable via partition routing (confirmed: 684,175 rows for 2025+)
- `de_instrument`: 2,743 rows
- For 1-year HDFCBANK chart data: ~252 rows (acceptable — single-stock, date-bounded)

## Key Discovery: Partitioned OHLCV
The spec says `FROM de_equity_ohlcv` — this works because PostgreSQL routes to partitions.
Confirmed: `SELECT COUNT(*) FROM de_equity_ohlcv WHERE date >= '2025-01-01'` = 684,175.
Do NOT use year-specific table names — query the parent table with date range WHERE clause.

## Approach

### Schema changes (schemas.py)
- Add `PillarExternal(BaseModel)` with `tv_ta: Optional[dict[str, Any]]` and `explanation: str`
- Add `pillar_3: Optional[PillarExternal] = None` to `ConvictionPillars`
- Add `partial_data: bool = False` to `ResponseMeta`
- Add `ChartDataPoint` and `ChartDataResponse` models
- `Any` already imported via `from typing import Any` — need to verify

### Computation (computations.py)
- Update `build_conviction_pillars` to accept `tv_ta_data: Optional[dict[str, Any]] = None`
- Build `PillarExternal` when tv_ta_data is not None
- Import `PillarExternal` from schemas

### Data service (jip_equity_service.py + jip_data_service.py)
- Add `get_chart_data(symbol, from_date, to_date)` method
- SQL: JOIN `de_equity_ohlcv` with `de_equity_technical_daily` via (instrument_id, date)
- Scale: ~252 rows for 1-year range — Python-safe, Decimal all financial fields
- Date params: pass as Python `date` objects (asyncpg requires this — see bug pattern)

### Route changes (stocks.py)
- In `get_stock_deep_dive`: fetch TV TA via TVCacheService, pass to `build_conviction_pillars`
- Set `partial_data=True` when TVBridgeUnavailableError or any exception
- Add `GET /{symbol}/chart-data` endpoint BEFORE `GET /{symbol}` (FastAPI static-before-param)
  - Actually `/{symbol}/chart-data` is more specific than `/{symbol}` — path length differentiates
  - Safe to register after /{symbol} since /HDFCBANK/chart-data won't match /{symbol}
  - But be safe: register chart-data route before /{symbol} in router registration order

## Wiki Patterns Checked
- [FastAPI Static Route Before Path Param](bug-patterns/fastapi-static-route-before-path-param.md) — register `/{symbol}/chart-data` BEFORE `/{symbol}` in router
- [Asyncpg Date String Parameter](bug-patterns/asyncpg-date-string-parameter.md) — pass datetime.date objects not strings
- [Conftest Integration Marker Trap](bug-patterns/conftest-integration-marker-trap.md) — tests go in tests/routes/ (confirmed present)
- [FastAPI Dependency Patch Gotcha](bug-patterns/fastapi-dependency-patch-gotcha.md) — must patch get_db even when mocking service

## Existing Code Reused
- `TVCacheService.get_or_fetch()` — already implemented in V6-3
- `TVBridgeClient` + `TVBridgeUnavailableError` — already implemented in V6-2
- `get_settings()` — already imported in config.py
- `_dec()` helper in stocks.py — reused for chart data point construction

## Edge Cases
- TV bridge down: `tv_ta = None`, `partial_data = True` in meta
- OHLCV empty (stock too new): return empty `data` list, no 404 (404 only if stock doesn't exist)
- No technicals JOIN: LEFT JOIN means technical fields = NULL for days without data
- date range defaulting: to_date defaults to today, from_date to 1 year back
- NULL volume: pass as-is (Optional[int])

## Expected Runtime on t3.large
- Chart data query: ~10-20ms (1-year single stock, index on instrument_id+date)
- TV TA fetch from cache: ~5ms (cache hit) or 503 (bridge down)
- Total deep-dive with TV TA: ~50ms (existing 34ms + TV cache lookup ~5ms)
