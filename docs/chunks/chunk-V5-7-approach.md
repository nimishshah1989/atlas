# Chunk V5-7 Approach: LangGraph Agent Orchestration Scaffold

## Actual data scale
No DB reads or writes in this chunk. Pure in-memory graph execution engine. No table scans needed.

## Chosen approach
Pure Python async DAG executor — no new dependencies. Uses:
- `dataclass` + `asyncio` for graph state and node execution
- Kahn's algorithm (topological sort) for deterministic execution order
- try/except per node so no exception escapes `execute()`
- `is_stale` flag propagated to downstream nodes when any dep fails

Chosen over alternatives because:
- LangGraph/langchain not installed (heavy deps, spec forbids)
- Pure Python keeps it auditable and test-friendly
- Matches the DAG Executor wiki pattern (topological sort + failure isolation)

## Wiki patterns checked
- `architecture/dag-executor.md` — Kahn's algorithm, state machine per node (PENDING→RUNNING→SUCCESS/FAILED), failure isolation
- `patterns/cross-agent-synthesis.md` — partial data graceful degradation, each source optional

## Existing code being reused
- `structlog` pattern from `backend/services/llm_client.py` — same `log = structlog.get_logger(__name__)` convention
- IST timezone constant pattern from existing services

## Edge cases
- Cycle in graph: `_topological_sort()` detects via len(order) != len(nodes), returns stale state
- Unknown dependency: raises ValueError in sort, caught in execute(), returns stale
- Node B depends on failed node A: node B still executes but gets `is_stale=True`
- Empty graph: topological sort returns `[]`, execute completes immediately, is_stale=False
- Node raises non-Exception BaseException: spec says no exception escapes — bare `except Exception` is sufficient; BaseException (KeyboardInterrupt, SystemExit) intentionally not caught

## Expected runtime on t3.large
Graph execution is pure in-memory async — sub-millisecond for the test graphs. No IO.

## Files
- `backend/services/agent_graph.py` (NEW)
- `tests/services/test_agent_graph.py` (NEW)
- `tests/services/__init__.py` already exists
