# Chunk V1-7 Approach: Pipeline Runner + Systemd Timer

## Data Scale (from pg_stat_user_tables)
- de_rs_scores: 14.7M rows — JIP reads only, never direct SQL from atlas
- de_equity_technical_daily: 4.0M rows — JIP reads only
- atlas_intelligence: ~hundreds of rows (3 agents writing findings)
- atlas_decisions: ~hundreds of rows (decisions_generator writing)

All agent reads go through JIPDataService (never direct de_* SQL).
Pipeline itself does no bulk data processing — it orchestrates 3 agents in sequence.

## Chosen Approach

**Sequential orchestrator in `backend/pipeline.py`** — not a DAG executor.
V1 is simple: 3 agents run in order. rs_analyzer → sector_analyst → decisions_generator.
Keep it simple per spec ("V1 pipeline, not a DAG executor").

Key design decisions:
1. **Partial failure handling**: Each agent wrapped in try/except. Log error, continue with next agent. Return partial stats. Don't let one agent failure block others.
2. **CLI entry**: `atlas/__init__.py` + `atlas/pipeline/__init__.py` + `atlas/pipeline/__main__.py` to support `python -m atlas.pipeline run`. Python resolves the `atlas` package from the working dir `/home/ubuntu/atlas`.
3. **Latest date query**: `MAX(date) FROM de_rs_scores` via raw SQL text() on the JIP session — this is de_* read only, no write. JIPDataService doesn't expose a `get_latest_date()` method so we query it directly via text() within the pipeline. The de_* tables are read-only for atlas.
4. **IST datetime**: `datetime.timezone(timedelta(hours=5, minutes=30))` for IST, keeping it stdlib (no new deps).
5. **Module guard**: `if __name__ == "__main__": asyncio.run(main())` in `__main__.py` — never module-level side effects.
6. **structlog**: All logging via structlog with context vars. No print().

## Wiki Patterns Checked
- Pipeline ABC Orchestration — not using ABC (V1 is too simple), but adopting the sequential agent calling pattern
- Module-Level Side Effect — using `if __name__ == "__main__":` guard everywhere
- Pure Computation Agent — all 3 agents are pure computation, no LLM
- Idempotent Upsert — agents already handle idempotency; pipeline just re-runs them

## Existing Code Being Reused
- `backend/agents/rs_analyzer.py` — `run(db, jip, data_as_of)`
- `backend/agents/sector_analyst.py` — `run(db, jip, data_as_of)`
- `backend/agents/decisions_generator.py` — `run(db, data_as_of)`
- `backend/db/session.py` — `async_session_factory`
- `backend/clients/jip_data_service.py` — `JIPDataService`
- `backend/config.py` — `get_settings()`
- Test mocking patterns from `tests/agents/test_rs_analyzer.py`

## Edge Cases
- NULLs: All agents handle None gracefully already. Pipeline handles agent failures.
- Missing data_as_of: Query MAX(date) from de_rs_scores, fall back to today IST.
- Empty results: Agents already handle empty JIP responses (write summary finding with 0 counts).
- Partial agent failure: Wrap each agent call in try/except, log, continue.
- Naive datetime: Each agent raises ValueError. Pipeline validates before passing.

## Expected Runtime
- JIP queries: fast (<1s each, uses indexes)
- rs_analyzer: ~500 equities × DB query = ~5-10s total
- sector_analyst: ~30 sectors × DB query = ~1-2s total
- decisions_generator: ~500-600 findings × idempotency check = ~5-10s total
- Total expected: <60s on cassette fixture, <2min on live data
- Well within 5min requirement

## Files to Create
- `backend/pipeline.py` — pipeline orchestrator
- `atlas/__init__.py` — thin package
- `atlas/pipeline/__init__.py` — re-export
- `atlas/pipeline/__main__.py` — CLI entry point
- `backend/systemd/atlas-pipeline.service` — systemd service
- `backend/systemd/atlas-pipeline.timer` — systemd timer
- `tests/integration/test_v1_pipeline.py` — integration tests

## Files NOT to Modify
- Any existing backend/ or tests/ files (per spec)
