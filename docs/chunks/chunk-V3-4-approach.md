---
chunk: V3-4
project: atlas
date: 2026-04-14
status: in-progress
---

# V3-4 Approach: Backtest Engine + Analytics + SimulationService.run

## Data scale
- No DB writes for the compute phase; all pure computation
- Signal series and price series are passed in-memory
- Typical simulation: 2-5 years of daily data = ~500-1300 rows per series
- Well within 1K-100K range — pandas not needed; pure Python list iteration is fine
- AtlasSimulation DB: persists result JSONB after computation

## Chosen approach

### backtest_engine.py
Pure dataclass-based computation engine. No pandas, no DB, no async.
- Walk price_series + signal_series jointly (date intersection)
- SIP: track first trading day per (year, month) pair
- State machine for lumpsum cooldown: track last_lumpsum_date
- FIFOLotTracker for lot management and sell taxation
- All arithmetic in Decimal — convert via Decimal(str(x)) at boundaries
- Return BacktestResult dataclass

### analytics.py
Pure functions over BacktestResult. No pandas, no DB, no async.
- CAGR: standard formula with actual-day count
- XIRR: Newton's method with Decimal arithmetic, 20 iterations max, fallback Decimal("0")
- Sharpe/Sortino: compute from daily_values.total returns
- vs_plain_sip: simulate plain SIP over same price_series with same calendar
- max_drawdown: running peak from daily_values.total

### service.py
Async orchestration layer:
- Accept optional price_data + signal_data + jip parameter
- For MF: jip.get_fund_nav_history() → price_data
- Run get_adapter() to build signal series from signal_data
- For COMBINED signal: build two series then combine_signals()
- Run BacktestEngine.run()
- Run compute_analytics()
- Build TaxSummary via compute_annual_tax_summary() per FY
- Save to atlas_simulations via SimulationRepo
- Return SimulationResult

### routes/simulate.py
Wire POST /run to SimulationService.run_backtest().
Keep GET / as 501 stub for V3-5.
Update Contract-Stub-501-Sync list.

## Wiki patterns checked
- Pure Computation Agent: backtest_engine + analytics are pure computation (no LLM, no DB)
- AST-Scanned Anti-Pattern Detection: tests scan for float annotations and print() calls
- Decimal Not Float: all financial math uses Decimal via str() conversion at boundaries
- sum() Decimal Start Arg: use sum(..., Decimal("0")) for all generator sums

## Existing code reused
- FIFOLotTracker.add_lot / sell_units / total_units from tax_engine.py
- IndianTaxRates.get_rates() from tax_engine.py
- compute_annual_tax_summary() from tax_engine.py
- SignalState / SignalSeries / SignalPoint from signal_adapters.py
- get_adapter() / combine_signals() from signal_adapters.py
- SimulationConfig, SimulationResult, etc. from models/simulation.py
- SimulationRepo from services/simulation/repo.py

## Edge cases handled
- Empty price_series: raise ValueError immediately
- Missing signal for a date: skip the day (fault tolerant)
- Zero standard deviation (flat returns): Sharpe/Sortino → Decimal("0")
- XIRR non-convergence: return Decimal("0")
- Period < 365 days: absolute return, not annualized CAGR
- sell_pct=100 with small floating precision: clamp to total_units
- Reentry with zero liquid: no-op
- COMBINED signal: combined_config must be present in SimulationConfig

## Expected runtime
- 5-year daily simulation: ~1300 dates, O(n) walk = <100ms per run
- XIRR Newton: 20 iterations over cashflow list = negligible
- Full request with DB save: <500ms on t3.large

## Files
- CREATE: backend/services/simulation/backtest_engine.py
- CREATE: backend/services/simulation/analytics.py
- MODIFY: backend/services/simulation/service.py
- MODIFY: backend/services/simulation/__init__.py
- MODIFY: backend/routes/simulate.py
- CREATE: tests/unit/simulation/test_backtest_engine.py
- CREATE: tests/unit/simulation/test_analytics.py
