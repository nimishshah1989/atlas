# Chunk V11-0: Routine Visibility — Approach

## Date
2026-04-18

## Data Scale
- Database unreachable in this environment (EC2 / RDS not connected), so de_routine_runs check is skipped — graceful degradation path is the primary path
- Manifest has 10 existing + 14 new_routines = 24 total routines

## Chosen Approach

### Backend
1. **`backend/models/routines.py`** — Pure Pydantic v2 models: RoutineLastRun, RoutineEntry, RoutinesResponse. No DB mapping.
2. **`backend/services/routines_service.py`** — Reads YAML manifest with `yaml.safe_load` (pyyaml 6.0.3 available in venv). Queries `de_routine_runs` via `text()` SQL (DISTINCT ON pattern per wiki). Catches all exceptions for graceful degradation. Module-level `_prev_statuses: dict[str, str]` for transition logging.
3. **`backend/routes/system_routines.py`** — Imports `router` from system.py, registers route. Own 60s cache dict (separate from system.py's 10s cache) to avoid TTL collision.
4. **`backend/routes/system.py`** — Add 1 import line at bottom (same pattern as system_roadmap).

### Wiki Patterns Applied
- **Conftest Integration Marker Trap** — tests go in `tests/routes/` not `tests/api/`
- **FastAPI Dependency Patch Gotcha** — `app.dependency_overrides[get_db]` in tests
- **Session Poisoning Missing Table** bug-pattern — `UndefinedTableError` / `ProgrammingError` catch + rollback not needed (read-only query)
- **DISTINCT ON Latest-Row-Per-Key** — query pattern for latest run per routine_id
- **Facade Split God Module** — system_routines.py imports router from system.py

### Existing Code Reused
- `backend/db/session.py` get_db dependency
- `backend/routes/system.py` router (prefix /api/v1)
- `yaml.safe_load` from pyyaml (already in venv via ruamel.yaml bringing it in, and pyyaml directly present)
- `structlog.get_logger()` pattern from every other service

### YAML Library
- `import yaml` (pyyaml 6.0.3) — same as `backend/core/roadmap_loader.py`. NOT ruamel.yaml (different API). pyyaml `yaml.safe_load` is the simpler choice.

### Edge Cases
- `de_routine_runs` missing → catch ProgrammingError + generic Exception → return {} + set data_available=False
- `table` field in manifest can be a comma-separated string like "de_index_prices, de_index_technical_daily" OR partitioned like "de_equity_ohlcv_y{YEAR}" → `_parse_tables()` splits on comma
- `new_routines` have `target_table` instead of `table`, no `source` (has `source_url`), no `status` field
- `sla_freshness_hours` is optional — existing routines may not have it
- NULL `ran_at` with SLA set → breach = True
- IST timezone conversion for timestamps in frontend

### Expected Runtime
- Manifest load: <5ms (small YAML file)
- DB query: <500ms (DISTINCT ON over a small table or graceful fail)
- Total: well under 1s on t3.large

## Files to Create/Modify
- `backend/models/routines.py` — CREATE
- `backend/services/routines_service.py` — CREATE
- `backend/routes/system_routines.py` — CREATE
- `backend/routes/system.py` — MODIFY (1 line at bottom)
- `frontend/src/lib/api-routines.ts` — CREATE
- `frontend/src/app/forge/routines/page.tsx` — CREATE
- `tests/routes/test_routines.py` — CREATE
