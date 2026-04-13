# Chunk V1-6: Decisions Generator — Approach

## Data Scale
- `atlas_intelligence`: no live row count needed (mocked in tests; real data is small at this stage)
- `atlas_decisions`: new rows written by this agent; no existing rows to worry about
- Processing scale: 12 findings → 12 decisions. Python is fine.

## Approach

### Chosen pattern: Cross-Agent Synthesis (downstream consumer)
The decisions generator reads `atlas_intelligence` findings via `list_findings()` (same
service as upstream agents) and maps them to `atlas_decisions` rows via ORM INSERT.

No SQL aggregation needed — row count is small (12-fixture scale).
Idempotency: pre-INSERT check for existing (entity, decision_type, source_agent, data_as_of)
tuple. Skip if exists. Avoids unique-constraint migration.

### Wiki patterns checked
- Cross-Agent Synthesis — downstream reads upstream findings, degrades gracefully
- Idempotent Upsert — check-before-insert for decisions (no ON CONFLICT needed)
- Decimal Not Float — all confidence values stay Decimal; supporting_data sanitized via
  `_sanitize_for_jsonb` pattern from intelligence.py
- Decimal in JSONB Persist bug pattern — sanitize supporting_data at persist boundary

### Finding → Decision type mapping (spec §23.2)
```
rs-analyzer / quadrant_classification:
  LEADING   → buy_signal  (confidence 0.85)
  IMPROVING → buy_signal  (confidence 0.70, weaker)
  WEAKENING → sell_signal (confidence 0.75)
  LAGGING   → sell_signal (confidence 0.80)

rs-analyzer / quadrant_transition:
  to LEADING   → buy_signal  (confidence 0.85)
  to IMPROVING → buy_signal  (confidence 0.70)
  to WEAKENING → sell_signal (confidence 0.80)
  to LAGGING   → sell_signal (confidence 0.85)

sector-analyst / sector_rotation:
  to LEADING   → overweight (confidence 0.85)
  to IMPROVING → overweight (confidence 0.70)
  to WEAKENING → avoid      (confidence 0.80)
  to LAGGING   → avoid      (confidence 0.85)

sector-analyst / breadth_divergence:
  bullish_rs_weak_breadth  → avoid      (confidence 0.75) conflicting signals
  bearish_rs_strong_breadth → overweight (confidence 0.70) recovery signal
```

### DecisionSignal enum expansion
Add lowercase spec values alongside existing uppercase ones.
`decisions.py` route calls `DecisionSignal(r.decision_type)` so all DB values
must be valid enum members.

### Files to create/modify
1. CREATE `backend/agents/decisions_generator.py`
2. MODIFY `backend/models/schemas.py` — expand DecisionSignal
3. CREATE `tests/agents/test_decisions_generator.py`

### Edge cases handled
- NULL evidence in finding — use `{}` default
- findings with NULL entity — skip gracefully
- No findings → 0 decisions + clean summary log
- Decimal in supporting_data → sanitize via _sanitize_for_jsonb
- Naive datetime → raise ValueError (same as other agents)
- Re-run: existing (entity, decision_type, source_agent, data_as_of) → skip

### Expected runtime
Fixture scale (12 findings): <1ms. Even at 500 findings: <100ms (Python loop + 1 query
per decision for idempotency check). All within t3.large budget.
