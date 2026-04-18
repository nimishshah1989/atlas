# Chunk V11-6 Approach: vectorbt port of backtest engine

## Data Scale
No new DB tables. Pure computation module — no row count queries needed.
This chunk is entirely in-memory: price_series + signal_series → BacktestResult.
The performance test uses 1000-day synthetic data × 100 configs; all in RAM.

## Chosen Approach

### VectorbtEngine (single-run parity mode)
- Mirror BacktestEngine loop day-by-day, using float64 arithmetic internally.
- FIFOLotTracker called with Decimal inputs (via _D helper) for tax correctness — identical to legacy.
- At output boundary: convert all float64 → Decimal via _D(value).
- This gives ≥4 decimal parity with legacy because the only float≠Decimal difference is floating-point noise beyond 10 decimal places, which rounds away at 4 decimals.
- _D helper: `lambda v: Decimal(str(round(float(v), 10)))` — Computation Boundary pattern.

### VectorbtBatchEngine (parallel sweep mode)
- numpy broadcasting: configs × dates matrix in one pass.
- SELL/REENTRY explicitly not modeled (documented limitation).
- SIP mask via _compute_sip_mask() helper (pure Python, one pass).
- BUY signal mask from signal_series.
- units matrix = np.cumsum(sip_units + buy_units, axis=0); shape (n_dates, n_configs).
- 100 configs × 1000 days = trivial numpy operation, easily 10x faster than 100 sequential Python loops.

### Engine dispatch in service.py
- Add `engine: str = "vectorbt"` param to run_backtest().
- Import guard: lazy import at dispatch time.

### Route param
- `engine: str = Query(default="vectorbt", pattern="^(legacy|vectorbt)$")` in /run endpoint.

## Wiki Patterns Checked
- Computation Boundary Pattern (29x seen) — _D helper at all output conversions.
- Decimal Not Float — float64 only internal to VectorbtEngine, never in public return types.
- AST-Scanned Anti-Pattern Detection — no bare float annotations in new file.

## Existing Code Being Reused
- FIFOLotTracker from tax_engine.py — identical call pattern in VectorbtEngine.
- BacktestResult dataclass — same return type from both engines.
- DailyValue, TransactionRecord models — same in both engines.
- _make_config, _make_price_series, _make_signal_series helpers from test_backtest_engine.py — copied to test files.

## Edge Cases
- Empty price_series: ValueError (same as legacy).
- No overlapping dates: ValueError (same as legacy).
- Zero sip_amount: SIP mask fires but no units added (same as legacy).
- Zero lumpsum_amount: BUY signal day, no units added (same as legacy).
- sell_pct=0: no sell happens (same as legacy).
- Cooldown: VectorbtEngine maintains last_lumpsum_date (same as legacy).
- SELL with no units held: skip (same as legacy, lot_tracker.total_units check).
- REENTRY with no liquid: skip.
- Batch engine: SELL/REENTRY signals → silently ignored (documented, expected).

## Performance Target
- 100 configs × 1000 trading days (≈4 years).
- Legacy: 100 sequential loops of 1000-day simulation ≈ 5-10s.
- VectorbtBatchEngine: numpy matrix ops on (1000, 100) arrays ≈ 0.1-0.5s.
- Speedup ≥ 10× is achievable with pure numpy cumsum (no Python loops over configs).

## Expected Runtime on t3.large
- Test suite (parity 60 assertions): < 5s.
- Performance test: < 30s total (100 legacy + 1 batch run).
- Gate check: < 2 min.

## Files
1. CREATE backend/services/simulation/vectorbt_engine.py
2. MODIFY backend/routes/simulate.py (add ?engine= param)
3. MODIFY backend/services/simulation/service.py (engine dispatch)
4. CREATE tests/unit/simulation/test_backtest_parity.py
5. CREATE tests/unit/simulation/test_backtest_perf.py
