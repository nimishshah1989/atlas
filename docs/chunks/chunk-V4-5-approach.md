# Chunk V4-5 Approach: Riskfolio-Lib Optimization

## Data Scale
- DB check skipped (no direct DATABASE_URL in shell env); JIP de_mf_nav_daily has historically ~2-5M rows
- Production candidate universe: 6-15 MF schemes per portfolio (not 1M+ rows)
- NAV history fetched per fund via JIPMFService.get_fund_nav_history(); ~252 rows/fund/year (1Y lookback = feasible in RAM)
- 12 funds × 252 daily returns = 3024 rows — trivially fits in pandas DataFrame

## Chosen Approach
Pure computation layer — no new DB tables, no Alembic migration.

1. **Pydantic models** added to `backend/models/portfolio.py` (OptimizationModel, RiskProfile, SEBIConstraint, OptimizedWeight, OptimizationResult, PortfolioOptimizationResponse)
2. **Service** `backend/services/portfolio/optimization.py` — constructor takes repo + jip, fetches NAV history via JIPMFService, builds returns DataFrame, runs riskfolio-lib MV and HRP
3. **Route** replaces 501 stub in `backend/routes/portfolio.py`
4. **Tests** at `tests/unit/portfolio/test_optimization.py` and `tests/api/test_portfolio_optimize.py`

## Computation Boundary Pattern (from wiki)
- float internally for numpy/riskfolio computation
- `Decimal(str(round(val, 4)))` at API boundary
- Pattern already used in V3-4 backtest, V3-6 optimizer, V4-4 attribution

## Riskfolio-Lib API (verified in shell)
- Version 7.2.1, numpy 2.4.4 — already installed
- `rp.Portfolio(returns=df)` → `.assets_stats()` → `.optimization(model='Classic', rm='MV', obj='Sharpe')`
- `rp.HCPortfolio(returns=df)` → `.optimization(model='HRP', rm='MV')`
- SEBI 10% cap: `port.upperlng = 0.10` (requires ≥10 assets to be feasible)
- Infeasibility: `.optimization()` returns `None` (not raises exception)
- Determinism: `np.random.seed(42)` before each run

## Edge Cases Handled
- Fewer than 10 funds: 10% cap may be infeasible → detected (weights is None), structured error returned
- Fund with <20 NAV data points: excluded from candidate universe (insufficient history)
- All funds excluded: error response with excluded_funds list
- NAV history fetch failure: fund added to excluded_funds, computation continues with remaining
- HRP requires ≥2 assets: guard added
- max_positions cardinality: riskfolio `port.card` is used but often returns None; gracefully fall back

## SEBI Constraints
- max_weight: `port.upperlng = float(max_weight)` — per-fund upper bound
- max_positions: `port.card = max_positions` — cardinality
- Sector caps: not implemented in V4-5 (holdings don't carry reliable sector labels yet); reserved field in SEBIConstraint

## Expected Runtime
- 12 funds × 252 rows: NAV fetch ~0.5-1s per fund (async concurrent) → ~2s total
- Riskfolio MV solve: <0.5s (small covariance matrix)
- HRP solve: <0.1s (hierarchical, no solver)
- Total: <5s comfortably under 10s limit
- EC2 t3.large (2 vCPU, 8GB): riskfolio uses cvxpy/scipy, single-threaded but light

## Wiki Patterns Checked
- Computation Boundary (28x): float->Decimal(str(round())) at API edge — applied
- AsyncMock Context Manager (2x): test pattern for async services — applied in tests
- FastAPI Dependency Patch Gotcha: patch get_db even when service mocked — applied
- FastAPI Static Route Before Path Param: static routes already correctly ordered in portfolio.py

## Existing Code Being Reused
- `PortfolioRepo.get_portfolio()` + `get_holdings()` — standard holding fetch
- `JIPMFService.get_fund_nav_history()` — NAV series per fund
- `AnalysisProvenance` model — already in portfolio.py
- Attribution service pattern (repo+jip constructor, async method) — copied exactly

## Files Modified
- `backend/models/portfolio.py` — append new optimization models
- `backend/services/portfolio/optimization.py` — new service (create)
- `backend/routes/portfolio.py` — replace 501 stub, add import
- `tests/unit/portfolio/test_optimization.py` — new unit tests
- `tests/api/test_portfolio_optimize.py` — new API tests
