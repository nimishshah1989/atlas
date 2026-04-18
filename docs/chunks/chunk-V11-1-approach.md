# Chunk V11-1 Approach: Manifest + Health-Check Wiring + Scoring Calibration

## Data Scale
- No new tables. No DB queries in this chunk itself.
- Scripts read existing de_* tables (JIP, read-only). pg_stat row counts irrelevant here.
- This chunk is pure logic/wiring: YAML edits, Python script fixes, FastAPI routes, frontend page.

## Chosen Approach

### 1. data-coverage.yaml — mandatory fields
Add `mandatory: true` to all existing domains (equity_ohlcv, equity_technicals, equity_fundamentals, mf, mf_flows, indices, etfs, global_macros, relative_strength, market_breadth, rrg_quadrants, corporate_actions, institutional_flows, gold_lens, derived_signals) and `mandatory: false` to all `status: missing` domains (derivatives_eod, india_vix, insider_trading, block_bulk_deals, shareholding_patterns, yield_curve, fx_rates). `global_rates` is `status: existing` → `mandatory: true`.

### 2. check-data-coverage.py fixes

**Fix A: --mandatory-only flag**
- Add argparse `--mandatory-only` flag
- Pass to `collect_tables()` as new param with default=False
- In collect_tables loop: `if mandatory_only and not domain_spec.get("mandatory", True): continue`

**Fix B: Partition-aware freshness**
- Compile `_YEAR_PART_RE = re.compile(r".*_y(\d{4})$")` at module level
- At top of `score_freshness`: if year < current_year - 1 → return DimensionScore("freshness", 100.0, "archived partition...", {})
- Active partitions (current year, prev year) → normal check

**Fix C: Sampling-based integrity**
- In `score_integrity`: first fetchval pg_stat_user_tables for n_live_tup
- If est_rows > 500_000: use `TABLESAMPLE SYSTEM(1)` query
- Include "sampled" in detail string for large tables

**Fix D: --strict with --mandatory-only**
- Existing behavior already works since collect_tables filters the domain list

### 3. backend/routes/system_data_health.py
New file using bare-import pattern. Reads data-health.json with 60s in-process cache. Returns DataHealthResponse pydantic model.

### 4. backend/core/health_gate.py
New FastAPI dependency factory. Fail-open when file missing. Raises HTTP 503 with structured detail dict when domain failing.

### 5. system.py wiring
Bare import at bottom following established pattern.

### 6. Frontend: api-data-health.ts + page.tsx
TypeScript client + Server Component page at /forge/data-health. Groups by domain, shows 6 dimension badges per domain card.

### 7. CI step
Conditional on DATABASE_URL presence — skips gracefully in GitHub CI.

## Wiki patterns checked
- `importlib-isolation-standalone-scripts` — relevant for test loading of the script via importlib
- `bare-import-route-registration` — used for system_data_health.py registration

## Existing code reused
- `system_routines.py` as template for system_data_health.py structure
- Existing `_REPO_ROOT` pattern from system.py
- `router` from `backend.routes.system`

## Edge cases
- data-health.json missing → `available: False` with empty tables list (fail open)
- Archived year partition → freshness=100 (not stale)
- pg_stat returns NULL → treat as 0 rows (skip sampling)
- health_gate domain missing from file → pass through (fail open)
- Large table TABLESAMPLE → sample_rows_est = max(est_rows // 100, 1) prevents div/0

## Expected runtime
- Script runs in CI: full DB scan in <2 min for all tables
- Integrity on 1M-row table with TABLESAMPLE: <5s
- Unit tests (all AsyncMock): <5s total

## Implementation order
1. docs/specs/data-coverage.yaml — mandatory fields
2. scripts/check-data-coverage.py — all fixes + --mandatory-only
3. backend/core/health_gate.py — create
4. backend/routes/system_data_health.py — create
5. backend/routes/system.py — add bare import
6. frontend/src/lib/api-data-health.ts — create
7. frontend/src/app/forge/data-health/page.tsx — create
8. .github/workflows/ci.yml — add step
9. tests/unit/test_check_data_coverage_v11_1.py — create + run
