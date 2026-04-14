# Chunk V3-3 Approach: Signal Adapters

## Data Scale
No DB queries in this chunk. The signal adapters are a pure-computation module
(no DB, no async, no I/O). They receive pre-fetched time-series data as input dicts
and return SignalSeries objects. Scale is irrelevant here — the caller fetches from
de_* tables and passes data in.

## Chosen Approach
Pure computation module mirroring tax_engine.py structure:
- `dataclass` types (SignalState enum, SignalPoint, SignalSeries)
- Private `_apply_threshold_logic()` shared by all 7 adapters
- Public `adapt_*()` functions per signal source
- `combine_signals()` for AND/OR combining
- `get_adapter()` dispatcher/registry
- `_has_float_annotation()` AST utility reused from tax_engine pattern

All 7 signal adapters delegate to `_apply_threshold_logic()` which:
1. Extracts the relevant field from each raw data dict
2. Converts to Decimal (str path, never float)
3. Applies buy/sell/hold/reentry state machine

REGIME signal: string enum mapped to Decimal (BULL=100, RECOVERY=75, SIDEWAYS=50, BEAR=0)
before passing to `_apply_threshold_logic()`.

## Wiki Patterns Used
- [Decimal Not Float](patterns/decimal-not-float.md) — all values via Decimal(str(x))
- [Pure Computation Agent](patterns/pure-computation-agent.md) — no DB, no async, no I/O

## Existing Code Reused
- `backend/models/simulation.py` — `SignalType`, `CombineLogic` enums
- `backend/services/simulation/tax_engine.py` — structure, `_has_float_annotation()` pattern
- `backend/services/simulation/__init__.py` — add new exports

## Edge Cases
- Empty data list → return empty SignalSeries (not an error)
- NULL/None values in raw data dict → skip that data point (don't emit a SignalPoint)
- REGIME string not in mapping → raise ValueError with clear message
- reentry_level=None → REENTRY state never emitted
- Thresholds: buy_level may equal sell_level (user error) — still deterministic
- Single data point → works correctly
- combine_signals on empty series → returns empty SignalSeries

## Signal Logic (shared across all 7)
```
State machine per data point:
  if value <= buy_level:
      state = BUY
  elif value >= sell_level:
      state = SELL
  elif reentry_level is not None and prev_state == SELL and value <= reentry_level:
      state = REENTRY
  else:
      state = HOLD
```
Note: REENTRY fires when: previous state was SELL and current value <= reentry_level.
This allows re-entry between buy_level and sell_level (like a dead-cat bounce confirmation).

## Combined Signal Logic
- AND: BUY if both are BUY or REENTRY; SELL if either is SELL; else HOLD
- OR: BUY if either is BUY or REENTRY; SELL if both are SELL; else HOLD

## File Plan
- CREATE: `backend/services/simulation/signal_adapters.py`
- CREATE: `tests/services/test_signal_adapters.py`  
  (matches tax_engine.py → tests/services/test_tax_engine.py pattern)
- MODIFY: `backend/services/simulation/__init__.py`

## Expected Runtime
Pure Python computation. Even 10 years of daily data = ~3650 points. Sub-millisecond.
