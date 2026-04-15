---
chunk: V5-12
project: atlas
date: 2026-04-15
status: in-progress
---

# V5-12: Darwinian Daily Weight Adjustment — Approach

## Scope
Fix a tie-break bug in `compute_new_weight()` and add comprehensive tests for quartile
logic, floor/ceiling clamps, even-distribution tie-break, holiday no-op, and the DB
CHECK constraint.

## Data Scale
No data reads — this chunk is pure unit tests + one two-line code fix.  
No psql query needed (zero DB writes, pure computation module).

## Existing Code Being Reused
- `backend/agents/darwinian_scorer.py` — `compute_new_weight()` (line 142-170),
  `_update_agent_weights()` (line 281-308), `WEIGHT_CAP`, `WEIGHT_FLOOR`,
  `WEIGHT_TOP_QUARTILE_FACTOR`, `WEIGHT_BOTTOM_QUARTILE_FACTOR`
- `backend/db/models.py` — `AtlasAgentWeight.__table_args__` with
  `CheckConstraint("weight >= 0.3 AND weight <= 2.5", name="ck_agent_weight_range")`
- `tests/agents/test_darwinian_scorer.py` — existing `TestWeightAdjustment` class (lines 543-578)

## Wiki Patterns Checked
- [Pure Computation Agent](~/.forge/knowledge/wiki/patterns/pure-computation-agent.md) —
  zero LLM, deterministic, Decimal throughout
- [Decimal Not Float](~/.forge/knowledge/wiki/patterns/decimal-not-float.md) — all
  weight arithmetic uses `Decimal`, clamp returns `Decimal`

## Bug
When all agents have the same rolling accuracy, `p25 == p75`, so
`rolling_accuracy >= p75` is always True for every agent — all get boosted.
Fix: after computing p25/p75, if `p25 == p75` return `current_weight` unchanged.

## Chosen Approach
1. One-line guard in `compute_new_weight()` right after p75 is computed.
2. Add new test class `TestDarwinianDailyWeightAdjustment` to existing test file.
   Tests are pure unit — no DB, no mocks beyond what is necessary.

## Edge Cases
- `rolling_accuracy is None` → already returns `current_weight` (line 153)
- `all_accuracies` empty → already returns `current_weight` (line 153)
- Single agent (n=1) → `p25 = sorted_acc[0]`, `p75 = sorted_acc[0]`, p25==p75 → unchanged
- All equal accuracies → p25==p75 → unchanged (the fix)
- Current weight at ceiling (2.5), top quartile → clamped, no overflow
- Current weight at floor (0.3), bottom quartile → clamped, no underflow
- Weight just under ceiling (2.45 × 1.05 = 2.5725 → clamps to 2.5)
- Weight just above floor (0.31 × 0.95 = 0.2945 → clamps to 0.3)

## Files Modified
- `backend/agents/darwinian_scorer.py` — add `if p25 == p75: return current_weight`
- `tests/agents/test_darwinian_scorer.py` — add `TestDarwinianDailyWeightAdjustment` class

## Expected Runtime
Pure Python unit tests — sub-second.
