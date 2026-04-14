# V4-3 Approach: Portfolio Analysis Engine

## Data Scale
- `atlas_portfolio_holdings`: O(10s-100s) rows per portfolio — no scale concern
- JIP `de_*` tables: read-only via JIPMFService (batch RS call, no N+1)
- All computations are in-Python with Decimal; no SQL aggregations needed at this row count

## Chosen Approach

**Pure Python computation service** — `PortfolioAnalysisService` reads holdings from repo, fetches JIP data through `JIPMFService`, computes portfolio-level metrics in Decimal arithmetic.

Rationale:
- Holdings per portfolio: under 100 rows — pure Python with Decimal is fine
- JIP data is already behind a service facade; no direct SQL allowed
- RS momentum uses batch call (`get_mf_rs_momentum_batch`) — single query, not N+1
- Fund detail/sectors/weighted technicals: one call per mapped holding (acceptable at this row count)

## Wiki Patterns Used
- **Decimal Not Float**: `str(x)` → `Decimal(str(x))` at all conversion boundaries
- **FastAPI Dependency Patch Gotcha**: must patch `get_db` in all tests even when service mocked
- **Contract Stub 501 Sync**: `test_portfolio_stubs.py` must be updated to flip `analysis` from 501 → 200
- **Zero-Value Truthiness Trap**: use `is not None` for all financial field checks
- **sum() Decimal Start Arg**: `sum(..., Decimal("0"))` for all Decimal sums

## Existing Code Reused
- `JIPMFService` — `get_fund_detail`, `get_fund_sectors`, `get_fund_weighted_technicals`, `get_mf_rs_momentum_batch`, `get_fund_overlap`
- `PortfolioRepo` — `get_portfolio`, `get_holdings`
- `backend/models/portfolio.py` — extended with new Pydantic models

## Files to Create/Modify
- **CREATE** `backend/services/portfolio/analysis.py` — `PortfolioAnalysisService`
- **MODIFY** `backend/models/portfolio.py` — add `HoldingAnalysis`, `AnalysisProvenance`, `PortfolioLevelAnalysis`, rich `PortfolioAnalysisResponse`
- **MODIFY** `backend/routes/portfolio.py` — wire the 501 stub
- **CREATE** `tests/unit/portfolio/test_analysis.py`
- **CREATE** `tests/api/test_portfolio_analysis.py`
- **MODIFY** `tests/api/test_portfolio_stubs.py` — flip analysis from 501 test to non-501 test

## Edge Cases
- Holdings with no `mstar_id` (pending/unmapped): included in value totals, excluded from JIP-derived metrics
- `get_mf_rs_momentum_batch` raises (negative cache): log warning, set `rs_data_available=False`, continue analysis
- `get_fund_detail` returns None: add holding to `unavailable` list with reason
- All JIP calls wrapped in try/except: graceful degradation, partial result > no result
- Empty portfolio: total_value=Decimal("0"), empty lists, weighted_rs=None
- Division by zero on weighted RS: guard when total_value = 0
- Decimal in JSONB: sanitize at persist boundary (analysis_cache)

## Analysis Computation
```
weighted_rs = sum(holding_value * rs_composite) / total_value
sector_weights = {sector: sum(weight_pct * holding_value/total_value) for each sector across holdings}
quadrant_distribution = count(holdings per quadrant)
weighted_sharpe = sum(holding_value * sharpe_ratio) / total_value_with_sharpe_data
```

## Determinism
- `data_as_of` param → passed through to log; JIP data is read-only snapshots
- Same `portfolio_id` + `data_as_of` → same held holdings → same JIP data → same computations
- No random elements

## Expected Runtime on t3.large
- For a 10-holding portfolio: ~10 JIP calls (parallelizable with asyncio.gather) + 1 batch RS call
- Using `asyncio.gather` for per-holding JIP fetches: ~500ms total for 10 holdings
- Acceptable for a non-realtime analysis endpoint

## No New DB Migrations
- `AtlasPortfolioSnapshot` already exists
- This chunk does not write to snapshots (read-only analysis computation)
- No schema changes
