# Chunk V5-4 Approach: Intelligence Memory Service Compliance

## Data Scale
- `atlas_intelligence` table: checked via pg_stat; row count not needed for this chunk (no full-table loads, no data queries in this chunk — only service logic and test coverage changes).
- This chunk touches no data pipelines; no scale decision needed.

## Scope
Two files only:
1. `backend/services/intelligence.py` — two small changes
2. `tests/services/test_intelligence.py` — add comprehensive unit tests

## Changes to intelligence.py

### 1. Float type check in store_finding (line 27)
Add `if isinstance(confidence, float): raise TypeError("confidence must be Decimal, not float")` BEFORE the range check. This must come first so it fires before the Decimal comparison.

### 2. Add agent_id to get_relevant_intelligence log event (line 215)
The existing `log.info("intelligence_searched", ...)` call is missing `agent_id` and `query`. Add both to satisfy FR-023. Truncate query to 200 chars for log safety.

## Changes to test_intelligence.py

New unit tests to add (all mocked, no real DB):

1. **test_store_finding_float_confidence_raises_type_error** — pass `0.8` (float), assert TypeError with "Decimal" in message
2. **test_store_finding_happy_path** — mock embed + db.execute chain + db.commit; verify returned row has correct agent_id/entity
3. **test_get_relevant_intelligence_no_filters** — mock embed + db.execute returning empty ids; verify returns []
4. **test_get_relevant_intelligence_with_entity_filter** — verify entity appears in params dict passed to db.execute
5. **test_get_relevant_intelligence_with_all_filters** — entity + entity_type + finding_type + agent_id all in params
6. **test_get_relevant_intelligence_expired_exclusion** — verify "expires_at" WHERE clause present in search SQL
7. **test_get_relevant_intelligence_fr023_log_event** — use structlog.testing.capture_logs() to verify agent_id + query[:200] + top_k in log event
8. **test_list_findings_with_entity_filter** — mock db.execute, call list_findings(entity="AAPL"), verify stmt builds correctly
9. **test_list_findings_with_agent_id_filter** — similar for agent_id filter
10. **test_list_findings_with_min_confidence** — min_confidence filter
11. **test_get_finding_by_id_happy_path** — mock db.execute returning a row
12. **test_get_finding_by_id_not_found** — mock returning None

## Wiki patterns checked
- AsyncMock Context Manager Pattern — for mock DB async context managers
- Embedding Fault Tolerance in Store Path — confirms _try_embed already handles EmbeddingError
- structlog.testing.capture_logs() — standard pattern for log event assertion

## Edge cases
- Float confidence must raise before Decimal comparison (ordering matters)
- Query truncation to 200 chars for log safety (long queries from agents)
- structlog testing uses `structlog.testing.capture_logs()` context manager
- Mock DB for list_findings/get_finding_by_id uses SQLAlchemy ORM path (select()), not raw text SQL — mock must handle `.scalars().all()` chain

## Expected runtime
No DB queries. Pure unit tests. Expected: <10s for full test file.
