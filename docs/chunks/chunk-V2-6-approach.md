# Chunk V2-6 Approach — MF Decisions Generator

## Data scale
- `atlas_decisions`: small table (<<1K rows in dev), write-only for this agent
- `atlas_intelligence`: small table (<<1K rows in dev), read via `list_findings()` service
- No de_* table reads at all. Pure atlas_intelligence → atlas_decisions.

## Chosen approach
Pure-computation agent pattern (identical to V1 decisions_generator). No LLM calls.
Two MF-specific finding types consumed:
1. `mf_quadrant_transition` from `mf-rs-analyzer`
2. `mf_flow_reversal` from `mf-flow-analyzer`

Reads via `backend.services.intelligence.list_findings()` (not direct SQL).
Writes to `atlas_decisions` (existing table, no migration needed).
Single `run(db, data_as_of)` entry point, idempotent via `_decision_exists()`.

## Wiki patterns checked
- `pure-computation-agent` — exact match for this agent's shape
- `cross-agent-synthesis` — downstream reads upstream agent findings
- `decimal-not-float` — confidence as Decimal("0.85") etc.
- `decimal-in-jsonb-persist` bug — sanitize supporting_data before JSONB insert

## Existing code being reused
- `backend/agents/decisions_generator.py` — structural template (copy pattern, not code)
- `backend/db/models.AtlasDecision` — existing ORM model with user_action, user_action_at, user_notes fields (V1 lifecycle fields)
- `backend/services.intelligence.list_findings` — existing service method

## Finding→decision mapping
| finding_type | evidence field | decision_type | confidence |
|---|---|---|---|
| mf_quadrant_transition | quadrant=LEADING | buy_signal | 0.85 |
| mf_quadrant_transition | quadrant=IMPROVING | buy_signal | 0.70 |
| mf_quadrant_transition | quadrant=WEAKENING | sell_signal | 0.75 |
| mf_quadrant_transition | quadrant=LAGGING | sell_signal | 0.80 |
| mf_flow_reversal | flow_direction=positive_to_negative | avoid | 0.75 |
| mf_flow_reversal | flow_direction=negative_to_positive | overweight | 0.70 |

## Edge cases
- NULL entity → skip with log.warning, return False
- Unknown quadrant/flow_direction → mapper returns None → skip
- Naive datetime in run() → raise ValueError immediately
- Decimal in supporting_data → sanitize via _sanitize_for_jsonb()
- Re-run same data_as_of → _decision_exists() returns True → skip
- Empty findings list → 0 written, no db.commit() call

## Entity types
- mf_quadrant_transition findings → entity_type from finding (should be "mutual_fund")
- mf_flow_reversal findings → entity_type from finding (should be "mf_category")

## Expected runtime on t3.large
Sub-second. Reads are bounded lists (limit=200), all Python computation, 
no heavy SQL aggregation.

## Files
- `backend/agents/mf_decisions_generator.py` (new)
- `tests/agents/test_mf_decisions_generator.py` (new)
