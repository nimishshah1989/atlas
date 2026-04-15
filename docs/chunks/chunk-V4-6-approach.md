# Chunk V4-6: Daily Monitoring + Tax Harvesting

## Actual data scale
- No new DB tables. Pure computation modules (no SQL).
- Operates on in-memory lists of HoldingAnalysis objects (typ. 5-50 holdings).
- All scale: well under 1K rows — pure Python arithmetic is appropriate.

## Chosen approach
Pure computation pattern (same as `drift_detector.py` and `tax_engine.py`):
- No DB, no async, no I/O in the core modules
- All financial arithmetic in Decimal
- Fully deterministic: same inputs → same outputs

### monitoring.py
- `MonitoringAlertType` enum with 5 alert types
- `MonitoringThresholds` dataclass with configurable defaults
- `MonitoringAlert` Pydantic model with provenance
- `generate_monitoring_alerts()` — main entry point
- `consecutive_trading_days_lagging()` — helper counting contiguous LAGGING days
- Non-trading day: if `data_as_of` is weekend or holiday marker, return []
- LAGGING 28-day check: `len(consecutive_lagging_days) >= 28` exactly

### tax_harvest.py
- Thin wrapper over `backend.services.simulation.tax_engine`
- Imports `FIFOLotTracker`, `IndianTaxRates`, `TaxLot` from tax_engine
- Contains zero rate tables, zero cess constants, zero FIFO logic
- `identify_harvest_opportunities()` — calls `tracker.unrealized_gains()` per lot
- Per-lot analysis: checks each lot's holding_days to classify STCG vs LTCG
- Savings = abs(loss) × applicable_rate (STCG or LTCG) × (1 + CESS_RATE)

## Wiki patterns checked
- `AST-Scanned Anti-Pattern Detection` — used for the no-rate-tables test
- `PRD Golden Example Testing` — golden fixture for FIFO bit-for-bit match
- `Decimal Not Float` — all values use Decimal(str(...)) at boundaries
- `sum() Decimal Start Arg` — sum(..., Decimal("0")) throughout

## Existing code being reused
- `backend/services/simulation/tax_engine.py` — FIFOLotTracker, IndianTaxRates, TaxLot
- `backend/services/simulation/drift_detector.py` — structural reference for pure compute
- `backend/models/portfolio.py` — AnalysisProvenance, HoldingAnalysis

## Edge cases
- NULLs: all thresholds have defaults; None rs_composite skipped gracefully
- Empty holdings list: produces empty alert list
- Non-trading day: check `data_as_of.weekday() >= 5` → return []
- 27 consecutive LAGGING days: no alert (strictly < 28)
- 28 consecutive LAGGING days: alert fires
- 29 non-consecutive days with gap: no alert (gap breaks chain)
- Unrealized gain (positive): no harvest opportunity
- Mixed lots: only losing lots flagged

## Expected runtime
- Well under 1ms per portfolio on t3.large (pure Python Decimal arithmetic, <50 holdings)

## Files
New:
1. `backend/services/portfolio/monitoring.py`
2. `backend/services/portfolio/tax_harvest.py`
3. `tests/unit/portfolio/test_monitoring.py`
4. `tests/unit/portfolio/test_tax_harvest.py`

Edit:
1. `backend/models/portfolio.py`
