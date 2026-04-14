# Chunk V2-7 Approach: Overlap + holding-stock + NAV history routes

## Data Scale
No data scale check needed — this chunk writes nothing to atlas_* tables.
All reads go through JIPDataService → JIPMFService → de_* tables (JIP read-only).

## Approach

**Pure route-wiring work.** All three service methods already exist in `JIPMFService`
and are already exposed on the `JIPDataService` facade. No facade changes needed.

### 1. Overlap route `/api/v1/mf/overlap`
- Parse `funds` param (comma-separated), validate exactly 2, return 400 otherwise
- Call `svc.get_fund_overlap(fund_a, fund_b)` — already exists
- Map `common_holdings` (list of dicts with `weight_pct_a`, `weight_pct_b`, `instrument_id`, `holding_name`) → `OverlapHolding(instrument_id, symbol=holding_name, weight_a=weight_pct_a, weight_b=weight_pct_b)`
- `OverlapHolding.symbol` maps to `holding_name` key from JIP dict
- Return `OverlapResponse` with `fund_a`, `fund_b`, `overlap_pct`, `common_holdings`, `data_as_of`, `staleness`
- Add `db: AsyncSession = Depends(get_db)` to signature

### 2. Holding-stock route `/api/v1/mf/holding-stock/{symbol}`
- Call `svc.get_mf_holders(symbol)` — already exists
- JIP returns list of dicts with `mstar_id`, `fund_name`, `weight_pct`, `shares_held`, `market_value`
- Map to `FundHoldingStockEntry(mstar_id, fund_name, weight_pct)`
- Sort by `weight_pct` descending
- Return `HoldingStockResponse(symbol=symbol.upper(), funds=..., data_as_of=..., staleness=...)`
- Add `db: AsyncSession = Depends(get_db)` to signature

### 3. NAV history route `/{mstar_id}/nav-history`
- Call `svc.get_fund_nav_history(mstar_id, date_from, date_to)` — already exists
- Map each row to `NAVPoint(nav_date=..., nav=...)`
- Gap detection: if len(points) >= 2, compute `(max_date - min_date).days + 1 - len(points)` = calendar days including weekends. This surfaces total missing calendar days. Zero if no gaps or < 2 points.
- Return `NAVHistoryResponse(mstar_id, points, coverage_gap_days, data_as_of, staleness)`
- Add `db: AsyncSession = Depends(get_db)` to signature

## Wiki Patterns Applied
- **AsyncMock Context Manager Pattern**: use `MagicMock()` + `AsyncMock` on methods for test fixtures
- **FastAPI Dependency Patch Gotcha**: patch `backend.routes.mf.get_db` alongside JIPDataService mock
- **Contract Stub 501 Sync**: remove `/overlap`, `/holding-stock/RELIANCE`, `/nav-history` from `SKELETON_CALLS` in `test_mf_contracts.py`

## Existing Code Reused
- `_compute_staleness()` line 93 in `mf.py`
- `_data_as_of_from_freshness()` line 129 in `mf.py`
- `safe_decimal` from `backend.clients.sql_fragments`
- Test pattern from `tests/api/test_mf_deep_dive.py`

## Edge Cases
- **Overlap**: < 2 or > 2 funds → 400. Empty common_holdings → valid response. `overlap_pct` defaults to `Decimal("0")` in JIP service when no data.
- **Holding-stock**: symbol uppercased in response. Empty list → valid response (no 404).
- **NAV history**: empty → `coverage_gap_days=0`. Single point → `coverage_gap_days=0`. `nav` field must be Decimal not float.

## Facade Check
`JIPDataService` already exposes:
- `get_fund_overlap` (line 158)
- `get_mf_holders` (line 108)
- `get_fund_nav_history` (line 150)
- `get_mf_data_freshness` (line 164)

No facade changes needed.

## Expected Runtime
Tests run in < 5s on t3.large (all mocked, no real DB). Route logic is O(n) on holdings list.
