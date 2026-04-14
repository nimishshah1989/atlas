# Chunk V3-2 Approach: Indian FIFO Tax Engine

## Data Scale
This chunk is pure computation — no DB reads. No pg_stat_user_tables query needed.
The module processes in-memory lot queues per simulation run. Typical simulation:
- 10–20 years of monthly SIPs = 120–240 buy transactions
- Variable sells (signal-driven), maybe 5–30 sell events
- All well under 1K rows → any approach works; pure Python dataclasses chosen

## Chosen Approach

Pure Python module: `backend/services/simulation/tax_engine.py`
- No DB, no async, no I/O — deterministic computation only
- Dataclasses for TaxLot and LotDisposal (mutable, lightweight)
- Frozen dataclass for IndianTaxRates (immutable config)
- `collections.deque` for FIFO lot queue
- All arithmetic in `Decimal` — never float
- Two tax regimes gated by sell date vs 2024-07-23

## Wiki Patterns Checked
- `decimal-not-float` — Decimal(str(value)) pattern; no float annotations
- `prd-golden-example-testing` — golden fixture tests with exact Decimal assertions

## Key Design Decisions

### Tax regime switch
Budget 2024 changed rates on 23-Jul-2024. `IndianTaxRates.get_rates(sell_date)` returns
PRE or POST regime based on `sell_date >= date(2024, 7, 23)`.

### LTCG exemption
Applied at annual aggregate level, not per-transaction. `compute_tax_on_disposal`
computes raw tax on full gain; `compute_annual_tax_summary` applies exemption
to summed LTCG and then taxes the net.

### FIFO lot consumption
`FIFOLotTracker.sell_units` consumes from left of deque. If a lot is partially
consumed, remaining_units is reduced in-place. Lot stays in deque until exhausted.
Selling more than available raises `ValueError`.

### Financial year grouping
India FY = April 1 to March 31. Group disposals by FY of sell date.
`financial_year_start` param specifies which FY to summarize (pass Apr 1 of that year).

### Holding period
LTCG threshold = holding_days > 365 (>12 months). Spec says ">12 months".
365 days as proxy is standard Indian equity tax practice.

## Existing Code Reused
- `TaxDetail` and `TaxSummary` imported from `backend/models/simulation.py`
- `__init__.py` extended to export new tax engine classes

## Edge Cases Handled
- Sell at loss: gain <= 0 → zero TaxDetail (no negative tax)
- Sell exactly available units: works normally
- Sell more than held: raises ValueError with clear message
- Zero remaining units in lot: lot removed from deque
- NULL/None inputs: type system (Decimal) prevents this; dataclass constructors enforce types
- LTCG exemption > gains: max(ltcg - exemption, 0) → zero taxable LTCG

## Expected Runtime
Pure Python arithmetic on <1K lots: sub-millisecond. No concern.

## Test Strategy
14 tests in `tests/services/test_tax_engine.py`:
- Golden fixture tests with hand-computed expected values
- Exact Decimal comparisons (no pytest.approx)
- AST scan for float annotations (test_no_float_in_module)
- Determinism test (same inputs twice)
