# Chunk V5-10a Approach: Investor Persona Agents

## Data Scale
No new data reads — uses existing atlas_intelligence table and JIP data service.
Table is append-only write target.

## Chosen Approach

### Architecture
- 4 investor persona agents wrapped in a single module (`investor_personas.py`)
- Each persona: fixed agent_id = "persona-{name}", agent_type = "llm"
- LLM calls via httpx directly (no Anthropic SDK) — new `llm_client.py` wraps the API
- Every LLM call recorded in cost ledger before returning
- Cost ledger is a BigInteger PK table (append-only, high-write)

### Key decisions
1. **No Anthropic SDK**: httpx POST to `https://api.anthropic.com/v1/messages` directly. Spec says no SDK needed, just add httpx (already in requirements).
2. **Cost ledger first**: `record_llm_call` always called after every LLM response, before returning text.
3. **Decimal for cost**: pricing constants are `Decimal`, cost calculation uses `Decimal` arithmetic.
4. **Persona prompt reads RS data from JIP**: `get_stock_detail()` for each stock, constructs persona-specific narrative for LLM.
5. **Findings evidence**: includes persona_name, data_as_of, rs_values, llm_model used — full provenance.

### Alembic migration
- Revises from `f5a6b7c8d9e0` (latest V5-2 agent tables)
- New revision hash: `a8b9c0d1e2f3`
- Creates single table `atlas_cost_ledger`

## Wiki Patterns Checked
- **Pure Computation Agent**: This chunk extends it to LLM agents — same contract (db, jip, data_as_of), same store_finding write path
- **Budget-Aware API Integration**: Cost ledger implements the two-layer approach — record per call, queryable for budget checks
- **Decimal Not Float**: All pricing in Decimal, cost calculation Decimal arithmetic
- **Decimal in JSONB Persist**: evidence dict sanitized before JSONB write (handled by store_finding._sanitize_for_jsonb)
- **Alembic Mypy attr-defined**: `# type: ignore[attr-defined]` on alembic op import

## Existing Code Reused
- `backend/services/intelligence.py::store_finding()` — identical write path
- `backend/agents/goldilocks_analyst.py` — test structure cloned
- `backend/clients/jip_data_service.py` — read via JIP only
- `backend/agents/rs_analyzer.py` — `classify_quadrant()` for RS context in prompt

## Edge Cases
- ANTHROPIC_API_KEY missing → RuntimeError raised immediately (not silently skipped)
- httpx timeout (60s) → exception propagates, LLM call not recorded (no partial ledger entry)
- LLM returns empty content → use empty string, still write finding
- NULL rs_composite/rs_momentum → skip that stock, log warning
- Decimal in evidence → all values serialized as str() before JSONB

## Expected Runtime
- 4 personas × 5 stocks each = 20 LLM calls
- At 500ms per call = ~10s total (async sequential per persona)
- On t3.large: well within acceptable range

## Files to Create/Modify
1. MODIFY: `backend/db/models.py` — AtlasCostLedger
2. CREATE: `alembic/versions/a8b9c0d1e2f3_v5_10a_cost_ledger.py`
3. CREATE: `backend/services/cost_ledger.py`
4. CREATE: `backend/services/llm_client.py`
5. CREATE: `backend/agents/investor_personas.py`
6. MODIFY: `backend/agents/__init__.py`
7. CREATE: `tests/agents/test_investor_personas.py`
