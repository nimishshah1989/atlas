# V3-7 Approach: In-process auto-loop scheduler + drift alert + re-optimization handoff

## Data Scale
atlas_simulations table: small dev data, <50 rows. Scheduler reads is_auto_loop sims — likely 0-5.
No large-scale data concerns. All data fits in memory easily.

## Chosen Approach

### 1. In-process Scheduler (`backend/services/simulation/scheduler.py`)
- Use `croniter` (just installed) for cron expression parsing
- `asyncio` background task (not APScheduler/Celery — zero new deps)
- `asyncio.create_task()` started in FastAPI `lifespan` context manager
- Poll loop: sleep 60s, check all auto_loop sims whose next cron fire is past
- `SimulationScheduler` class with `start()`, `stop()`, `status()` methods
- State: is_running bool, last_run_at datetime, next_run_at datetime, active_simulations count
- Logs via structlog. No print()

### 2. Drift Detector (`backend/services/simulation/drift_detector.py`)
- Pure computation — no async, no DB
- `DriftThresholds` as Pydantic model (not frozen dataclass per spec note)
- `detect_drift(summary_delta, thresholds) -> list[DriftAlert]`
- Severity: HIGH if delta_pct >5%, CRITICAL if >20%
- All values Decimal. Convert via Decimal(str(x)) at boundary.
- Integrates into `_rerun_single_sim()` in service.py

### 3. Re-optimization Handoff
- `drift_history` JSONB column on `atlas_simulations` via Alembic migration
- `drift_alerts` + `needs_reoptimization` fields added to `AutoLoopResultItem`
- GET `/{sim_id}/drift-history` — static-before-path-param already respected in route file
- POST `/{sim_id}/reoptimize` — reads config, dispatches to existing optimizer
- Both routes must register BEFORE `/{sim_id}` GET and DELETE handlers (wiki pattern)

## Wiki Patterns Checked
- FastAPI Static Route Before Path Param (2x promoted) — CRITICAL for /drift-history and /reoptimize
- Decimal in JSONB Persist (9x) — drift_history JSONB uses sanitize_for_jsonb()
- Decimal Not Float — all financial values stay Decimal

## Existing Code Reused
- `sanitize_for_jsonb()` from `backend/services/simulation/helpers.py`
- `SimulationRepo` from `backend/services/simulation/repo.py`
- `run_optimization()` from `backend/services/simulation/optimizer.py`
- `AutoLoopResultItem` extended with new fields (backwards compatible: Optional)

## Edge Cases
- Empty drift_history JSONB column: handle as `[]`
- Cron expression parse failure: log warning, skip sim (don't crash scheduler)
- Missing metric in summary_delta: skip that metric in drift detection (no KeyError)
- Delta computation: `| new - prev | / | prev |` — guard against division by zero (prev=0)
- Scheduler stop: cancel asyncio task with timeout
- `last_run_at` is None on first run: next_run_at computed from now

## Alembic Migration
Add `drift_history JSONB nullable=True` to atlas_simulations.
Use `--autogenerate` then clean. Add `# type: ignore[attr-defined]` on alembic.op.

## Route Registration Order (in simulate.py)
```
POST /run          (existing)
POST /save         (existing static — before /{id})
POST /auto-loop/run (existing static)
POST /optimize     (existing static)
GET  /scheduler/status  (NEW static — before /{id})
GET  /{sim_id}/drift-history  (NEW — DANGER: needs sub-path handling)
POST /{sim_id}/reoptimize     (NEW — DANGER: needs sub-path handling)
GET  /             (existing)
GET  /{sim_id}     (existing parameterized — last)
DELETE /{sim_id}   (existing parameterized — last)
```
Note: `/{sim_id}/drift-history` is fine because FastAPI matches exact routes first 
before parameterized ones. The `/{sim_id}` pattern will not capture `/scheduler/status` 
because `scheduler` won't validate as UUID. Still, ordering by specificity is best.

## Expected Runtime
Drift detection: <1ms per sim (pure Decimal arithmetic)
Scheduler poll: 60s sleep loop, negligible CPU
Tests: <5s total

## Files Modified
- `backend/models/simulation.py` — add DriftAlert, DriftThresholds, SchedulerStatusResponse, DriftHistoryResponse, ReoptimizeRequest
- `backend/services/simulation/drift_detector.py` — NEW
- `backend/services/simulation/scheduler.py` — NEW
- `backend/services/simulation/service.py` — integrate drift_detector into _rerun_single_sim
- `backend/db/models.py` — add drift_history column
- `backend/routes/simulate.py` — add 3 new routes
- `alembic/versions/` — migration file
- `backend/requirements.txt` — add croniter
- `tests/unit/simulation/test_drift_detector.py` — NEW
- `tests/unit/simulation/test_scheduler.py` — NEW
