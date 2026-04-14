# Chunk V3-5 Approach: Simulation Listing + Auto-Loop

## Data scale
- atlas_simulations: new table, minimal rows in dev (sub-1K). All queries are simple SELECT with limit.
- No large-data concerns — this is CRUD + auto-loop orchestration.

## Chosen approach
- Wire 5 new endpoints in `backend/routes/simulate.py` (replace 501 stub + add 4 new)
- Add 5 service methods to `SimulationService` (list, get, save_config, delete, run_auto_loop)
- Add 4 new Pydantic models to `backend/models/simulation.py`
- Write 2 test files: test_listing.py, test_auto_loop.py

No schema changes needed — `AtlasSimulation` ORM and `SimulationRepo` already have all required fields/methods.

## Wiki patterns checked
- **AsyncMock Context Manager Pattern** — use `AsyncMock` for db session, `MagicMock` for execute results
- **Contract Stub 501 Sync** — the GET / stub must be removed when wiring real impl
- **Decimal in JSONB Persist** (bug pattern) — _sanitize_decimal already exists in service; reuse it for save_config
- **FastAPI Dependency Patch Gotcha** — tests must mock get_db even when service is mocked

## Existing code being reused
- `SimulationRepo.list_simulations`, `get_simulation`, `soft_delete`, `lock_for_update` — all exist
- `SimulationRepo.save_simulation` — already handles persist
- `_sanitize_decimal` helper inside service._persist — copy/refactor to module-level for reuse
- `SimulationListItem`, `SimulationListResponse` — already in models/simulation.py

## New models needed
- `SimulationDetailResponse` — full sim result + config + metadata
- `SimulationSaveRequest` — config + name + is_auto_loop + auto_loop_cron
- `SimulationSaveResponse` — id + name + created_at
- `AutoLoopResultItem` — simulation_id + status + summary_delta
- `AutoLoopResponse` — list of AutoLoopResultItem + ran_at

## Edge cases
- NULLs: user_id is Optional — repo handles None → no filter
- Missing sim (soft-deleted or never existed) → 404
- Auto-loop: one sim failure must NOT abort others → per-sim try/except
- Auto-loop: lock_for_update prevents concurrent races
- save_config: does NOT run backtest, just persists config + metadata
- JSONB: Decimal → str sanitization needed for config persist (reuse existing helper)
- last_auto_run: set after successful re-run per sim

## Route ordering (FastAPI path priority)
- POST /save must be registered BEFORE GET /{id} to avoid "save" matching as UUID
- POST /auto-loop/run similarly must precede any /{id} patterns

## Expected runtime
- List (50 rows): < 10ms
- Get by ID: < 5ms  
- Save: < 20ms (one INSERT)
- Auto-loop: N * backtest_time, each backtest ~100ms on test data → negligible for <20 sims
