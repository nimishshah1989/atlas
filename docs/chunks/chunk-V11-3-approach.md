# Chunk V11-3 Approach — Gold/USD Denomination Lens

## Data Scale

- `de_global_price_daily` for GOLDBEES: 4,093 rows (2010-01-03 to 2026-03-30)
- `de_global_price_daily` for USDINR=X: 3 rows (2026-04-09 to 2026-04-14)
- Scale: <10K rows per ticker — Python dict intersection is fine; no SQL aggregation needed
- Typical 365d date range query returns ~252 trading day rows for an instrument

## Chosen Approach

**Pure computation service pattern** (denomination_service.py): no DB/async/IO.
Takes two in-memory lists and returns the intersection. All arithmetic Decimal.

**SQL fetch**: `get_global_price_series` method added to JIPEquityService.
Simple SELECT with date range WHERE — returns (date, Decimal) tuples.
Row count ~252 for 1y range, well within pandas-free threshold.

**Cache**: In-process dict cache in instruments.py (`_DENOM_CACHE`), keyed by
`(ticker, from_date_str, to_date_str)`, 60s TTL (same as health cache pattern).
Cache hit proves DB fetch skipped.

## Wiki Patterns Applied

- `decimal-not-float`: Decimal(str(val)) at DB boundary; quantize(Decimal("0.0001"))
- `mypy-strict-dict-json-typing`: `_DENOM_CACHE` typed as
  `dict[tuple[str, str, str], tuple[float, list[tuple[date, Decimal]]]]`
  (concrete generic chain throughout)
- `soft-degradation-price-gate`: empty denom series → warning in _meta.warnings, not 503
- `pydantic-v2-meta-serializer`: denomination field added to PriceMeta, serialized via existing model_serializer
- `plain-dict-envelope-external-routes`: route stays dict[str, Any] return type

## Existing Code Reused

- `backend/routes/instruments.py` — `_HEALTH_CACHE` pattern replicated for `_DENOM_CACHE`
- `backend/services/adjustment_service.py` — pure computation pattern, same approach
- `backend/clients/jip_equity_service.py` — new method follows same SQL text() pattern
- `backend/models/instruments.py` — add one field to PriceMeta, no structural changes

## Edge Cases Handled

- NULL close in de_global_price_daily: `WHERE close IS NOT NULL` in SQL
- Zero denominator: close set to None (not divide-by-zero error)
- Empty denom series: returns ([], None); route logs warning, returns raw INR with warning
- None close_inr: preserved as None in output
- Date intersection: only dates present in BOTH series (denom_map.get(row_date) is None check)
- denom_data_as_of = None when empty: treated as no constraint on staleness

## Staleness Logic

`data_as_of = min(instrument_data_as_of, denom_data_as_of)` (worst-of).
Note USDINR=X only has 3 rows starting 2026-04-09, so USD denomination will
often yield short series or empty for historical queries.

## Expected Runtime on t3.large

- DB fetch for denom series (1y range): <50ms (simple indexed date-range query)
- Python intersection for 252 rows: <1ms
- Cache hit: <1ms (dict lookup)
- Total: <100ms typical, <200ms cold

## Files to Modify/Create

1. CREATE `backend/services/denomination_service.py`
2. CREATE `tests/unit/test_denomination_service.py`
3. MODIFY `backend/clients/jip_equity_service.py` (add method + Decimal import)
4. MODIFY `backend/models/instruments.py` (add denomination field)
5. MODIFY `backend/routes/instruments.py` (cache + route param + conversion)
6. MODIFY `tests/routes/test_instruments.py` (append new tests)
