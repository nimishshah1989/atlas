---
chunk: V5-8
project: atlas
date: 2026-04-15
---

# V5-8 Approach: Briefing Writer Pipeline (TradingAgents Debate Fork)

## Data Scale
- `atlas_intelligence`: small (few hundred rows from prior agent runs)
- `atlas_briefings`: new table — 1 row per trading day per scope (tiny at start)
- All reads are via select on AtlasIntelligence ORM model — no full-table scans
- Expected runtime: <5s per run (6 LLM calls serial, each ~1-2s)

## Chosen Approach

### Model
- BigInteger BIGSERIAL primary key (high-write append pattern, consistent with AtlasAlert, AtlasCostLedger)
- Functional unique index on (date, scope, COALESCE(scope_key, '__null__')) — needed because scope_key is NULLable
- Raw SQL text() for upsert — ORM can't express functional index conflict targets (confirmed by ON CONFLICT Partial/Functional Index bug pattern)

### Upsert pattern
```sql
INSERT INTO atlas_briefings (...) VALUES (...)
ON CONFLICT (date, scope, COALESCE(scope_key, '__null__'))
DO UPDATE SET ...
```
Must match the index definition exactly.

### Agent architecture
- 4 sub-agents (macro, sentiment, technical, risk) via LLM haiku — perspective paragraphs
- Bull/bear debate: compose from perspectives, judge picks conviction
- Editor synthesis via sonnet — returns JSON with structured fields
- JSON parse with try/except fallback to raw text as narrative

### LLM calls
- 4 sub-agent perspectives: DEFAULT_MODEL (haiku)
- 1 debate judge: DEFAULT_MODEL (haiku, simpler task)
- 1 editor synthesis: claude-sonnet-4-5-20241022 (structured JSON output)
- Total: 6 LLM calls per run

### Staleness handling
- Read atlas_intelligence with SELECT filtered by data_as_of range
- If 0 rows found → set staleness_flags = {"upstream": "no_findings", "scope": "market"}
- Still produce a briefing (fault-tolerant: partial data > no data)

### JSONB sanitization
- _sanitize_for_jsonb() from intelligence.py pattern — convert Decimal→str recursively
- Applied to evidence before store_finding and to JSONB fields before upsert

## Wiki patterns checked
- Idempotent Upsert — ON CONFLICT DO UPDATE, natural key = (date, scope, scope_key)
- ON CONFLICT Partial/Functional Index — use expression not constraint name
- AsyncMock Context Manager Pattern — AsyncMock for db session and httpx client in tests
- Decimal in JSONB Persist — sanitize at persist boundary (12x seen)

## Existing code reused
- `backend/services/llm_client.complete()` — all LLM calls
- `backend/services/intelligence.store_finding()` — write companion finding
- `backend/services/intelligence._sanitize_for_jsonb()` — imported for JSONB safety
- Pattern from `backend/agents/investor_personas.py` — agent structure, structlog, Decimal

## Edge cases
- NULL scope_key: handled by COALESCE in index and upsert conflict target
- JSON parse failure from editor LLM: fallback to raw text as narrative, empty lists for arrays
- Missing upstream intelligence: staleness_flags set, briefing still produced
- Naive datetime: raise ValueError immediately (consistent with all agents)
- Decimal in evidence dicts: _sanitize_for_jsonb before any JSONB write

## Expected runtime on t3.large
- 6 LLM calls @ ~1-2s each = ~8-12s total
- DB reads and writes: <100ms
- Total: ~10-15s per run

## Files
1. `backend/db/models.py` — add AtlasBriefing model after AtlasCostLedger
2. `alembic/versions/g6b7c8d9e0f1_v5_8_briefings_table.py` — new migration
3. `backend/agents/briefing_writer.py` — agent implementation
4. `tests/agents/test_briefing_writer.py` — integration tests (6 required)
